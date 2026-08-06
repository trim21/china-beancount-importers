import dataclasses
import datetime
import decimal
import re
from pathlib import Path

import pdfplumber
from beancount import Amount
from beancount.core import data
from beangulp.importer import Importer

from .utils import make_posting, make_transaction

_ROW_START_RE = re.compile(r"^\d+\s+\d{8}\s+\d{8}\s+\d{4}\s+")
_ROW_RE = re.compile(r"^(\d+)\s+(\d{8})\s+(\d{8})\s+(\d{4})\s+(.+)$")
_AMOUNT_RE = re.compile(r"人民币\s*元/\s*([+-]?\d[\d,]*\.\d{2})")


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Record:
    trade_date: datetime.date
    booking_date: datetime.date
    card_last4: str
    description: str
    amount: decimal.Decimal


class CCBXykmxPdfImporter(Importer):
    """Importer for CCB credit card transaction detail PDFs (xykmx_*.pdf).

    Data rows look like::

        1 20240101 20240102 1234 商户名... 人民币 元/-123.45
    """

    def __init__(self, account: str, currency: str = "CNY") -> None:
        self._account: str = account
        self._currency: str = currency

    def account(self, filepath: str) -> data.Account:
        return self._account

    def identify(self, filepath: str) -> bool:
        path = Path(filepath)
        if path.suffix.lower() != ".pdf":
            return False
        if not path.name.lower().startswith("xykmx_"):
            return False

        try:
            with pdfplumber.open(path) as pdf:
                first_page = pdf.pages[0]
                for line in first_page.extract_text_lines():
                    text = (line.get("text") or "").strip()
                    if "信用卡交易明细" in text:
                        return True
        except Exception:  # noqa: BLE001 - any parse failure means "not our file"
            return False

        return False

    def extract(self, filepath: str, existing: data.Entries) -> data.Entries:
        results: list[data.Directive] = []

        for lineno, row in enumerate(self._extract_rows(Path(filepath)), start=1):
            record = self._parse_row(row)
            if record is None:
                continue

            meta = data.new_metadata(filepath, lineno)
            meta["booking_date"] = record.booking_date.isoformat()
            meta["card_last4"] = record.card_last4
            meta["raw_summary"] = record.description

            postings = [
                make_posting(
                    account=self._account,
                    units=Amount(-record.amount, self._currency),
                )
            ]

            results.append(
                make_transaction(
                    meta,
                    record.trade_date,
                    narration=record.description,
                    postings=postings,
                )
            )

        return results

    @staticmethod
    def _extract_rows(path: Path) -> list[str]:
        rows: list[str] = []
        current: str | None = None

        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                for raw_line in page.extract_text_lines():
                    text = (raw_line.get("text") or "").strip()
                    if not text:
                        continue

                    if "信用卡交易明细" in text or text.startswith(
                        (
                            "生成时间:",
                            "Credit Card Transaction Details",
                            "客户姓名（Name）：",
                            "序号 交易日",
                            "No. T-Date",
                        )
                    ):
                        continue

                    if _ROW_START_RE.match(text):
                        if current:
                            rows.append(current)
                        current = text
                    elif current is not None:
                        current = f"{current} {text}"

        if current:
            rows.append(current)

        return rows

    @staticmethod
    def _parse_row(row: str) -> Record | None:
        row = re.sub(r"\s+", " ", row).strip()
        m = _ROW_RE.match(row)
        if m is None:
            return None

        _index, trade_text, booking_text, card_last4, tail = m.groups()
        amount_match = _AMOUNT_RE.search(tail)
        if amount_match is None:
            return None

        description = tail[: amount_match.start()].strip()
        if not description:
            return None

        return Record(
            trade_date=datetime.date(
                int(trade_text[:4]), int(trade_text[4:6]), int(trade_text[6:8])
            ),
            booking_date=datetime.date(
                int(booking_text[:4]), int(booking_text[4:6]), int(booking_text[6:8])
            ),
            card_last4=card_last4,
            description=description,
            amount=CCBXykmxPdfImporter._parse_decimal(amount_match.group(1)),
        )

    @staticmethod
    def _parse_decimal(value: str) -> decimal.Decimal:
        return decimal.Decimal(value.replace(",", ""))
