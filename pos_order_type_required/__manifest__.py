{
    "name": "POS Required Order Type",
    "version": "17.0.1.5.0",
    "summary": "Require the POS order type and provide a branded thermal receipt",
    "category": "Sales/Point of Sale",
    "author": "Eljohany",
    "license": "LGPL-3",
    "depends": ["point_of_sale"],
    "data": [
        "views/pos_order_views.xml",
        "views/res_company_views.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_order_type_required/static/src/app/order_type.js",
            "pos_order_type_required/static/src/app/order_type.xml",
            "pos_order_type_required/static/src/app/receipt.scss",
        ],
    },
    "installable": True,
    "application": False,
}
