{
    "name": "Eljohany Partner Dual Account Control",
    "summary": "Enforce separate receivable and payable accounts for dual-role partners",
    "version": "17.0.1.1.0",
    "category": "Accounting/Accounting",
    "license": "LGPL-3",
    "author": "Eljohany",
    "depends": ["account"],
    "data": [
        "security/ir.model.access.csv",
        "views/res_config_settings_views.xml",
        "views/res_partner_views.xml",
        "views/account_move_views.xml",
        "views/account_payment_views.xml",
        "wizard/partner_account_audit_views.xml",
    ],
    "installable": True,
    "application": False,
}
