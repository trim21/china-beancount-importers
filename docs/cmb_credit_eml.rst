招行信用卡邮件
==============

示例配置:

.. code-block:: python

   from china_beancount_importers.cmb_credit_eml import CmbEmlImporter

   CONFIG = [
       CmbEmlImporter(account_name="Liabilities:CreditCard"),
   ]

.. autoclass:: china_beancount_importers.cmb_credit_eml.CmbEmlImporter
