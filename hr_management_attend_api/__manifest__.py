{
    "name": "HR Management Attendance API",
    "summary": "Secure REST API for branch-based GPS employee attendance",
    "version": "17.0.1.6.0",
    "category": "Human Resources/Attendances",
    "author": "Eljohany",
    "license": "LGPL-3",
    "depends": ["hr", "hr_attendance", "branch"],
    "data": [
        "security/hr_management_attend_api_security.xml",
        "security/ir.model.access.csv",
        "data/ir_cron.xml",
        "views/res_branch_views.xml",
        "views/hr_employee_views.xml",
        "views/hr_attendance_views.xml",
        "views/api_audit_views.xml",
        "views/res_config_settings_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "hr_management_attend_api/static/src/scss/attendance_sync_log.scss",
        ],
    },
    "application": False,
    "installable": True,
    "auto_install": False,
}
