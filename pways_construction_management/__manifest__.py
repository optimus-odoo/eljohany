{
    'name': 'Construction Management System',
    'version': '17.0.1.0.1',
    'category': 'Projects & Industries',
    'sequence': '100',
    'summary': """ date=27/11/24 Manage your Construction Details,Construction Cost Estimation,Job Orders,Material Requistions,Vehicle and Equipment Request,Instruction Quality Checks,Maintenance Request,Construction Dialy logs,Contractors,Inspections,Compliances,House Sales Process""",
    'description': """Construction Details
                    Construction Cost Estimation
                    Job Orders
                    Material Requistions
                    Vehicle Request
                    Equipment Request,Instruction
                    Quality Checks,Maintenance Request
                    Construction Dialy logs
                    Contractor Management
                    Inspections,Compliances
                    House Sales Process Reports
                    Construction Management
                    Project Management
                    Scrap Management
                    Bugdet Management
                    Material Management

    """,
    'author': 'Preciseways',
    'website': 'https://www.preciseways.com',
    'depends': [
                'project', 'account', 'mail', 
                'stock', 'hr', 'purchase',
                'sale', 'hr_timesheet',
                'stock_account', 'fleet',
                'maintenance','hr_expense',
                'sale_management', 'sale_project',
                ],
    'data': [
        'security/ir.model.access.csv',
        'security/security.xml',
        'report/job_costing_report.xml',
        'report/purchase_requisition_report.xml',
        'report/construct_daily_log_report.xml',
        'report/report_project.xml',
        'report/report_task.xml',
        'data/project_email_send_pdf.xml',
        'data/employee_purchase_approval_template.xml',
        'data/confirm_template_material_purchase.xml',
        'data/sequence_data.xml',
        'wizard/project_user_subtask_view.xml',
        'wizard/task_picking_wizard_view.xml',
        'wizard/timesheet_bill_wizard_view.xml',
        'wizard/project_inherited_wizard_action.xml',
        'views/construct_cycle_view.xml',
        'views/construct_process_view.xml',
        'views/construct_inspector_view.xml',
        'views/construct_compliance_tags_view.xml',
        'views/construct_compliance_view.xml',
        'views/construct_daily_logs_view.xml',
        'views/construct_instruction_qlty_checklist_view.xml',
        'views/account.xml',
        'views/material_requisition_view.xml',
        'views/cost_veh_eqq_request.xml',
        'views/maintenance_request_view.xml',
        'views/stock_picking_view.xml',
        'views/project_project_view.xml',
        'views/project_task_view.xml',
        'views/job_costing_view.xml',
        'views/job_type.xml',
        'views/product_view.xml',
        'views/purchase_view.xml',
        'views/project_task_type.xml',
        'views/construction_management_view.xml',
        'views/menu_view.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'pways_construction_management/static/src/js/construct_dashboard.js',
            'pways_construction_management/static/src/xml/construct_dashboard_template.xml',
            'pways_construction_management/static/src/css/style.css',
            "https://www.gstatic.com/charts/loader.js",
            "https://cdnjs.cloudflare.com/ajax/libs/Chart.js/2.9.4/Chart.js",
            'pways_construction_management/static/src/xml/many2many_binary_field_preview.xml',
            'pways_construction_management/static/src/js/many2many_binary_field_preview.js',
        ],
    },
    'images': ['static/description/banner.png'],
    'application': True,
    'installable': True,
    'price': 69,
    'currency': 'EUR',
    'license': 'OPL-1',
}
