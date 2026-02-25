import csv
import dataclasses
import datetime
import decimal
import fnmatch
import io
from pathlib import Path
from typing import Annotated

import pydantic
import regex
from beancount import Amount
from beancount.core import data
from beangulp import extract
from beangulp.importer import Importer

from .utils import make_posting, make_transaction


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Row:
    date: Annotated[str, pydantic.Field(alias="交易日期")]
    time: Annotated[str, pydantic.Field(alias="交易时间")]
    income: Annotated[str, pydantic.Field(alias="收入")]
    outcome: Annotated[str, pydantic.Field(alias="支出")]
    balance: Annotated[str, pydantic.Field(alias="余额")]
    typ: Annotated[str, pydantic.Field(alias="交易类型")]
    description: Annotated[str, pydantic.Field(alias="交易备注")]


decoder = pydantic.TypeAdapter(Row)
_pattern = regex.compile(r"账\s+号: \[一卡通:\d{4}\*\*\*\*\*\*\*\*(\d{4})")


def _parse_cmb_debit_last4_from_header(header_lines: list[str]) -> str:
    for line in header_lines:
        m = _pattern.search(line)
        if m is not None:
            return m.group(1)

    header_preview = "".join(header_lines[:7])
    raise ValueError(
        f"cannot parse card last4 from CMB debit header: {header_preview!r}"
    )


def _resolve_account_from_last4(account_map: dict[str, str], last4: str) -> str:
    if last4 not in account_map:
        known = ", ".join(sorted(account_map))
        raise KeyError(f"card last4 '{last4}' not in account_map; known: {known}")
    return account_map[last4]


class CMBDebitImporter(Importer):
    """
    从PC端的招商银行专业版导出
    """

    def __init__(self, account_map: dict[str, str], currency: str = "CNY") -> None:
        self._account_map: dict[str, str] = account_map
        self._currency: str = currency

    def account(self, filepath: str) -> data.Account:
        with open(filepath, encoding="utf-8-sig") as f:
            header_lines = [next(f, "") for _ in range(7)]

        last4 = _parse_cmb_debit_last4_from_header(header_lines)
        return _resolve_account_from_last4(self._account_map, last4)

    def identify(self, filepath: str) -> bool:
        p = Path(filepath)
        return fnmatch.fnmatch(p.name, "CMB_*.csv")

    def deduplicate(self, entries: data.Entries, existing: data.Entries) -> None:
        window = datetime.timedelta(days=0)
        extract.mark_duplicate_entries(
            [entry for entry in entries if isinstance(entry, data.Transaction)],
            existing,
            window,
            self.cmp,
        )

    def extract(self, filepath: str, existing: data.Entries) -> data.Entries:
        with open(filepath, encoding="utf-8-sig") as f:
            all_lines = f.readlines()

        header_lines = all_lines[:7]
        lines = all_lines[7:-3]

        last4 = _parse_cmb_debit_last4_from_header(header_lines)
        account = _resolve_account_from_last4(self._account_map, last4)

        day_balance: dict[datetime.date, str] = {}

        results: list[data.Directive] = []

        reader = csv.DictReader(io.StringIO("\n".join(lines)))

        for i, record in enumerate(reader):
            row_data = {key: value.strip() for key, value in record.items()}
            row = decoder.validate_python(row_data)

            meta = data.new_metadata(
                filepath,
                i,
                kvlist={"time": row.time, "card_last4": last4, "row": row_data},
            )

            date = datetime.date(
                year=int(row.date[:4]),
                month=int(row.date[4:6]),
                day=int(row.date[6:8]),
            )

            if row.income:
                amount = decimal.Decimal(row.income)
            else:
                amount = -decimal.Decimal(row.outcome)

            postings = [
                make_posting(
                    account=account,
                    units=Amount(number=amount, currency=self._currency),
                )
            ]

            if date not in day_balance:
                day_balance[date] = row.balance
                results.append(
                    data.Balance(
                        meta=data.new_metadata(
                            filepath, i, kvlist={"card_last4": last4, "row": row_data}
                        ),
                        date=date + datetime.timedelta(days=1),
                        account=account,
                        amount=Amount(decimal.Decimal(row.balance), "CNY"),
                        tolerance=None,
                        diff_amount=None,
                    )
                )

            results.append(
                make_transaction(
                    meta,
                    date,
                    "*",
                    row.description,
                    None,
                    data.EMPTY_SET,
                    data.EMPTY_SET,
                    postings,
                )
            )

        return list(reversed(results))


# Backward-compatible alias (original spelling)
CMBDebeit = CMBDebitImporter
