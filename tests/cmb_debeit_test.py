import csv
from os import path

from beancount.core import data
from beangulp.extract import extract_from_file

from china_beancount_importers.cmb_debeit import CMBDebitImporter


def _write_cmb_debit_csv(filepath: str) -> None:
    # Header lines (7 lines total), matching CMB PC export style.
    header_lines = [
        "# 招商银行交易记录\n",
        "# 导出时间: [            2026-02-25 20:54:27]\n",
        "# 账    号: [一卡通:6214********1234   招商银行]\n",
        "# 币    种: [                         人民币]\n",
        "# 起始日期: [20260219]   终止日期: [20260225]\n",
        "# 过滤设置:  无\n",
        '""\n',
    ]

    with open(filepath, "w", encoding="utf-8", newline="") as f:
        f.writelines(header_lines)
        writer = csv.writer(f)
        writer.writerow(
            ["交易日期", "交易时间", "收入", "支出", "余额", "交易类型", "交易备注"]
        )
        writer.writerow(["20260225", "20:00:00", "", "10.00", "90.00", "消费", "午饭"])
        # Footer lines (export usually has 3 trailing lines; importer slices them away)
        f.write("# end\n")
        f.write("# end\n")
        f.write("# end\n")


def test_account_selected_from_header(tmpdir):
    csv_path = path.join(tmpdir, "CMB_foo.csv")
    _write_cmb_debit_csv(csv_path)

    importer = CMBDebitImporter(account_map={"1234": "Assets:Bank:CMB:1234"})

    assert importer.account(csv_path) == "Assets:Bank:CMB:1234"

    entries = extract_from_file(importer, csv_path, [])
    assert len(entries) == 2

    balance = next(entry for entry in entries if isinstance(entry, data.Balance))
    txn = next(entry for entry in entries if isinstance(entry, data.Transaction))
    assert balance.account == "Assets:Bank:CMB:1234"
    assert txn.postings[0].account == "Assets:Bank:CMB:1234"
    assert txn.meta.get("card_last4") == "1234"
