from datetime import date, timedelta
from odoo import fields, http
from odoo.http import request
from collections import defaultdict

class ConstructDashboard(http.Controller):
    @http.route('/construct/dashboard', type='json', auth='user')
    def _get_agri_dashboard_values(self):
        company_id = request.env.user.company_id
        current_year = date.today().year
        construct_start_date = request.env['ir.config_parameter'].sudo().get_param('pways_construction_management.construct_start_date')
        construct_end_date = request.env['ir.config_parameter'].sudo().get_param('pways_construction_management.construct_end_date')
        
        # Fetch invoices related to projects for the current year
        invoices = request.env['account.move'].search([
            # ('move_type', '=', 'out_invoice'),
            ('invoice_date', '>=', construct_start_date),
            ('invoice_date', '<=', construct_end_date),
            ('project_id', '!=', False),
        ])

        # Prepare data for the yearly invoices chart with month abbreviations
        project_invocie_yearly = [['Month', 'Total Invoices']]
        for month in range(1, 13):
            monthly_total = sum(invoice.amount_total for invoice in invoices if invoice.invoice_date.month == month)
            month_name = date(current_year, month, 1).strftime("%b")
            project_invocie_yearly.append([month_name, monthly_total])

        # Project data
        projects = request.env['project.project'].search([
            ('company_id', '=', company_id.id),
            ('date_start', '>=', construct_start_date),
            ('date', '<=', construct_end_date),
        ])

        project_state_data = [['State', 'Projects']]
        state_count = defaultdict(int)
        selection_labels = dict(request.env['project.project'].fields_get(['state'])['state']['selection'])

        for project in projects:
            state_label = selection_labels.get(project.state, project.state)
            state_count[state_label] += 1

        for state, count in state_count.items():
            project_state_data.append([state, count])

        # Task data
        # tasks = request.env['project.task'].search([
        #     ('company_id', '=', company_id.id),
        #     ('create_date', '>=', construct_start_date),
        #     ('create_date', '<=', construct_end_date),
        # ])
        tasks = request.env['project.task'].search([
            ('company_id', '=', company_id.id),
            ('create_date', '>=', construct_start_date),
            ('create_date', '<=', construct_end_date),
        ])

        task_stage_data = [['Stage', 'Tasks']]
        stage_count = defaultdict(int)
        for task in tasks:
            if task.stage_id.set_default:
                stage_name = task.stage_id.name if task.stage_id else 'Undefined'
                stage_count[stage_name] += 1

        for stage, count in stage_count.items():
            task_stage_data.append([stage, count])

        # Get all job costing records for the current year
        job_costings = request.env['job.costing'].search([
            ('create_date', '>=', construct_start_date),
            ('create_date', '<=', construct_end_date),
            ('company_id', '=', company_id.id),
        ])
        # job_costings = request.env['job.costing'].search([
        #     ('start_date', '>=', construct_start_date),
        #     ('complete_date', '<=', construct_end_date),
        #     ('company_id', '=', company_id.id),
        # ])

        # Aggregate the total cost by job type
        cost_by_job_type = defaultdict(float)

        for job in job_costings:
            # Get the amount based on the job type
            cost_by_job_type['material'] += job.cost_material_total_price
            cost_by_job_type['labour'] += job.cost_labours_total_price
            cost_by_job_type['overhead'] += job.cost_overheads_total_price
            cost_by_job_type['vehicle'] += job.cost_fleet_total_price
            cost_by_job_type['equipment'] += job.cost_equipment_total_price

        # Prepare data for the graph
        cost_type_data = [['Job Type', 'Total Cost']]
        for job_type, total_cost in cost_by_job_type.items():
            cost_type_data.append([job_type.capitalize(), total_cost])

        job_costing_count = request.env['job.costing'].sudo().search_count([('user_id', '=', request.env.user.id)])
        projects_count = request.env['project.project'].sudo().search_count([('user_id', '=', request.env.user.id)])
        tasks_count = request.env['project.task'].sudo().search_count([('project_id', '!=', False), ('user_ids', 'in', request.env.user.id)])
        contractors_count = request.env['res.partner'].sudo().search_count([])
        bills_count = request.env['account.move'].sudo().search_count(['|', '|', ('project_id', '!=', False), ('task_id', '!=', False), ('job_cost_id', '!=', False)])
        picking_count = request.env['stock.picking'].sudo().search_count(['|', '|', ('project_id', '!=', False), ('task_id', '!=', False), ('job_cost_id', '!=', False)])
        inspection_count = request.env['construct.inspector'].sudo().search_count([('inspector_id', '=', request.env.user.id)])
        compliance_count = request.env['construct.compliance'].sudo().search_count([('user_id', '=', request.env.user.id)])
        materials_count = request.env['product.product'].sudo().search_count([])
        purchase_count = request.env['material.purchase.requisition'].sudo().search_count([('requisition_type', '=', 'purchase'), ('task_user_ids', 'in', request.env.user.id)])
        in_picking_count = request.env['material.purchase.requisition'].sudo().search_count([('requisition_type', '=', 'internal'), ('task_user_ids', 'in', request.env.user.id)])
        scraps_count = request.env['material.purchase.requisition'].sudo().search_count([('requisition_type', '=', 'scrap'), ('task_user_ids', 'in', request.env.user.id)])

        data = {
            'job_costing_count': job_costing_count,
            'projects_count': projects_count,
            'tasks_count': tasks_count,
            'contractors_count': contractors_count,
            'bills_count': bills_count,
            'picking_count': picking_count,
            'inspection_count': inspection_count,
            'compliance_count': compliance_count,
            'materials_count': materials_count,
            'purchase_count': purchase_count,
            'in_picking_count': in_picking_count,
            'scraps_count': scraps_count,
            'project_state_data': project_state_data,
            'task_stage_data': task_stage_data,
            'project_invoice_yearly': project_invocie_yearly,
            'cost_type_estimated_amount_yearly': cost_type_data,
        }
        return data
