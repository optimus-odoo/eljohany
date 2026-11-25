# -*- coding: utf-8 -*-
{
    'name': "Partner Ledger Logo",

    'summary': "Add company logo to Partner Ledger reports",

    'description': """
This module customizes the Partner Ledger report by adding the company logo 
to improve branding and professional appearance.

Developer Info:
- Name: Ahmed Hamdy Sayed
- Mobile: 01020443517
- LinkedIn: https://www.linkedin.com/in/a1hamdy/
    """,

    'author': "Ahmed Hamdy Sayed",
    'website': "https://www.linkedin.com/in/a1hamdy/",

    'category': 'Accounting',
    'version': '1.0.0',
    'license': 'LGPL-3',

    'depends': ['base','account'],

    'data': [
        'views/templates.xml',
    ],

    'installable': True,
    'application': False,
    'auto_install': False,
}
