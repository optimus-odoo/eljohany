{
    "name": "Customer Credit Control + Dashboard (Arabic) - Odoo 17",
    "version": "17.0.1.3.2",
    "license": "LGPL-3",
    "category": "Sales",
    "summary": "Block SO confirmation by credit limit or follow-up overdue status + Arabic dashboard.",
    "depends": ["sale_management", "account", "web", "account_followup"],
    "data": [
        "security/ir.model.access.csv",
        "views/res_partner_views.xml",
        "views/credit_dashboard_views.xml",
        "views/credit_control_menus.xml"
    ],
    "assets": {
        "web.assets_backend": [
            "customer_credit_control/static/src/js/credit_dashboard.js",
            "customer_credit_control/static/src/xml/credit_dashboard.xml"
        ]
    },
    "installable": True,
    "application": False
}
