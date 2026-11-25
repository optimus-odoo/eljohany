# -*- coding: utf-8 -*-
{
    "name": "Eljohany Stock Aging Report",
    "version": "17.0.1.1.1",
    "category": "Inventory/Reporting",
    "summary": "Arabic stock aging report with cost, quantities, product category, Excel and PDF.",
    "depends": ["stock", "account", "branch"],
    "data": [
        "security/ir.model.access.csv",
        "views/stock_aging_report_views.xml",
        "report/stock_aging_report_templates.xml",
        "report/stock_aging_report_actions.xml",
    ],
    "license": "LGPL-3",
    "application": False,
    "installable": True,
}
