# Part of Softhealer Technologies.
from odoo import models, fields, api, exceptions, _

class Partner(models.Model):
    _inherit = "res.partner"

    visit_count = fields.Integer(string="Visit Counter", compute="_compute_visit_counter")
    # country_ids = fields.Many2many('res.country', string="Country Codes", help="Select the country codes of the clients")
    def _compute_visit_counter(self):
        for rec in self:
            rec.visit_count = self.env['visit.visit'].search_count([('partner_id', '=', rec.id)])

    def action_open_visits(self):
        return {
            'name': _('Visits'),
            'view_mode': 'kanban,tree,form',
            'res_model': 'visit.visit',
            'view_id': False,
            'type': 'ir.actions.act_window',
            'domain': [('partner_id', '=', self.id)],
        }