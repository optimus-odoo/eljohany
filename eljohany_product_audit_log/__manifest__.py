{
    "name": "Eljohany Product Audit Log",
    "summary": "Immutable, permission-controlled audit trail for product changes",
    "version": "17.0.1.0.2",
    "category": "Inventory/Inventory",
    "author": "Eljohany",
    "license": "LGPL-3",
    "depends": ["product"],
    "data": [
        "security/product_audit_security.xml",
        "security/ir.model.access.csv",
        "views/product_template_views.xml",
    ],
    "installable": True,
    "application": False,
}
