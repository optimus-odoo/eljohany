# -*- coding: utf-8 -*-
{
    "name": "Customer Payment Invoice Allocation",
    "version": "17.0.1.0.7",
    "category": "Accounting",
    "summary": "Allocate customer payments against open invoices from payment form",
    "depends": ["account"],
    "data": [
        "security/ir.model.access.csv",
        "views/account_payment_views.xml"
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
