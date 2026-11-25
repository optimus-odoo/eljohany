# -*- coding: utf-8 -*-
{
    "name": "Invoice Attachment Batch Download",
    "summary": "Download unique invoice attachments from journal entries and items",
    "version": "17.0.1.0.0",
    "category": "Accounting/Accounting",
    "author": "Eljohany",
    "license": "LGPL-3",
    "depends": ["account"],
    "data": [
        "security/ir.model.access.csv",
        "data/server_actions.xml",
    ],
    "installable": True,
    "application": False,
}
