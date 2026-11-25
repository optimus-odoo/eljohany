from datetime import date
from odoo import models, fields, api, _

class VehicleEquipmentRequest(models.Model):
    _name = 'vehicle.equipment.request'
    _description = 'Vehicle Equipment Request'
    _order = "id desc"
    
    name = fields.Char()
    hours = fields.Float(default="1.0")
    unit_price = fields.Float()
    description = fields.Text()
    request_type = fields.Selection(selection=[('vehicle','Vehicle'),('equipment','Equipment')], string='Type', default='vehicle')
    equipment_ids = fields.Many2many('maintenance.equipment', string="Equipments")
    fleet_ids = fields.Many2many('fleet.vehicle', string="Fleet")
    task_id = fields.Many2one('project.task', string="Task")
    state = fields.Selection(selection=[('draft', 'Draft'), ('confirm', 'Confirmed'), ('cancel', 'Canceled')], string='State', tracking=True, default='draft')
    bill_count = fields.Integer(compute='_compute_bill_count')

    def action_draft(self):
        for rec in self:
            rec.write({'state': 'draft'})

    def action_confirm(self):
        for rec in self:
            rec.write({'state': 'confirm'})

    def action_cancel(self):
        for rec in self:
            rec.write({'state': 'cancel'})

    @api.model
    def create(self, vals):
        if vals.get('request_type') == 'vehicle':
            prefix = 'FLT/REQ/'
        else:
            prefix = 'EQP/REQ/'
        seq_number = self.env['ir.sequence'].next_by_code('vehicle.equipment.request') or 'New'
        vals['name'] = f"{prefix}{seq_number}"
        return super(VehicleEquipmentRequest, self).create(vals)

    def write(self, vals):
        if 'request_type' in vals:
            del vals['request_type']
        return super(VehicleEquipmentRequest, self).write(vals)

    def action_create_bill(self):
        journal = self.env['account.journal'].sudo().search([('type', '=', 'purchase')], limit=1)
        line_vals = []

        for rec in self:
            analytic_distribution = {str(rec.task_id.project_id.analytic_account_id.id): 100}
            line_val = {
                'product_id': False,
                'name': rec.name,
                'quantity': rec.hours,
                'price_unit': rec.unit_price,
                'job_cost_id': rec.task_id.job_cost_id.id if rec.task_id.job_cost_id.id else False,
                'analytic_distribution': analytic_distribution if analytic_distribution else False,
            }
            line_vals.append((0, 0, line_val))

            vals = {
                'move_type': 'in_invoice',
                'invoice_date': date.today(),
                'journal_id': journal.id,
                'partner_id': rec.task_id.partner_id.id,
                'invoice_line_ids': line_vals,
                'req_vehcle_equipment_id': rec.id,
                'project_id': rec.task_id.project_id.id if rec.task_id.project_id else False,
                'task_id': rec.task_id.id if rec.task_id else False,
                'job_cost_id': rec.task_id.job_cost_id.id if rec.task_id.job_cost_id.id else False,
            }
            self.env['account.move'].sudo().create(vals)

    def open_bills_action(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Bills',
            'res_model': 'account.move',
            'domain': [('req_vehcle_equipment_id', '=', self.id)],
            'view_mode': 'tree,form',
            'target': 'current',
        }

    def _compute_bill_count(self):
        move = self.env['account.move']
        for rec in self:
            rec.bill_count = move.search_count([('req_vehcle_equipment_id', '=', self.id)])