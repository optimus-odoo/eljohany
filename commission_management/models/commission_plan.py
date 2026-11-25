# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class CommissionPlan(models.Model):
    _name = 'commission.plan'
    _description = 'Commission Plan'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'sequence, name'


    name = fields.Char(required=True, tracking=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('closed', 'Closed'),
    ], default='draft', tracking=True)
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company,
        tracking=True)
    currency_id = fields.Many2one(
        'res.currency', related='company_id.currency_id', store=True,
        readonly=True)
    date_start = fields.Date(required=True, tracking=True)
    date_end = fields.Date(tracking=True)
    trigger_type = fields.Selection([
        ('invoice_posted', 'Invoice Posted'),
        ('invoice_paid', 'Invoice Paid'),
        ('manual', 'Manual'),
    ], default='invoice_posted', required=True, tracking=True)
    base_type = fields.Selection([
        ('invoice_total', 'Invoice Total'),
        ('invoice_line_subtotal', 'Invoice Untaxed Amount (Legacy)'),
        ('invoice_untaxed', 'Invoice Untaxed Amount'),
        ('margin', 'Gross Margin'),
        ('quantity', 'Quantity'),
    ], default='invoice_total', required=True, tracking=True)
    payment_frequency = fields.Selection([
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('yearly', 'Yearly'),
        ('manual', 'Manual'),
    ], default='monthly', required=True)
    allow_rule_stacking = fields.Boolean(
        string='Allow Multiple Matching Rules',
        help='If disabled, only the first matching rule by sequence is applied.')
    rule_ids = fields.One2many('commission.rule', 'plan_id', string='Rules')
    line_ids = fields.One2many('commission.line', 'plan_id', string='Commission Lines')
    journal_id = fields.Many2one(
        'account.journal', string='Accrual Journal',
        domain="[('type', '=', 'general'), ('company_id', '=', company_id)]")
    expense_account_id = fields.Many2one(
        'account.account', string='Commission Expense Account',
        domain="[('deprecated', '=', False)]")
    liability_account_id = fields.Many2one(
        'account.account', string='Commission Liability Account',
        domain="[('deprecated', '=', False)]")
    notes = fields.Html()

    _sql_constraints = [
        ('date_check', 'CHECK(date_end IS NULL OR date_end >= date_start)',
         'The end date must be after the start date.'),
    ]

    @api.constrains('state', 'rule_ids')
    def _check_active_has_rules(self):
        for plan in self:
            if plan.state == 'active' and not plan.rule_ids:
                raise ValidationError('An active commission plan must have at least one rule.')

    def action_activate(self):
        for plan in self:
            if not plan.rule_ids:
                raise UserError('Please configure at least one commission rule before activation.')
            plan.state = 'active'

    def action_close(self):
        self.write({'state': 'closed'})

    def action_reset_to_draft(self):
        self.write({'state': 'draft'})

    def _is_effective_for_date(self, date):
        self.ensure_one()
        return (
            self.state == 'active'
            and self.date_start <= date
            and (not self.date_end or date <= self.date_end)
        )

    def _get_matching_rules(self, move):
        self.ensure_one()
        rules = self.rule_ids.filtered(lambda rule: rule.active and rule._matches_invoice(move))
        rules = rules.sorted(lambda rule: rule.sequence)
        if not self.allow_rule_stacking:
            rules = rules[:1]
        return rules

    def action_generate_commissions_for_invoices(self):
        active_ids = self.env.context.get('active_ids') or []
        moves = self.env['account.move'].browse(active_ids).filtered(
            lambda move: move.move_type in ('out_invoice', 'out_refund') and move.state == 'posted')
        if not moves:
            raise UserError('Please select posted customer invoices or credit notes.')
        for move in moves:
            move.action_generate_commission_lines()
