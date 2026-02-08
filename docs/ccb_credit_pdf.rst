建行信用卡 PDF
===============

示例配置:

.. code-block:: python

   from china_beancount_importers.ccb_credit_pdf import CCBCreditPdfImporter

   CONFIG = [
       CCBCreditPdfImporter(
           account="Liabilities:CreditCard",
           currency="CNY",
       ),
   ]

.. autoclass:: china_beancount_importers.ccb_credit_pdf.CMB
