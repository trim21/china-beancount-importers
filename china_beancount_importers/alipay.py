import csv
import datetime
import fnmatch
import zoneinfo
from pathlib import Path

from beancount.core import data, flags
from beancount.core.amount import Amount
from beancount.core.number import D
from beangulp.importer import Importer

from .utils import make_posting, make_transaction

_START = "-------收支明细列表-----"

_COMMENTS_STR = "收款方备注:二维码收款付款方留言:"

tz = zoneinfo.ZoneInfo("Asia/Shanghai")


def parse_time(s: str) -> datetime.datetime:
    """parse date time from string '2023-08-30 20:46:41'"""
    return datetime.datetime.strptime(s, "%Y-%m-%d %H:%M:%S").astimezone(tz)


class AlipayImporter(Importer):
    """An importer for Alipay CSV files."""

    def __init__(
        self,
        account: str,
    ) -> None:
        self._account = account
        self.default_set = frozenset({"alipay"})
        self.currency = "CNY"

    def account(self, filepath: str = "") -> str:
        return self._account

    def identify(self, filepath: str) -> bool:
        fn = Path(filepath).name
        return fnmatch.fnmatch(fn, "*_ACCLOG.csv")

    def extract(self, filepath: str, existing: data.Entries) -> data.Entries:
        entries: data.Entries = []

        lines: list[str] = []
        with open(filepath, encoding="gb18030") as f:
            start = False
            for line in f:
                if _START in line:
                    start = True
                    continue
                if start:
                    lines.append(line)

        reader = csv.DictReader(lines)
        rows = list(reader)
        day_balance: dict[datetime.date, str] = {}

        for i, row in enumerate(rows):
            flag = flags.FLAG_WARNING
            dt = parse_time(row["时间"])
            account_1_text = row["资金渠道"]
            row_data = dict(row)
            meta = data.new_metadata(
                filepath,
                i,
                kvlist={
                    "time": str(dt.time()),
                    "funding_channel": account_1_text,
                    "row": row_data,
                },
            )
            amount = Amount(D(row["支出"] or row["收入"]), self.currency)
            payee: str = row.get("商品说明") or row["备注"] or row["名称"]
            payee = payee.removeprefix(_COMMENTS_STR)
            if payee == "/":
                payee = ""
            account_1 = self._account
            flag = flags.FLAG_OKAY

            postings = [make_posting(account_1, amount)]

            balance_raw = row.get("账户余额（元）", "").replace(",", "").strip()
            if (
                balance_raw
                and dt.date() not in day_balance
                and account_1 == self._account
            ):
                day_balance[dt.date()] = balance_raw
                entries.append(
                    data.Balance(
                        meta=data.new_metadata(filepath, i, kvlist={"row": row_data}),
                        date=dt.date() + datetime.timedelta(days=1),
                        account=account_1,
                        amount=Amount(D(balance_raw), self.currency),
                        tolerance=None,
                        diff_amount=None,
                    )
                )

            txn = make_transaction(
                meta,
                dt.date(),
                flag,
                payee,
                None,
                self.default_set,
                data.EMPTY_SET,
                postings,
            )
            entries.append(txn)
        return entries
