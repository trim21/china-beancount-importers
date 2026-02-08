from __future__ import annotations

import dataclasses
import decimal
import re
from collections.abc import Iterable
from datetime import date
from email import parser, policy
from email.message import EmailMessage
from pathlib import Path

from beancount import Amount
from beancount.core import data, flags
from beancount.core.number import D
from beangulp.importer import Importer
from bs4 import BeautifulSoup
from bs4.element import Tag

from .utils import make_posting, make_transaction


@dataclasses.dataclass(frozen=True, slots=True)
class Record:
    trade_date: date
    description: str
    currency: str
    amount: decimal.Decimal


_CCB_CN_DATE_RE = re.compile(r"(?P<y>\d{4})年(?P<m>\d{1,2})月(?P<d>\d{1,2})日")
_CCB_DATE_RANGE_RE = re.compile(
    r"(?P<s>\d{4}年\d{1,2}月\d{1,2}日)\s*(?:至|\-|—|~|～)\s*(?P<e>\d{4}年\d{1,2}月\d{1,2}日)"
)
_CCB_ISO_DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")


def parse_amount(raw: str) -> decimal.Decimal:
    """Parse amount strings like '1,234.56' or '(1,234.56)' and return a Decimal."""

    cleaned = raw.replace(",", "").strip()
    sign = 1
    value = cleaned
    if cleaned.startswith("(") and cleaned.endswith(")"):
        sign = -1
        value = cleaned[1:-1]
    return decimal.Decimal(value) * sign


def parse_date(raw: str) -> date:
    return date(year=int(raw[0:4]), month=int(raw[5:7]), day=int(raw[8:10]))


def _parse_cn_date(raw: str) -> date:
    m = _CCB_CN_DATE_RE.search(raw)
    if not m:
        raise ValueError(f"Cannot parse chinese date: {raw!r}")
    return date(int(m.group("y")), int(m.group("m")), int(m.group("d")))


def _extract_statement_date(text: str) -> date | None:
    idx = text.find("Statement Date")
    haystack = text[idx : idx + 300] if idx != -1 else text
    m = _CCB_ISO_DATE_RE.search(haystack)
    if not m:
        return None
    return parse_date(m.group(0))


def _extract_billing_period(text: str) -> tuple[date, date] | None:
    stmt_date = _extract_statement_date(text)
    candidates: list[tuple[date, date]] = []
    for m in _CCB_DATE_RANGE_RE.finditer(text):
        start = _parse_cn_date(m.group("s"))
        end = _parse_cn_date(m.group("e"))
        if start <= end:
            candidates.append((start, end))

    if not candidates:
        return None

    if stmt_date is not None:
        for start, end in candidates:
            if end == stmt_date:
                return start, end

    for m in _CCB_DATE_RANGE_RE.finditer(text):
        prefix = text[max(0, m.start() - 24) : m.start()]
        if "上一" in prefix:
            continue
        return _parse_cn_date(m.group("s")), _parse_cn_date(m.group("e"))

    return candidates[0]


def _period_tag_for(filepath: str, period: tuple[date, date] | None) -> str | None:
    if period is not None:
        start, _end = period
        return f"credit-ccb-{start.year:04d}-{start.month:02d}"

    name = Path(filepath).name
    m = re.search(r"-(\d{4})-(\d{2})\.eml$", name)
    if m:
        return f"credit-ccb-{int(m.group(1)):04d}-{int(m.group(2)):02d}"
    return None


def iter_html_parts(msg: EmailMessage) -> Iterable[str]:
    for part in msg.walk():
        if part.get_content_type() == "text/html":
            content = part.get_content()
            if isinstance(content, bytes):
                yield content.decode(
                    part.get_content_charset() or "utf-8", errors="replace"
                )
            else:
                yield content


class CCBCreditEmlImporter(Importer):
    account_name: str
    currency: str = "CNY"

    def __init__(self, account_name: str) -> None:
        super().__init__()
        self.account_name = account_name

    def account(self, filepath: str) -> data.Account:
        return self.account_name

    def identify(self, filepath: str) -> bool:
        p = Path(filepath)
        return p.suffix.lower() == ".eml" and "中国建设银行信用卡" in p.name

    def extract(self, filepath: str, existing: data.Entries) -> data.Entries:
        with open(filepath, "rb") as f:
            msg: EmailMessage = parser.BytesParser(policy=policy.default).parse(fp=f)

        subject = msg.get("Subject", "")
        if "中国建设银行信用卡" not in subject:
            raise ValueError("Not a CCB credit card email")

        html_parts = list(iter_html_parts(msg))
        if not html_parts:
            raise ValueError("No HTML part found in email")

        soup = BeautifulSoup("\n".join(html_parts), "html.parser")

        text = soup.get_text(" ", strip=True)
        period = _extract_billing_period(text)
        period_tag = _period_tag_for(filepath, period)

        table = soup.find(
            lambda a: (
                a.name == "table"
                and "【交易明细】" in a.get_text()
                and a.find("table") is None
            )
        )
        if table is None:
            raise ValueError("Cannot locate transaction table in email")

        records = self._parse_records(table)
        entries: list[data.Directive] = []

        for index, record in enumerate(records):
            row_data = {
                "trade_date": record.trade_date.isoformat(),
                "description": record.description,
                "currency": record.currency,
                "amount": str(record.amount),
            }
            meta = data.new_metadata(filepath, index, kvlist={"row": row_data})
            amount = -Amount(D(record.amount), record.currency)

            tags = data.EMPTY_SET
            if period_tag:
                tags = frozenset({period_tag})

            txn = make_transaction(
                meta,
                record.trade_date,
                flags.FLAG_OKAY,
                record.description,
                None,
                tags,
                data.EMPTY_SET,
                [make_posting(self.account_name, amount)],
            )
            entries.append(txn)

        return entries

    def _parse_records(self, table: Tag) -> list[Record]:
        rows = table.find_all(lambda a: a.name == "tr" and len(a.select("td")) == 8)
        records: list[Record] = []

        for row in rows:
            tds = row.select("td")
            trade_date = parse_date(tds[0].get_text(strip=True))
            description = tds[3].get_text(strip=True)
            currency = tds[6].get_text(strip=True) or self.currency
            amount_raw = tds[7].get_text(strip=True)

            records.append(
                Record(
                    trade_date=trade_date,
                    description=description,
                    currency=currency,
                    amount=parse_amount(amount_raw),
                )
            )

        return records
