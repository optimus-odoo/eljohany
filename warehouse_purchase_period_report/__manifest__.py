# -*- coding: utf-8 -*-

{
    "name": "Warehouse Movement by Period",
    "version": "17.0.1.3.0",
    "category": "Inventory/Reporting",
    "summary": "Closing quantity and opening-balance average cost by warehouse",
    "author": "Eljohany",
    "license": "LGPL-3",
    "depends": ["stock_account", "purchase_stock"],
    "data": [
        "security/ir.model.access.csv",
        "views/warehouse_purchase_report_views.xml",
        "report/warehouse_purchase_report_actions.xml",
        "report/warehouse_purchase_report_templates.xml",
    ],
    "installable": True,
    "application": False,
}
