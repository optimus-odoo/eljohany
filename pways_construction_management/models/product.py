
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import date, timedelta, datetime

################## Product ##################

class Product(models.Model):
    _inherit = 'product.product'

    boq_type = fields.Selection([('eqp_machine', 'Machinery / Material'), ('worker_resource', 'Worker / Resource'), ('work_cost_package', 'Work Cost Package'), ('subcontract', 'Subcontract')],  string='BOQ Type',)
    is_material = fields.Boolean(string='Material')

################## Maintenance Equipment ##################

class MaintenanceEquipment(models.Model):
    _inherit = 'maintenance.equipment'

    task_id = fields.Many2one('project.task', string='Project Task')
    product_id = fields.Many2one('product.product', string='Product')
    job_cost_id = fields.Many2one('job.costing', string='Job Cost Center')


################## HR ##################

class HrExpense(models.Model):
    _inherit = 'hr.expense'

    task_id = fields.Many2one('project.task', string='Task')
    project_id = fields.Many2one('project.project', related="task_id.project_id", string='Project')
    job_cost_id = fields.Many2one('job.costing', related="task_id.job_cost_id", string='Job Cost Center')

    def _get_default_expense_sheet_values(self):
        values = super(HrExpense, self)._get_default_expense_sheet_values()
        for val in values:
            val.update({
                'project_id': self.project_id.id if self.project_id else False,
                'task_id': self.task_id.id if self.task_id else False,
                'job_cost_id': self.job_cost_id.id if self.job_cost_id else False,
            })
        return values

        
    def _prepare_move_lines_vals(self):
        values = super(HrExpense, self)._prepare_move_lines_vals()
        values.update({
            'job_cost_id': self.job_cost_id.id if self.job_cost_id else False,
        })
        return values

class HrExpenseSheet(models.Model):
    _inherit = 'hr.expense.sheet'

    task_id = fields.Many2one('project.task', string='Task')
    project_id = fields.Many2one('project.project', related="task_id.project_id", string='Project',)
    job_cost_id = fields.Many2one('job.costing', related="task_id.job_cost_id", string='Job Cost Center')

    def _prepare_bills_vals(self):
        values = super(HrExpenseSheet, self)._prepare_bills_vals()
        values.update({
            'project_id': self.project_id.id if self.project_id else False,
            'task_id': self.task_id.id if self.task_id else False,
            'job_cost_id': self.job_cost_id.id if self.job_cost_id else False,
        })
        return values


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    dest_location_id = fields.Many2one('stock.location', string='Destination Location', groups='hr.group_hr_user')
    price_per_time = fields.Float(string='Salary/Time',)
    salary_period = fields.Selection(selection=[('hours', 'Hours'), ('days', 'Days'), ('months', 'Months')],  default="hours", string='Salary Period')

class HrEmployee(models.Model):
    _inherit = 'hr.department'

    dest_location_id = fields.Many2one('stock.location', string='Destination Location')

################## Project Task Type ##################

class ProjectTaskType(models.Model):
    _inherit = 'project.task.type'

    set_default = fields.Boolean('Default?')
    progress_bar = fields.Float(string='Progress (%)', help='Set your progress of the stage')
    is_progress_stage = fields.Boolean(string='Is Progress Bar', help='You can only see the progress ' 'if you enable this ')

    @api.constrains('progress_bar', 'sequence')
    def project_progress_bar(self):
        """The Constraints for the project Task Type Model"""
        for res in self:
            all_progress = res.search([('is_progress_stage', '=', True), ('id', '!=', res.id)])
            records = {}
            for rec in all_progress:
                records[rec.progress_bar] = rec.sequence
            if res.progress_bar in records.keys():
                raise UserError(_("Ensure that the progress is not duplicated."))
            for rec in res.env['project.task.type'].search([]).filtered(
                    lambda progress: progress.is_progress_stage == True and progress.id != res.id).mapped(
                'progress_bar'):
                value = [line for line in records if line == rec]
                if res.progress_bar < rec:
                    if float(res.sequence) >= records[value[0]]:
                        raise UserError(
                            _(" The progress in this stage must greater than that"
                              " of the other stages progress bars. Alternatively,"
                              " reassess the priority assigned to this stage."))
                    else:
                        continue
                else:
                    if float(res.sequence) < records[value[0]]:
                        raise UserError(
                            _(" The progress in this stage must less than that of"
                              " the other stages progress bars. Alternatively,"
                              " reassess the priority assigned to this stage."))
                    else:
                        continue
            if res.progress_bar > 100:
                raise UserError(_(" The progress must be less than or equal to 100"))

################## Res Partner ##################

class ResPartner(models.Model):
    _inherit = 'res.partner'

    is_contractor = fields.Boolean(string='Contractor')

################## Res Config Settings ##################

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    construct_start_date = fields.Datetime(config_parameter='pways_construction_management.construct_start_date', 
        string="Start Date",
        default=lambda self: datetime.now())
    construct_end_date = fields.Datetime(config_parameter='pways_construction_management.construct_end_date', 
        string="End Date",
        default=lambda self: datetime.now()+ timedelta(days=365))

