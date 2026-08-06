import datetime
import decimal
from pathlib import Path

import pandas as pd
from beancount import Amount
from beancount.core import data
from beangulp.importer import Importer

from .ccb_debit_txt import Row, decoder
from .utils import make_posting, make_transaction

# 建行借记卡 xls 与 txt 导出的列结构一致，共用 ccb_debit_txt.Row 做解析
_HEADER_ROW = 6  # 1-based; the 6th row holds the column headers
_COLUMNS = [
    "记账日",
    "交易日期",
    "交易时间",
    "支出",
    "收入",
    "账户余额",
    "币种",
    "摘要",
    "对方账号",
    "对方户名",
    "交易地点",
]


class CCBDebitXlsImporter(Importer):
    """Importer for CCB debit card xls exports (交易明细_*.xls)."""

    def __init__(self, account: str, currency: str = "CNY") -> None:
        self._account: str = account
        self._currency: str = currency

    def account(self, filepath: str) -> data.Account:
        return self._account

    def identify(self, filepath: str) -> bool:
        path = Path(filepath)
        if path.suffix.lower() != ".xls":
            return False
        if not path.name.startswith("交易明细_"):
            return False

        try:
            df = pd.read_excel(path, header=None, nrows=6, dtype=str)
            # Row 5 should contain the column headers
            row5 = df.iloc[5].tolist()
            return any("记账日" in str(v) for v in row5 if pd.notna(v))
        except Exception:  # noqa: BLE001 - any read failure means "not our file"
            return False

    def extract(self, filepath: str, existing: data.Entries) -> data.Entries:
        df = pd.read_excel(filepath, header=None, skiprows=_HEADER_ROW, dtype=str)
        df.columns = _COLUMNS

        # Drop footer rows
        df = df[df["记账日"].notna() & ~df["记账日"].str.contains("以上数据", na=False)]
        df = df.reset_index(drop=True)

        rows: list[Row] = [
            decoder.validate_python(
                {
                    col: "" if pd.isna(value) else str(value).strip()
                    for col, value in row.items()
                }
            )
            for _, row in df.iterrows()
        ]

        results: list[data.Directive] = []

        for lineno, row in enumerate(rows, start=_HEADER_ROW + 1):
            expense = (
                self._parse_decimal(row.expense) if row.expense else decimal.Decimal(0)
            )
            income = (
                self._parse_decimal(row.income) if row.income else decimal.Decimal(0)
            )

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
                    account=self._account,
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
        last = rows[-1]
        balance_date = last.parsed_date() + datetime.timedelta(days=1)
        balance_val = self._parse_decimal(last.balance)

        balance_meta = data.new_metadata(filepath, len(rows) + _HEADER_ROW + 1)
        results.append(
            data.Balance(
                meta=balance_meta,
                date=balance_date,
                account=self._account,
                amount=Amount(balance_val, self._currency),
                tolerance=None,
                diff_amount=None,
            )
        )

        return results

    @staticmethod
    def _parse_decimal(value: str) -> decimal.Decimal:
        raw = value.strip().replace(",", "")
        return decimal.Decimal(raw)
