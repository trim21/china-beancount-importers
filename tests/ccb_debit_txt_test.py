import csv
from os import path

from beancount.core import data
from beangulp.extract import extract_from_file

from china_beancount_importers.ccb_debit_txt import CCBDebitTxtImporter


def _write_ccb_debit_txt(filepath: str) -> None:
    with open(filepath, "w", encoding="utf-8", newline="") as f:
        f.write("账　　号：622280*********3864\n")
        f.write("起始日期：[20240101] 终止日期：[20240103]\n")
        f.write("币　　种：[人民币]\n")
        writer = csv.writer(f)
        writer.writerow(
            [
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
        )
        writer.writerow(
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
            ]
        )
        writer.writerow(
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
            ]
        )


def test_identify(tmpdir):
    p = path.join(tmpdir, "交易明细_3864.txt")
    _write_ccb_debit_txt(p)
    importer = CCBDebitTxtImporter(account_map={"3864": "Assets:Bank:CCB:3864"})
    assert importer.identify(p)

    # account suffix not in map
    other = CCBDebitTxtImporter(account_map={"1234": "Assets:Bank:CCB:1234"})
    assert not other.identify(p)


def test_extract(tmpdir):
    p = path.join(tmpdir, "交易明细_3864.txt")
    _write_ccb_debit_txt(p)
    importer = CCBDebitTxtImporter(account_map={"3864": "Assets:Bank:CCB:3864"})

    assert importer.account(p) == "Assets:Bank:CCB:3864"

    entries = extract_from_file(importer, p, [])
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
