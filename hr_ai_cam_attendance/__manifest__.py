# -*- coding: utf-8 -*-
{
    'name': 'Hr AI Cam Attendance',
    'version': '15.0.0',
    'summary': 'Face Recognition Attendance comparing face with user image',
    'description': """
        Allow users to use cam to register attendance by matching there face 
        with user profile image and git there location long and lat and comparing it with the company location if employee set to attendance from company or compare it with the location on the employee if he set to attendance from another locations then save them in attendance record
        you didn't need to install any other library
    """,
    'category': 'Human Resources',
    'author': "DeeB",
    'company': 'DeeB',
    'live_test_url': '',
    'price': 110,
    'currency': 'USD',
    'website': "",
    'depends': ['hr_attendance'],
    'data': [
        'views/menu.xml',
        'views/hr_attendance.xml',
        'views/hr_attendance_settings.xml',
        'views/hr_employee.xml',
    ],
    'demo': [],

    'assets': {
        "web.assets_frontend": [
            # to add scss and js here


        ],
        "web.assets_backend": [
            "hr_ai_cam_attendance/static/src/lib/face_api/dist/face_api.min.js",
            "hr_ai_cam_attendance/static/src/js/face_detection.js",
            "hr_ai_cam_attendance/static/src/css/face_detection.css",
            "hr_ai_cam_attendance/static/src/xml/face_detection.xml",

        ],
    },

    'images': ['static/description/icon.png'],
    'license': 'LGPL-3',
    'installable': True,
    'auto_install': False,
    'application': False,
}
