# -*- coding: utf-8 -*-
{
    "name": "Product Cost Security",
    "version": "17.0.1.2.0",
    "summary": "Restrict product cost editing and sales cost visibility",
    "category": "Inventory/Inventory",
    "author": "Ammar",
    "license": "LGPL-3",
    "depends": ["product", "stock", "sale_margin"],
    "data": [
        "security/security.xml",
        "views/sale_order_views.xml",
        # "views/product_template_views.xml",
        # "views/product_product_views.xml",
    ],
    "installable": True,
    "application": False,
}
