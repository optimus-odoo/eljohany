# -*- coding: utf-8 -*-

{
    "name": "Eljohany Slow Moving Products Report",
    "version": "17.0.1.1.0",
    "category": "Inventory/Reporting",
    "summary": "Reliable stagnant-products report based on completed customer deliveries",
    "depends": ["stock_account", "purchase_stock", "branch"],
    "data": [
        "security/ir.model.access.csv",
        "views/slow_moving_report_views.xml",
        "report/slow_moving_report_actions.xml",
        "report/slow_moving_report_templates.xml",
    ],
    "license": "LGPL-3",
    "application": False,
    "installable": True,
}
