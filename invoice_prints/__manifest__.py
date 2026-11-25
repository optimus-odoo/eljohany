# -*- coding: utf-8 -*-
{
    'name': "invoice_prints",

    'summary': "Short (1 phrase/line) summary of the module's purpose",

    'description': """
Long description of module's purpose
    """,

    'author': "My Company",
    'website': "https://www.yourcompany.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Uncategorized',
    'version': '17.0.1.1.0',
    'license': 'LGPL-3',

    # any module necessary for this one to work correctly
    'depends': ['base', 'account','sale','product'],

    # always loaded
    'data': [
        'views/views.xml',
        'views/esdar_template.xml',
        'views/invoice_temp.xml',
    ],
}
