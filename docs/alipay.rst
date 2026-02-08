支付宝
=====

示例配置:

.. code-block:: python

   from china_beancount_importers.alipay import AlipayImporter

   CONFIG = [
       AlipayImporter(account="Assets:Alipay"),
   ]

.. autoclass:: china_beancount_importers.alipay.AlipayImporter
