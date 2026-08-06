建行信用卡明细 PDF
===================

适用于建行信用卡交易明细 PDF（`xykmx_*.pdf`）。

示例配置:

.. code-block:: python

   from china_beancount_importers.ccb_xykmx_pdf import CCBXykmxPdfImporter

   CONFIG = [
       CCBXykmxPdfImporter(
           account="Liabilities:CreditCard",
           currency="CNY",
       ),
   ]

.. autoclass:: china_beancount_importers.ccb_xykmx_pdf.CCBXykmxPdfImporter
