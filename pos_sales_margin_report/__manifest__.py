{
    "name": "POS Sales and Margin Report",
    "version": "17.0.1.1.0",
    "summary": "Product sales, discounts, taxes, totals, and margins by POS and date/time range",
    "category": "Sales/Point of Sale",
    "author": "Eljohany",
    "license": "LGPL-3",
    "depends": ["point_of_sale"],
    "external_dependencies": {"python": ["xlsxwriter"]},
    "data": [
        "security/ir.model.access.csv",
        "views/pos_sales_margin_report_views.xml",
        "report/pos_sales_margin_report_templates.xml",
        "report/pos_sales_margin_report_actions.xml",
    ],
    "installable": True,
    "application": False,
}
