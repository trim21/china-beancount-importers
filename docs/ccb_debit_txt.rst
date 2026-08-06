建行借记卡 txt
===============

适用于建行网银导出的 txt 格式交易明细（`交易明细_*.txt`），
文件头部包含账号信息，根据账号尾号映射到 beancount 账户。

示例配置:

.. code-block:: python

   from china_beancount_importers.ccb_debit_txt import CCBDebitTxtImporter

   CONFIG = [
       CCBDebitTxtImporter(
           account_map={"3864": "Assets:Bank:CCB:3864"},
           currency="CNY",
       ),
   ]

.. autoclass:: china_beancount_importers.ccb_debit_txt.CCBDebitTxtImporter
