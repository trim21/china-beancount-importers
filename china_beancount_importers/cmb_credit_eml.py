import datetime
import re
from email import parser, policy
from email.message import Message
from os import path

from beancount.core import data, flags
from beancount.core.amount import Amount
from beancount.core.number import D
from beangulp.importer import Importer
from bs4 import BeautifulSoup
from dateutil.parser import parse as dateparse

from .utils import cast_checked, make_posting, make_transaction


class CmbEmlImporter(Importer):
    """An importer for CMB .eml files."""

    def __init__(self, account_name: str) -> None:
        self.account_name: str = account_name
        self.currency = "CNY"

    def identify(self, filepath: str) -> bool:
        filename = path.basename(filepath)
        return "招商银行信用卡电子账单" in filename and "eml" in filename

    def account(self, filepath: str) -> data.Account:
        return self.account_name

    def extract(self, filepath: str, existing: data.Entries) -> data.Entries:
        entries: data.Entries = []
        index = 0

        with open(filepath, "rb") as f:
            eml = parser.BytesParser(policy=policy.default).parse(fp=f)

        b = cast_checked(
            bytes,
            cast_checked(Message, cast_checked(list, eml.get_payload())[0]).get_payload(
                decode=True
            ),
        ).decode("utf-8")

        d = BeautifulSoup(b, "lxml")
        date_range = cast_checked(
            str,
            d.find(
                string=re.compile(r"\d{4}\/\d{1,2}\/\d{1,2}-\d{4}\/\d{1,2}\/\d{1,2}")
            ),
        )

        transaction_date = dateparse(date_range.split("-")[1].split("(")[0]).date()

        bands = d.select("#fixBand29 #loopBand2>table>tbody>tr")
        for band in bands:
            tds = band.select("td #fixBand15 table table td")
            if len(tds) == 0:
                continue

            full_descriptions = tds[3].text.strip().split("-")
            payee = full_descriptions[0]

            trade_date = tds[1].text.strip()
            if trade_date == "" or payee == "消费分期":
                trade_date = tds[2].text.strip()

            date = datetime.datetime.strptime(
                str(transaction_date.year) + trade_date, "%Y%m%d"
            ).date()

            narration = "-".join(full_descriptions[1:])
            real_currency = "CNY"
            real_price = (
                tds[4]
                .text.replace("￥", "")
                .replace("\xa0", "")
                .replace("¥", "")
                .strip()
            )

            amount = -Amount(D(real_price), real_currency)
            row_data = {
                "trade_date_raw": trade_date,
                "transaction_date": transaction_date.isoformat(),
                "date": date.isoformat(),
                "payee": payee,
                "narration": narration,
                "currency": real_currency,
                "amount": real_price,
            }
            meta = data.new_metadata(filepath, index, kvlist={"row": row_data})
            txn = make_transaction(
                meta,
                date,
                flags.FLAG_OKAY,
                payee,
                narration,
                data.EMPTY_SET,
                data.EMPTY_SET,
                [make_posting(self.account_name, amount)],
            )

            entries.append(txn)

        return entries
