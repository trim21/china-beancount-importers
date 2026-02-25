招行借记卡
=========

示例配置:

.. code-block:: python

   from china_beancount_importers.cmb_debeit import CMBDebitImporter

   CONFIG = [
       CMBDebitImporter(
           account_map={
               # 使用导出 CSV 文件头的“账 号: [一卡通:...XXXX ...]”里的末四位
               "1234": "Assets:Bank:CMB:C1234",
           },
           currency="CNY",
       ),
   ]

.. autoclass:: china_beancount_importers.cmb_debeit.CMBDebitImporter
