{
    "name": "POS Shift Summary Report",
    "version": "17.0.1.3.0",
    "summary": "Reliable Arabic POS shift report by exact date and time",
    "category": "Sales/Point of Sale",
    "author": "Eljohany",
    "license": "LGPL-3",
    "depends": ["point_of_sale"],
    "data": [
        "security/ir.model.access.csv",
        "views/pos_shift_summary_report_views.xml",
        "report/pos_shift_summary_report_templates.xml",
        "report/pos_shift_summary_report_actions.xml",
        "report/pos_sale_details_templates.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_shift_summary_report/static/src/app/closing_shift_report.js",
            "pos_shift_summary_report/static/src/app/closing_shift_report.xml",
        ],
    },
    "installable": True,
    "application": False,
}
