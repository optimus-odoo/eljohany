{
    'name': 'Account Customizations',
    'version': '1.0.0',
    'category': 'Accounting',
    'summary': 'Account Customizations',
    'description': '''
    ''',
    'author': 'Hamza Naveed',
    'website': 'https://linkedin.com/in/sm-hamza-naveed',
    'depends': [ 'base', 'account' ],
    'data': [
        'security/ir.model.access.csv',
        'views/res_config_settings.xml',
        'reports/custom_invoice_report.xml',
    ],

    'installable': True,
    'auto_install': False,
    'application': False,
    'license': 'LGPL-3',
}
