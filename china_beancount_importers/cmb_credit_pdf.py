import dataclasses
import datetime
import decimal
import re
from datetime import date
from pathlib import Path
from typing import Any

import pdfplumber
from beancount import Amount
from beancount.core import data
from beangulp import extract
from beangulp.importer import Importer
from sslog import logger

from .utils import make_posting, make_transaction

DATE_TOKEN = re.compile(r"^\d{2}/\d{2}$")
AMOUNT_TOKEN = re.compile(r"^\(?[+-]?\d[\d,]*(?:\.\d+)?\)?$")
AMOUNT_TOKEN_WITH_CURRENCY = re.compile(
    r"^\(?[+-]?\d[\d,]*(?:\.\d+)?\)?(?:\([A-Za-z]{2,4}\))?$"
)
LAST4_TOKEN = re.compile(r"^\d{4}$")
SECTION_MARKERS = {"消费", "分期", "退款", "还款"}
NON_TXN_PATTERNS = [
    re.compile(r"招商银行信用卡对账单（个人消费卡账户 \d{4}年\d{2}月）"),
    re.compile(r"CMB Credit Card Statement \(\d{4}\.\d{2}\)"),
    re.compile(r"人民币账户 RMB A/C"),
    re.compile(r"本期账务明细 Transaction Details"),
    re.compile(r"Trans Post Card Number Original Trans"),
    re.compile(r"Date Date \(last 4 digits\) Amount"),
    re.compile(r"Description RMB Amount"),
    re.compile(
        r"SOLD POSTED DESCRIPTION RMB AMOUNT CARD NO\(Last 4digits\) Original Tran Amount"
    ),
]


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Row:
    trade_date: date
    booking_date: date
    summary: str
    amount: str
    last_4: str
    amount_in_location: str
    section: str | None = None
    trade_date_raw: str = ""
    booking_date_raw: str = ""
    raw_line: str = ""


def parse_date(s: Any) -> Any:
    if isinstance(s, str):
        dt = int(s)
        return date(year=dt // 10000, month=(dt // 100) % 100, day=dt % 100)
    return s


def normalize_currency(raw: str, mapping: dict[str, str]) -> str:
    head = raw.split("/", 1)[0].strip()
    if head not in mapping:
        known = ", ".join(sorted(mapping))
        raise ValueError(f"currency '{head}' not in currency_map; known: {known}")
    return mapping[head]


def extract_amount(raw: str) -> decimal.Decimal:
    """parse '人民币元/32.50'"""
    cleaned = raw.split("/")[-1].replace(",", "").strip()
    match = re.search(r"[-+]?\d+(?:\.\d+)?", cleaned)
    if match is None:
        raise ValueError(f"cannot parse amount from {raw!r}")
    amount = decimal.Decimal(match.group())
    if cleaned.startswith("(") and cleaned.endswith(")"):
        amount = -amount
    return amount


def parse_mmdd(s: str, *, year: int, default_month: int) -> date:
    s = s.strip()
    if not s:
        raise ValueError("empty date string")
    if "/" in s:
        m_str, d_str = s.split("/", 1)
        m = int(m_str)
        d = int(d_str)
        y = year - 1 if m > default_month else year
        return date(year=y, month=m, day=d)

    raise ValueError(f"unexpected date format {s!r}")


class CMBCreditPdfImporter(Importer):
    def __init__(
        self,
        account: str,
        currency: str = "CNY",
        *,
        currency_map: dict[str, str] | None = None,
    ) -> None:
        self._account: str = account
        self._currency: str = currency
        self._currency_map: dict[str, str] = currency_map or {"人民币元": "CNY"}

    def account(self, filepath: str) -> data.Account:
        return self._account

    def identify(self, filepath: str) -> bool:
        fn = Path(filepath).name
        return fn.startswith("CreditCardReckoning") and fn.lower().endswith(".pdf")

    def deduplicate(self, entries: data.Entries, existing: data.Entries) -> None:
        window = datetime.timedelta(days=0)
        extract.mark_duplicate_entries(
            [entry for entry in entries if isinstance(entry, data.Transaction)],
            existing,
            window,
            self.cmp,
        )

    def _is_non_txn_line(self, text: str) -> bool:
        return any(pattern.match(text) for pattern in NON_TXN_PATTERNS)

    def _parse_rows(
        self,
        lines: list[str],
        *,
        year: int,
        month: int,
    ) -> list[Row]:
        rows: list[Row] = []
        in_table = False
        current_section: str | None = None

        for text in lines:
            if not text:
                continue

            if not in_table:
                if "交易日 记账日 交易摘要" in text:
                    in_table = True
                continue

            if (
                text.startswith("本期还款总额")
                or text.startswith("本期应还金额")
                or "Current Balance" in text
                or "New Balance" in text
            ):
                break

            if text == "交易日 记账日 交易摘要 人民币金额 卡号末四位 交易地金额":
                continue

            if self._is_non_txn_line(text):
                continue

            if text in SECTION_MARKERS:
                current_section = text
                continue

            tokens = text.split()
            if not tokens or not DATE_TOKEN.match(tokens[0]):
                raise ValueError(f"unexpected line in transaction table: {text!r}")

            if len(tokens) < 5:
                raise ValueError(f"too few tokens in transaction line: {text!r}")

            trade_s = tokens[0]
            idx = 1

            if idx < len(tokens) and DATE_TOKEN.match(tokens[idx]):
                book_s = tokens[idx]
                idx += 1
            else:
                book_s = trade_s

            if len(tokens) - idx < 3:
                raise ValueError(
                    f"too few trailing tokens in transaction line: {text!r}"
                )

            amount_s = tokens[-3]
            last4 = tokens[-2]
            amount_in_location = tokens[-1]
            summary_tokens = tokens[idx:-3]
            summary = " ".join(summary_tokens).strip()

            if not summary:
                raise ValueError(f"empty summary in transaction line: {text!r}")
            if not AMOUNT_TOKEN.match(amount_s):
                raise ValueError(f"invalid amount in transaction line: {text!r}")
            if not AMOUNT_TOKEN_WITH_CURRENCY.match(amount_in_location):
                raise ValueError(
                    f"invalid original amount in transaction line: {text!r}"
                )
            if not LAST4_TOKEN.match(last4):
                raise ValueError(f"invalid card last4 in transaction line: {text!r}")

            trade_date = parse_mmdd(trade_s, year=year, default_month=month)
            booking_date = parse_mmdd(book_s, year=year, default_month=month)

            rows.append(
                Row(
                    trade_date=trade_date,
                    booking_date=booking_date,
                    summary=summary,
                    amount=amount_s,
                    last_4=last4.strip(),
                    amount_in_location=amount_in_location,
                    section=current_section,
                    trade_date_raw=trade_s,
                    booking_date_raw=book_s,
                    raw_line=text,
                )
            )

        return rows

    def extract(self, filepath: str, existing: data.Entries) -> data.Entries:
        match = re.search(r".*(\d{4})-(\d{2}).*.pdf", filepath)
        if match is None:
            raise ValueError(f"cannot infer year-month from filepath: {filepath!r}")
        s_year, s_month = match.groups()
        year = int(s_year)
        month = int(s_month.removeprefix("0"))
        period_tag = f"credit-cmb-{year:04d}-{month:02d}"

        results: list[data.Directive] = []

        lines: list[str] = []
        with pdfplumber.open(filepath) as pdf:
            for page in pdf.pages:
                for line in page.extract_text_lines():
                    text = (line.get("text") or "").strip()
                    if text:
                        lines.append(text)

        parsed_rows = self._parse_rows(lines, year=year, month=month)

        if not parsed_rows:
            logger.warning("no transaction rows parsed from {}", filepath)

        for i, row in enumerate(parsed_rows):
            row_data = {
                "trade_date": row.trade_date.isoformat(),
                "booking_date": row.booking_date.isoformat(),
                "summary": row.summary,
                "amount": row.amount,
                "last_4": row.last_4,
                "amount_in_location": row.amount_in_location,
                "section": row.section,
                "trade_date_raw": row.trade_date_raw,
                "booking_date_raw": row.booking_date_raw,
                "raw_line": row.raw_line,
            }
            kvlist: dict[str, Any] = {
                "booking_date": row.booking_date.isoformat(),
                "trade_date": row.trade_date.isoformat(),
                "trade_date_raw": row.trade_date_raw,
                "raw_line": row.raw_line,
                "section": row.section,
                "row": row_data,
            }

            meta = data.new_metadata(filepath, i, kvlist=kvlist)

            amount = -extract_amount(row.amount)
            currency = "CNY"

            account = self._account

            trade_date_for_txn = row.trade_date
            if row.section == "分期":
                trade_date_for_txn = row.booking_date

            postings = [
                make_posting(
                    account=account,
                    units=Amount(amount, currency),
                )
            ]

            tags = frozenset({period_tag})
            flag = "*"
            if row.section == "分期":
                tags = tags | frozenset({"installment"})
                flag = "!"

            results.append(
                make_transaction(
                    meta,
                    trade_date_for_txn,
                    flag,
                    row.summary,
                    None,
                    tags,
                    data.EMPTY_SET,
                    postings,
                )
            )

        return results
