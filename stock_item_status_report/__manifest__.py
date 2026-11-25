# -*- coding: utf-8 -*-
{
    "name": "Stock Item Status Report (Excel + PDF)",
    "version": "17.0.1.4.1",
    "category": "Inventory/Reporting",
    "summary": "Stock report with current quantity split by receipt vendor, standard cost, reorder point, sold qty, Excel and PDF. Supports multiple locations and branches (res.branch).",
    "depends": ["stock", "account", "purchase_stock", "base", "branch"],
    "data": [
        "security/ir.model.access.csv",
        "views/stock_item_status_report_views.xml",
        "report/stock_item_status_report_templates.xml",
        "report/stock_item_status_report_actions.xml",
    ],
    "license": "LGPL-3",
    "application": False,
    "installable": True,
}
