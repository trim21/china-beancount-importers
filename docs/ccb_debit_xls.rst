建行借记卡 xls
===============

适用于建行网银导出的 xls 格式交易明细（`交易明细_*.xls`）。

示例配置:

.. code-block:: python

   from china_beancount_importers.ccb_debit_xls import CCBDebitXlsImporter

   CONFIG = [
       CCBDebitXlsImporter(
           account="Assets:Bank:CCB",
           currency="CNY",
       ),
   ]

.. autoclass:: china_beancount_importers.ccb_debit_xls.CCBDebitXlsImporter
