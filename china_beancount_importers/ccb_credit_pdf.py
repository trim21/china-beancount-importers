import dataclasses
import datetime
import decimal
import re
import sys
from datetime import date
from fnmatch import fnmatch
from pathlib import Path

import pdfplumber
from beancount import Amount
from beancount.core import data
from beangulp import extract
from beangulp.importer import Importer

from .utils import make_posting, make_transaction

DATE_TOKEN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Record:
    trade_date: date
    booking_date: date
    card_last4: str
    description: str
    trans_currency: str
    trans_amount: decimal.Decimal
    settlement_currency: str
    settlement_amount: decimal.Decimal
    raw_line: str


def _parse_amount_token(raw: str) -> decimal.Decimal:
    cleaned = raw.replace(",", "").strip()
    if cleaned.startswith("(") and cleaned.endswith(")"):
        return -decimal.Decimal(cleaned[1:-1])
    return decimal.Decimal(cleaned)


class CCBCreditPdfImporter(Importer):
    def __init__(
        self,
        account: str,
        currency: str = "CNY",
        *,
        currency_map: dict[str, str] | None = None,
    ) -> None:
        self._account: str = account
        self._currency: str = currency
        self._currency_map: dict[str, str] = currency_map or {"CNY": "CNY"}

    def account(self, filepath: str) -> data.Account:
        return self._account

    def identify(self, filepath: str) -> bool:
        p = Path(filepath)
        print(p.name, file=sys.stderr)
        return fnmatch(p.name, "ccb-credit-*.pdf")

    def deduplicate(self, entries: data.Entries, existing: data.Entries) -> None:
        window = datetime.timedelta(days=0)
        extract.mark_duplicate_entries(
            [entry for entry in entries if isinstance(entry, data.Transaction)],
            existing,
            window,
            self.cmp,
        )

    def _is_header_line(self, text: str) -> bool:
        return "交易日 银行记账日 卡号后四位 交易描述 交易币/金额 结算币/金额" in text

    def _should_stop(self, text: str) -> bool:
        return text.startswith("*** 结束")

    def _should_skip(self, text: str) -> bool:
        return (
            text == "承前页"
            or "接下页" in text
            or text.startswith("T-Date P-Date")
            or text.startswith("[人民币账户]")
            or "上期账单余额" in text
        )

    def _parse_record_line(self, text: str) -> Record | None:
        tokens = text.split()
        if len(tokens) < 7:
            return None

        first, second, last4 = tokens[0], tokens[1], tokens[2]
        if not (DATE_TOKEN.match(first) and DATE_TOKEN.match(second)):
            return None

        trade_date = date.fromisoformat(first)
        booking_date = date.fromisoformat(second)

        if len(last4) != 4:
            return None

        if len(tokens) < 8:
            raise ValueError(f"unexpected transaction line: {text!r}")

        trans_currency, trans_amount = tokens[-4], tokens[-3]
        settlement_currency, settlement_amount = tokens[-2], tokens[-1]
        description = " ".join(tokens[3:-4]).strip()

        if not description:
            raise ValueError(f"empty description in transaction line: {text!r}")

        return Record(
            trade_date=trade_date,
            booking_date=booking_date,
            card_last4=last4,
            description=description,
            trans_currency=trans_currency,
            trans_amount=_parse_amount_token(trans_amount),
            settlement_currency=settlement_currency,
            settlement_amount=_parse_amount_token(settlement_amount),
            raw_line=text,
        )

    def _extract_records(self, lines: list[str]) -> list[Record]:
        records: list[Record] = []
        in_table = False

        for text in lines:
            if not in_table and self._is_header_line(text):
                in_table = True
                continue

            if not in_table:
                continue

            if self._should_stop(text):
                break

            if self._should_skip(text):
                continue

            record = self._parse_record_line(text)
            if record is None:
                continue
            records.append(record)

        return records

    def extract(self, filepath: str, existing: data.Entries) -> data.Entries:
        results: list[data.Directive] = []

        lines: list[str] = []
        with pdfplumber.open(filepath) as pdf:
            filename = Path(filepath).name
            match = re.search(r"(\d{4})(\d{2})\.pdf$", filename)
            if match is None:
                raise ValueError(f"cannot infer year-month from filepath: {filepath!r}")
            year, month = match.groups()
            period_tag = f"credit-ccb-{int(year):04d}-{int(month):02d}"
            for page in pdf.pages:
                for line in page.extract_text_lines():
                    text = (line.get("text") or "").strip()
                    if text:
                        lines.append(text)

        records = self._extract_records(lines)

        for i, record in enumerate(records):
            row_data = {
                "交易日": record.trade_date.isoformat(),
                "银行记账日": record.booking_date.isoformat(),
                "卡号后四位": record.card_last4,
                "交易描述": record.description,
                "交易币/金额": f"{record.trans_currency}/{record.trans_amount}",
                "结算币/金额": (
                    f"{record.settlement_currency}/{record.settlement_amount}"
                ),
            }
            meta = data.new_metadata(
                filepath,
                i,
                kvlist={
                    "booking_date": record.booking_date.isoformat(),
                    "trans_currency": record.trans_currency,
                    "trans_amount": str(record.trans_amount),
                    "raw": record.raw_line,
                    "row": row_data,
                },
            )

            currency = self._currency_map.get(record.settlement_currency)
            if currency is None:
                known = ", ".join(sorted(self._currency_map))
                raise ValueError(
                    f"currency '{record.settlement_currency}' not in currency_map; known: {known}"
                )

            amount = -record.settlement_amount

            account = self._account

            postings = [
                make_posting(
                    account=account,
                    units=Amount(amount, currency),
                )
            ]

            tags = frozenset({period_tag})

            results.append(
                make_transaction(
                    meta,
                    record.trade_date,
                    "*",
                    record.description,
                    None,
                    tags,
                    data.EMPTY_SET,
                    postings,
                )
            )

        return results
