建行借记卡
=========

示例配置:

.. code-block:: python

   from china_beancount_importers.ccb_debeit import CCBDebeitImporter

   CONFIG = [
       CCBDebeitImporter(account="Assets:Bank", currency="CNY"),
   ]

.. autoclass:: china_beancount_importers.ccb_debeit.CCBDebeitImporter
