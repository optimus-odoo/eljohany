from odoo import fields, models, api
from odoo.addons.resource.models.utils import HOURS_PER_DAY


class EmployeeBonus(models.Model):
    _name = 'employee.overtime'
    _inherit = ['mail.thread', "mail.activity.mixin"]

    name = fields.Char(compute="get_employee_name")
    type = fields.Selection([
        ('employee', 'Employee'),
        ('department', 'Department'),
        ('all', 'All Employees')
    ], default='employee', required=True)
    employee_id = fields.Many2one(comodel_name="hr.employee", domain=[('contract_id.can_request_overtime', '=', 'yes')])
    no_of_days = fields.Float(default=0)
    department_id = fields.Many2one(comodel_name="hr.department")
    type_id = fields.Many2one(comodel_name="overtime.type", string="Bonus Type", required=True)
    date = fields.Date(required=True)
    bonus_amount = fields.Float(default=1)
    company_id = fields.Many2one(comodel_name="res.company", string='Company', default=lambda self: self.env.company)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('approve', 'Approved'),
        ('reject', 'Rejected'),
        ('cancel', 'Canceled')
    ], default="draft", string="Status", track_visibility="onchange")
    overtime_per = fields.Selection([('day', 'Days'), ('hour', 'Hours')], default="day", string="Per",
                                    track_visibility="onchange")
    description = fields.Text()
    rate = fields.Float(related='type_id.rate', default=1)
    overtime_responsible = fields.Many2one(related='employee_id.overtime_responsible',
                                           comodel_name='hr.employee',
                                           string='Overtime Responsible',
                                           required=False)

    @api.onchange('no_of_days', 'employee_id', 'rate')
    def onchange_no_of_days(self):
        for rec in self:
            if rec.type == 'employee' and rec.employee_id and rec.employee_id.contract_id and rec.employee_id.contract_id.can_request_overtime:
                if rec.overtime_per == 'day' and rec.no_of_days > 0:
                    if rec.employee_id.contract_id.over_day > 0:
                        rec.bonus_amount = rec.employee_id.contract_id.over_day * rec.no_of_days * rec.rate
                    else:
                        rec.bonus_amount = (rec.employee_id.contract_id.wage / 30) * rec.no_of_days * rec.rate
                elif rec.overtime_per == 'hour' and rec.no_of_days > 0:
                    if rec.employee_id.contract_id.over_hour > 0:
                        rec.bonus_amount = rec.employee_id.contract_id.over_hour * rec.no_of_days * rec.rate
                    else:
                        rec.bonus_amount = ((
                                                        rec.employee_id.contract_id.wage / 30) / HOURS_PER_DAY) * rec.no_of_days * rec.rate

    @api.onchange('employee_id', 'date')
    def get_employee_name(self):
        for rec in self:
            name = ''
            if rec.type == 'employee' and rec.employee_id:
                rec.department_id = rec.employee_id.department_id.id
                name = rec.employee_id.name + ' '
            elif rec.type == 'department' and rec.department_id:
                name = rec.department_id.name + ' '
            elif rec.type == 'all':
                name = "Employees "
            name += rec.date and str(rec.date) or ''
            rec.name = name

    def action_approve(self):
        for rec in self:
            rec.state = "approve"

    def action_reject(self):
        for rec in self:
            rec.state = "reject"


class EmployeeCustomOverTime(models.Model):
    _inherit = 'hr.employee'

    overtime_responsible = fields.Many2one(
        comodel_name='hr.employee',
        string='',
        required=False)
