招行信用卡 PDF
===============

示例配置:

.. code-block:: python

   from china_beancount_importers.cmb_credit_pdf import CMBCreditPdfImporter

   CONFIG = [
       CMBCreditPdfImporter(
           account="Liabilities:CreditCard",
           currency="CNY",
       ),
   ]

.. autoclass:: china_beancount_importers.cmb_credit_pdf.CMBCreditPdfImporter
