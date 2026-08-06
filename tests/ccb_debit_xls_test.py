from os import path

import xlwt
from beancount.core import data
from beangulp.extract import extract_from_file

from china_beancount_importers.ccb_debit_xls import CCBDebitXlsImporter

_HEADER = [
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


def _write_ccb_debit_xls(filepath: str) -> None:
    wb = xlwt.Workbook(encoding="utf-8")
    ws = wb.add_sheet("交易明细")
    rows = [
        ["中国建设银行账户交易明细"],
        ["账　　号：622280*********3864"],
        ["起始日期：[20240101] 终止日期：[20240102]"],
        ["币　　种：[人民币]"],
        [],
        _HEADER,
        [
            "20240102",
            "20240101",
            "12:00:00",
            "10.00",
            "",
            "100.00",
            "CNY",
            "午餐",
            "6222",
            "某商户",
            "北京",
        ],
        [
            "20240103",
            "20240102",
            "13:00:00",
            "",
            "20.00",
            "120.00",
            "CNY",
            "转账",
            "6222",
            "某人",
            "上海",
        ],
        ["以上数据为打印时点数据", "", "", "", "", "", "", "", "", "", ""],
    ]
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            ws.write(r, c, value)
    wb.save(filepath)


def test_identify(tmpdir):
    p = path.join(tmpdir, "交易明细_3864.xls")
    _write_ccb_debit_xls(p)
    importer = CCBDebitXlsImporter(account="Assets:Bank:CCB:3864")
    assert importer.identify(p)
    assert not importer.identify(path.join(tmpdir, "交易明细_3864.txt"))


def test_extract(tmpdir):
    p = path.join(tmpdir, "交易明细_3864.xls")
    _write_ccb_debit_xls(p)
    importer = CCBDebitXlsImporter(account="Assets:Bank:CCB:3864")

    entries = extract_from_file(importer, p, [])
    # footer row "以上数据..." is dropped
    assert len(entries) == 3  # 2 transactions + 1 balance

    txns = [e for e in entries if isinstance(e, data.Transaction)]
    balance = next(e for e in entries if isinstance(e, data.Balance))

    assert txns[0].date.isoformat() == "2024-01-01"
    assert txns[0].payee == "某商户"
    assert txns[0].narration == "北京"
    assert txns[0].meta.get("time") == "12:00:00"
    assert txns[0].postings[0].units.number == -10.0

    assert txns[1].postings[0].units.number == 20.0

    assert balance.account == "Assets:Bank:CCB:3864"
    assert balance.date.isoformat() == "2024-01-03"
    assert balance.amount.number == 120.0
