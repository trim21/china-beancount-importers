"""Importer for 微信"""

from __future__ import annotations

import csv
import datetime
import re
from os import path
from typing import Dict

from beancount.core import data, flags
from beancount.core.amount import Amount
from beancount.core.number import D
from beangulp import Importer

_COMMENTS_STR = "收款方备注:二维码收款付款方留言:"


def parse_time(s: str) -> datetime.datetime:
    """parse date time from string '2020.9.6 16:59'"""
    return datetime.datetime.strptime(s, "%Y.%m.%d %H:%M").astimezone()


class WechatImporter(Importer):
    """An importer for Wechat CSV files."""

    def __init__(
        self,
        account: str = "Assets:WeChat",
        account_dict: Dict | None = None,
    ):
        """

        :param account: 微信零钱账户
        :param account_dict: 支付方式和beancount账户的对应
        """
        self._account = account
        self.accountDict = account_dict or {}
        self.accountDict.update(
            {
                "零钱": self._account,
                "/": self._account,
            }
        )
        self.default_set = frozenset({"wechat"})
        self.currency = "CNY"

    def account(self, filepath: str = "") -> str:
        return self._account

    def identify(self, file):
        # Match if the filename is as downloaded and the header has the unique
        # fields combination we're looking for.
        return re.match(r"微信支付账单\(\d{8}-\d{8}\).csv", path.basename(file.name))

    def file_name(self, file):
        return "wechat.{}".format(path.basename(file.name))

    def file_date(self, file):
        # Extract the statement date from the filename.
        return datetime.datetime.strptime(
            path.basename(file.name).split("-")[-1], "%Y%m%d).csv"
        ).date()

    def extract(self, filepath: str, existing_entries=None) -> list[data.Transaction]:
        # Open the CSV file and create directives.
        entries: list[data.Transaction] = []
        with open(filepath, encoding="utf-8") as f:
            for _ in range(16):
                next(f)
            for index, row in enumerate(reversed(list(csv.DictReader(f)))):
                flag = flags.FLAG_WARNING
                dt = parse_time(row["交易时间"])
                meta = data.new_metadata(
                    filepath, index, kvlist={"time": str(dt.time())}
                )
                amount = Amount(D(row["金额(元)"].lstrip("¥")), self.currency)
                if row["收/支"] in {"支出", "/"}:
                    # 支出
                    amount = -amount
                payee = row["交易对方"]
                narration: str = row["商品"]
                if narration.startswith(_COMMENTS_STR):
                    narration = narration.replace(_COMMENTS_STR, "")
                if narration == "/":
                    narration = ""
                account_1_text = row["支付方式"]
                account_1 = "Assets:FIXME"
                for asset_k, asset_v in self.accountDict.items():
                    if asset_k in account_1_text:
                        account_1 = asset_v
                        flag = flags.FLAG_OKAY

                postings = [data.Posting(account_1, amount, None, None, None, None)]

                if row["当前状态"] == "充值完成":
                    postings.insert(
                        0,
                        data.Posting(self._account, -amount, None, None, None, None),
                    )
                    narration = "微信零钱充值"
                    payee = None
                txn = data.Transaction(
                    meta,
                    dt.date(),
                    flag,
                    payee,
                    narration,
                    self.default_set,
                    data.EMPTY_SET,
                    postings,
                )
                entries.append(txn)
        return entries
