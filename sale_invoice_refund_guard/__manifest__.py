{
    "name": "Sales Invoice Refund Guard",
    "summary": "Prevent customer refunds from exceeding invoiced quantities",
    "version": "17.0.1.2.4",
    "category": "Accounting/Accounting",
    "license": "LGPL-3",
    "depends": ["account", "product_last_price"],
    "data": [
        "security/refund_security.xml",
    ],
    "installable": True,
    "application": False,
}
