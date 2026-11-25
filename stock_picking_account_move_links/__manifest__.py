# -*- coding: utf-8 -*-

{
    "name": "قيود أذونات المخزون",
    "version": "17.0.1.0.0",
    "category": "Inventory/Inventory",
    "summary": "عرض القيود المحاسبية المرتبطة فعليًا بإذن المخزون",
    "author": "Eljohany",
    "license": "LGPL-3",
    "depends": ["stock_account", "sale_stock", "purchase_stock"],
    "data": [
        "views/stock_picking_views.xml",
    ],
    "installable": True,
    "application": True,
}
