招行借记卡
=========

示例配置:

.. code-block:: python

   from china_beancount_importers.cmb_debeit import CMBDebitImporter

   CONFIG = [
       CMBDebitImporter(account="Assets:Bank", currency="CNY"),
   ]

.. autoclass:: china_beancount_importers.cmb_debeit.CMBDebitImporter
