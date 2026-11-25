from odoo import models, fields ,api


class HrContractOvertime(models.Model):
    _inherit = 'hr.contract'

    over_hour = fields.Monetary('Hour Wage',store=True,compute='get_hour_wage')
    over_day = fields.Monetary('Day Wage',store=True,compute='get_day_wage')
    can_request_overtime = fields.Selection([('no', 'No'), ('yes', 'Yes')], default='no')




    @api.depends('wage')
    def get_day_wage(self):
        for rec in self:
            if rec.wage:
                rec.over_day = rec.wage / (30)

    @api.depends('over_day')
    def get_hour_wage(self):
        for rec in self:
            if rec.over_day:
                rec.over_hour = rec.over_day / (8)
