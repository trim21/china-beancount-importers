"""Importer for 微信."""

from __future__ import annotations

import csv
import datetime
import re
from pathlib import Path

import pandas as pd
from beancount.core import data, flags
from beancount.core.amount import Amount
from beancount.core.number import D
from beangulp import Importer

from .utils import make_posting, make_transaction

_COMMENTS_STR = "收款方备注:二维码收款付款方留言:"
_CSV_NAME_RE = re.compile(r"微信支付账单\(\d{8}-\d{8}\)\.csv")
_XLSX_NAME_RE = re.compile(r"微信支付账单流水文件\(\d+-\d+\)_\d+\.xlsx")


def parse_time(s: str) -> datetime.datetime:
    """parse date time from string '2023-08-30 20:46:41'"""
    return datetime.datetime.strptime(s, "%Y-%m-%d %H:%M:%S").astimezone()


def _read_csv_rows(filepath: str) -> list[dict[str, str]]:
    with open(filepath, encoding="utf-8") as f:
        for _ in range(16):
            next(f, None)
        return list(csv.DictReader(f))


def _read_xlsx_rows(filepath: str) -> list[dict[str, str]]:
    df = pd.read_excel(filepath, dtype=str).fillna("")
    header: list[str] = df.values[15]
    rows: list[dict[str, str]] = []
    for line in df.values[16:]:
        rows.append({key: value for key, value in zip(header, line, strict=True)})
    return rows


class WechatImporter(Importer):
    """An importer for Wechat CSV/XLSX files."""

    def __init__(
        self,
        account: str,
    ) -> None:
        """
        :param account: 微信零钱账户
        """
        self._account = account
        self.default_set = frozenset({"wechat"})
        self.currency = "CNY"

    def account(self, filepath: str = "") -> str:
        return self._account

    def identify(self, filepath: str) -> bool:
        name = Path(filepath).name
        return bool(_CSV_NAME_RE.match(name) or _XLSX_NAME_RE.match(name))

    def extract(
        self, filepath: str, existing_entries: data.Entries | None = None
    ) -> list[data.Transaction]:
        entries: list[data.Transaction] = []
        suffix = Path(filepath).suffix.lower()
        if suffix in {".xlsx", ".xls"}:
            rows = _read_xlsx_rows(filepath)
        else:
            rows = _read_csv_rows(filepath)

        for index, row in enumerate(reversed(rows)):
            flag = flags.FLAG_WARNING
            dt = parse_time(row["交易时间"])
            account_1_text = row["支付方式"]
            row_data = dict(row)
            meta = data.new_metadata(
                filepath,
                index,
                kvlist={
                    "time": str(dt.time()),
                    "payment_method": account_1_text,
                    "row": row_data,
                },
            )
            amount = Amount(D(row["金额(元)"].lstrip("¥")), self.currency)
            if row["收/支"] in {"支出", "/"}:
                amount = -amount
            payee: str | None = row["交易对方"]
            narration: str = row["商品"]
            if narration.startswith(_COMMENTS_STR):
                narration = narration.replace(_COMMENTS_STR, "")
            if narration == "/":
                narration = ""
            account_1 = self._account
            flag = flags.FLAG_OKAY

            postings = [make_posting(account_1, amount)]

            if row["当前状态"] == "充值完成":
                postings.insert(
                    0,
                    make_posting(self._account, -amount),
                )
                narration = "微信零钱充值"
                payee = None
            txn = make_transaction(
                meta,
                dt.date(),
                flag,
                payee,
                narration,
                data.EMPTY_SET,
                data.EMPTY_SET,
                postings,
            )
            entries.append(txn)
        return entries
