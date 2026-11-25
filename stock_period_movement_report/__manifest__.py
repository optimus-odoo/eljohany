# -*- coding: utf-8 -*-
{
    "name": "تقرير حركة المخزون بين فترتين (عربي + Excel)",
    "version": "17.0.1.1.1",
    "category": "Inventory/Reporting",
    "summary": "تقرير حركة المخزون بين فترتين مع الرصيد الافتتاحي وتصدير Excel (واجهة عربية).",
    "author": "ChatGPT",
    "license": "LGPL-3",
    "depends": ["stock", "stock_account"],
    "data": [
        "security/ir.model.access.csv",
        "views/stock_period_report_views.xml",
        "views/stock_period_report_menu.xml",
        # "views/stock_period_report_settings.xml"
    ],
    "installable": True,
    "application": False
}
