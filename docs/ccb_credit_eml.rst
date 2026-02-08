建行信用卡邮件
==============

示例配置:

.. code-block:: python

   from china_beancount_importers.ccb_credit_eml import CCBCreditEmlImporter

   CONFIG = [
       CCBCreditEmlImporter(account_name="Liabilities:CreditCard"),
   ]

.. autoclass:: china_beancount_importers.ccb_credit_eml.CCBCreditEmlImporter
