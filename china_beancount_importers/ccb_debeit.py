import dataclasses
import datetime
import fnmatch
from decimal import Decimal
from pathlib import Path
from typing import Annotated

import pandas as pd
import pydantic
from beancount import Amount
from beancount.core import data
from beangulp import extract
from beangulp.importer import Importer

from .utils import make_posting, make_transaction


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Row:
    date: Annotated[str, pydantic.Field(alias="交易日期")]
    amount: Annotated[str, pydantic.Field(alias="交易金额")]
    summary: Annotated[str, pydantic.Field(alias="摘要")]
    balance: Annotated[str, pydantic.Field(alias="账户余额")]
    description: Annotated[str, pydantic.Field(alias="交易地点/附言")]
    posting: Annotated[str, pydantic.Field(alias="对方账号与户名")]


decoder = pydantic.TypeAdapter(Row)


class CCBDebeitImporter(Importer):
    def __init__(
        self,
        account: str,
        currency: str = "CNY",
    ) -> None:
        self._account: str = account
        self._currency: str = currency

    def account(self, filepath: str) -> data.Account:
        return self._account

    def identify(self, filepath: str) -> bool:
        p = Path(filepath)
        return fnmatch.fnmatch(p.name.lower(), "hqmx_*.xls")

    def deduplicate(self, entries: data.Entries, existing: data.Entries) -> None:
        window = datetime.timedelta(days=0)
        extract.mark_duplicate_entries(
            [entry for entry in entries if isinstance(entry, data.Transaction)],
            existing,
            window,
            self.cmp,
        )

    def extract(self, filepath: str, existing: data.Entries) -> data.Entries:
        account = self._account

        results: list[data.Directive] = []

        day_balance: dict[datetime.date, str] = {}

        df = pd.read_excel(filepath, dtype=str).fillna("")

        header: list[str] = df.values[2]
        rows: list[dict[str, str]] = [
            {key: value for key, value in zip(header, row, strict=True)}
            for row in df.values[3:]
        ]

        for i, item in reversed(list(enumerate(rows))):
            row_data = dict(item)
            row = decoder.validate_python(item)

            meta = data.new_metadata(filepath, i, kvlist={"row": row_data})

            amount = Amount(Decimal(row.amount.replace(",", "")), self._currency)

            date = datetime.date(
                year=int(row.date[:4]),
                month=int(row.date[4:6]),
                day=int(row.date[6:8]),
            )

            if date not in day_balance:
                day_balance[date] = row.balance
                results.append(
                    data.Balance(
                        meta=meta,
                        date=date + datetime.timedelta(days=1),
                        account=account,
                        amount=Amount(Decimal(row.balance.replace(",", "")), "CNY"),
                        tolerance=None,
                        diff_amount=None,
                    )
                )

            postings = [
                make_posting(account=account, units=amount),
            ]

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

        return results
