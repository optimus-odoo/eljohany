# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import UserError


class CommissionLine(models.Model):
    _name = 'commission.line'
    _description = 'Commission Line'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    name = fields.Char(default='New', copy=False, readonly=True)
    unique_key = fields.Char(required=True, copy=False, readonly=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('calculated', 'Calculated'),
        ('approved', 'Approved'),
        ('accrued', 'Accrued'),
        ('paid', 'Paid'),
        ('reversed', 'Reversed'),
        ('cancelled', 'Cancelled'),
    ], default='calculated', tracking=True)
    line_type = fields.Selection([
        ('commission', 'Commission'),
        ('adjustment', 'Adjustment'),
        ('clawback', 'Clawback'),
    ], default='commission', required=True)
    plan_id = fields.Many2one('commission.plan', required=True, index=True, ondelete='restrict')
    rule_id = fields.Many2one('commission.rule', required=True, index=True, ondelete='restrict')
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id', store=True, readonly=True)
    date = fields.Date(required=True, default=fields.Date.context_today, index=True)
    beneficiary_type = fields.Selection(related='rule_id.beneficiary_type', store=True, readonly=True)
    user_id = fields.Many2one('res.users', string='Salesperson/User', index=True)
    employee_id = fields.Many2one('hr.employee')
    partner_id = fields.Many2one('res.partner', string='Agent/Partner', index=True)
    sales_team_id = fields.Many2one('crm.team')
    customer_id = fields.Many2one('res.partner', string='Customer', index=True)
    product_id = fields.Many2one('product.product')
    invoice_id = fields.Many2one('account.move', string='Invoice/Credit Note', index=True, ondelete='cascade')
    invoice_line_id = fields.Many2one('account.move.line', string='Invoice Line', index=True, ondelete='cascade')
    payment_move_id = fields.Many2one('account.move', string='Payment Entry', index=True, ondelete='set null')
    partial_reconcile_id = fields.Many2one('account.partial.reconcile', string='Payment Match', index=True, ondelete='set null')
    sale_order_id = fields.Many2one('sale.order', string='Sales Order')
    base_amount = fields.Monetary(currency_field='currency_id')
    commission_rate = fields.Float(string='Rate (%)', digits='Discount')
    commission_amount = fields.Monetary(currency_field='currency_id', tracking=True)
    statement_id = fields.Many2one('commission.statement', ondelete='set null')
    reversed_line_id = fields.Many2one('commission.line', string='Reversed Commission Line')
    move_id = fields.Many2one('account.move', string='Accrual Entry', related='statement_id.move_id', store=True)
    note = fields.Text()

    _sql_constraints = [
        ('unique_commission_source', 'UNIQUE(unique_key)',
         'A commission line already exists for this plan, rule, source line, and beneficiary.'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('commission.line') or 'New'
        return super().create(vals_list)

    def action_approve(self):
        self.filtered(lambda line: line.state in ('draft', 'calculated')).write({'state': 'approved'})

    def action_cancel(self):
        blocked = self.filtered(lambda line: line.state in ('accrued', 'paid'))
        if blocked:
            raise UserError('Accrued or paid commission lines cannot be cancelled. Create an adjustment instead.')
        self.write({'state': 'cancelled'})

    def action_reset_to_calculated(self):
        self.filtered(lambda line: line.state in ('draft', 'cancelled')).write({'state': 'calculated'})

    def _make_unique_key(self, plan, rule, move_line, beneficiary_values):
        user_id = beneficiary_values.get('user_id') or 0
        partner_id = beneficiary_values.get('partner_id') or 0
        return '%s-%s-%s-%s-%s-%s' % (
            plan.id, rule.id, move_line.id,
            beneficiary_values.get('beneficiary_type') or 'none',
            user_id, partner_id)

    def _make_invoice_unique_key(self, plan, rule, move, beneficiary_values):
        user_id = beneficiary_values.get('user_id') or 0
        partner_id = beneficiary_values.get('partner_id') or 0
        return 'invoice-%s-%s-%s-%s-%s-%s' % (
            plan.id, rule.id, move.id,
            beneficiary_values.get('beneficiary_type') or 'none',
            user_id, partner_id)

    def _make_payment_unique_key(self, plan, rule, move, partial_reconcile, beneficiary_values):
        user_id = beneficiary_values.get('user_id') or 0
        partner_id = beneficiary_values.get('partner_id') or 0
        return 'payment-%s-%s-%s-%s-%s-%s-%s' % (
            plan.id, rule.id, move.id, partial_reconcile.id,
            beneficiary_values.get('beneficiary_type') or 'none',
            user_id, partner_id)
