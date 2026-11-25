{
    "name": "كشف حساب الموردين الشامل",
    "version": "17.0.1.3.0",
    "category": "المحاسبة/التقارير",
    "summary": "كشف حساب الموردين لجميع الحسابات مع الرصيد الافتتاحي والطباعة والتصدير",
    "author": "Eljohany",
    "license": "LGPL-3",
    "depends": ["account"],
    "external_dependencies": {"python": ["xlsxwriter"]},
    "data": [
        "security/ir.model.access.csv",
        "views/vendor_ledger_report_views.xml",
        "report/vendor_ledger_report_templates.xml",
        "report/vendor_ledger_report_actions.xml",
    ],
    "installable": True,
    "application": False,
}
