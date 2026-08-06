import csv
import dataclasses
import datetime
from decimal import Decimal
from pathlib import Path
from typing import Annotated

import pydantic
from beancount import Amount
from beancount.core import data
from beangulp.importer import Importer

from .utils import make_posting, make_transaction


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Row:
    booking_date: Annotated[str, pydantic.Field(alias="记账日")]
    tx_date: Annotated[str, pydantic.Field(alias="交易日期")]
    tx_time: Annotated[str, pydantic.Field(alias="交易时间")]
    expense: Annotated[str, pydantic.Field(alias="支出")]
    income: Annotated[str, pydantic.Field(alias="收入")]
    balance: Annotated[str, pydantic.Field(alias="账户余额")]
    currency: Annotated[str, pydantic.Field(alias="币种")]
    summary: Annotated[str, pydantic.Field(alias="摘要")]
    counterpart_account: Annotated[str, pydantic.Field(alias="对方账号")]
    counterpart_name: Annotated[str, pydantic.Field(alias="对方户名")]
    location: Annotated[str, pydantic.Field(alias="交易地点")]

    def parsed_date(self) -> datetime.date:
        s = self.tx_date
        return datetime.date(int(s[:4]), int(s[4:6]), int(s[6:8]))


decoder = pydantic.TypeAdapter(Row)


class CCBDebitTxtImporter(Importer):
    """Importer for CCB debit card txt exports (交易明细_*.txt).

    The file starts with 3 metadata header lines (the account number is
    extracted from one of them, e.g. "账　　号：622280*********3864"),
    followed by the column header row and csv rows.
    """

    def __init__(self, account_map: dict[str, str], *, currency: str = "CNY") -> None:
        self._account_map: dict[str, str] = account_map
        self._currency: str = currency

    def account(self, filepath: str) -> data.Account:
        suffix = self._account_suffix(Path(filepath))
        if suffix is not None and suffix in self._account_map:
            return self._account_map[suffix]
        return ""

    def identify(self, filepath: str) -> bool:
        path = Path(filepath)
        if path.suffix.lower() != ".txt":
            return False
        if not path.name.startswith("交易明细_"):
            return False

        try:
            with open(path, encoding="utf-8") as f:
                lines = [f.readline() for _ in range(4)]
        except OSError:
            return False

        # Line 4 should be the column header row containing "记账日"
        if "记账日" not in lines[3]:
            return False
        suffix = self._extract_suffix_from_header(lines)
        return suffix is not None and suffix in self._account_map

    def extract(self, filepath: str, existing: data.Entries) -> data.Entries:
        path = Path(filepath)
        with open(path, encoding="utf-8") as f:
            # Skip 3 metadata header lines
            header_lines = [f.readline() for _ in range(3)]
            reader = csv.DictReader(f)
            rows = list(reader)

        suffix = self._extract_suffix_from_header(header_lines)
        if suffix is None:
            raise ValueError(f"cannot extract account suffix from {filepath!r}")
        if suffix not in self._account_map:
            raise ValueError(f"account suffix {suffix!r} not in account_map")
        account = self._account_map[suffix]

        parsed = [decoder.validate_python(row) for row in rows]

        results: list[data.Directive] = []

        for lineno, row in enumerate(parsed, start=5):
            expense = self._parse_decimal(row.expense) if row.expense else Decimal(0)
            income = self._parse_decimal(row.income) if row.income else Decimal(0)

            if income > 0:
                amt = income
            else:
                amt = -expense

            narration = row.location if row.location else row.summary

            meta = data.new_metadata(filepath, lineno)
            if row.tx_time:
                meta["time"] = row.tx_time
            meta["raw_summary"] = row.summary

            postings = [
                make_posting(
                    account=account,
                    units=Amount(amt, self._currency),
                )
            ]

            results.append(
                make_transaction(
                    meta,
                    row.parsed_date(),
                    payee=row.counterpart_name or None,
                    narration=narration,
                    postings=postings,
                )
            )

        # Emit a balance assertion dated the day after the last transaction
        last = parsed[-1]
        balance_date = last.parsed_date() + datetime.timedelta(days=1)
        balance_val = self._parse_decimal(last.balance)

        balance_meta = data.new_metadata(filepath, len(parsed) + 5)
        results.append(
            data.Balance(
                meta=balance_meta,
                date=balance_date,
                account=account,
                amount=Amount(balance_val, self._currency),
                tolerance=None,
                diff_amount=None,
            )
        )

        return results

    @staticmethod
    def _extract_suffix_from_header(lines: list[str]) -> str | None:
        """Extract the last 4 digits of the account number from the header."""
        for line in lines:
            if "账" in line and "号" in line:
                # e.g. "账　　号：622280*********3864"
                parts = line.split("：", 1)
                if len(parts) == 2:
                    account_num = parts[1].strip()
                    if len(account_num) >= 4:
                        return account_num[-4:]
        return None

    @staticmethod
    def _account_suffix(path: Path) -> str | None:
        try:
            with open(path, encoding="utf-8") as f:
                lines = [f.readline() for _ in range(4)]
            return CCBDebitTxtImporter._extract_suffix_from_header(lines)
        except OSError:
            return None

    @staticmethod
    def _parse_decimal(value: str) -> Decimal:
        raw = value.strip().replace(",", "")
        return Decimal(raw)
