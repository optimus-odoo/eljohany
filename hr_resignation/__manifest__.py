# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': "HR Resignation",
    'version': '17.0.1.8',
    'summary': """ HR Resignation """,
    'description': """Manage Employee Resignation""",
    'category': 'Human Resources',
    'author': 'DeeB',
    'company': '',
    'live_test_url': '',
    'website': '',
    'depends': ['hr', 'account', 'website', 'hr_custody','hr_employees_operations_menu'],
    'data': [
        'security/ir.model.access.csv',
        'security/ir_rule.xml',
        'views/hr_employee_resignation_view.xml',
        'views/hr_employee_view.xml',

        # 'views/template/portal_menu.xml',
        # 'views/template/resignation_template.xml',
        'data/sequence.xml',
        'views/menu.xml',
    ],
    'demo': [
        # 'demo/demo.xml'
    ],
    'images': ['static/description/banner.gif'],
    'license': 'LGPL-3',
    'installable': True,
    'auto_install': False,
    'application': False,
}
