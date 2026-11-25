# -*- coding: utf-8 -*-
{
    'name': 'Vendor vs Stock Difference Report',
    'version': '17.0.1.0.0',
    'summary': 'Compare vendor bill values against stock valuation values',
    'category': 'Accounting/Accounting',
    'author': 'OpenAI',
    'license': 'LGPL-3',
    'depends': ['account', 'stock', 'purchase'],
    'data': [
        'security/ir.model.access.csv',
        'wizard/vendor_stock_difference_wizard_views.xml',
        'views/vendor_stock_difference_result_views.xml',
        'report/vendor_stock_difference_report_templates.xml',
        'report/vendor_stock_difference_report_actions.xml',
        'views/menu_views.xml',

    ],
    'installable': True,
    'application': False,
}
