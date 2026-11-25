# Part of Softhealer Technologies.

{
    'name': 'Employee Visits With Location Information',
    'version': '0.0.3',
    'category': 'Sales',
    "license": "OPL-1",
    "author": "DeeB",
    "website": "",
    "summary": "Client Attendance With Map Check In with location and Check Out With Map Location in Odoo",
    "description": """Do you want to get the location of the partner(vendor, supplier, customer, client & contact) while visiting him and record check in & check out details? You can get check in & check out geolocation of the partner. This module helps to track the real-location of employee visits at the partner place. You can select a partner while visiting him from map and get geolocation. When partners check in & check out they can write messages, comments, or any notes. You can get geolocation result based on a filter like job position, date, department & employee name. So be very quick in all procedures and cheers!""",
    'depends': ['base', 'base_geolocalize','web_map'],
    'data': [
        'security/groups.xml',
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'views/visit_type_views.xml',
        'views/visit.xml',
        'views/partner.xml',
        'views/visit_settings.xml',
        'views/menu.xml',
    ],
    'assets': {
        'web.assets_backend': [

            'sales_visits/static/src/js/map.js',
            "sales_visits/static/src/xml/map.xml",
        ],
    },
    "images": ["static/description/background.jpeg", ],
    "live_test_url": "",
    'installable': True,
    'auto_install': False,
    'application': True,
    "price": 100,
    "currency": "USD"
}
