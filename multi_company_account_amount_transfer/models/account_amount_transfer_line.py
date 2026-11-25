# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError

class AccountAmountTransferLine(models.Model):
    _name = 'account.amount.transfer.line'
    _inherit = "analytic.mixin"
    _description = 'Account Amount Transfer Line'

    transfer_id = fields.Many2one('account.amount.transfer', string='Transfer ID')
    name = fields.Char(string='Label')
    date = fields.Date(string='Date', related='transfer_id.date')
    partner_id = fields.Many2one('res.partner', string='Partner', ondelete='restrict')
    company_id = fields.Many2one('res.company', string='Company')
    journal = fields.Many2one('account.journal', string='Journal')
    account = fields.Many2one('account.account', string='Account')
    debit = fields.Float(
        string='Debit',
        compute='_compute_debit_credit', inverse='_inverse_debit', store=True, precompute=True, copy=True,
    )
    credit = fields.Float(
        string='Credit',
        compute='_compute_debit_credit', inverse='_inverse_credit', store=True, precompute=True, copy=True,
    )
    balance = fields.Float(
        string='Balance',
        compute='_compute_balance', store=True, readonly=False, precompute=True,
    )
    journal_item_id = fields.One2many('account.move.line', 'account_amount_transfer_line_id', string='Journal Item')

    analytic_distribution = fields.Json(
    )
    currency_id = fields.Many2one('res.currency', string='Currency', related='company_id.currency_id')
    state = fields.Selection(
        string='Status',
        related='transfer_id.state',
        readonly=True,
    )

    @api.depends('transfer_id')
    def _compute_balance(self):
        for line in self:
            active_line_ids = [lid for lid in self.env.context.get('transfer_lines', []) if isinstance(lid, int)]
            existing_lines = self.env['account.amount.transfer.line'].browse(active_line_ids)
            outdated_lines = line.transfer_id.transfer_lines._origin
            new_lines = line.transfer_id.transfer_lines - line
            line.balance = -sum((existing_lines - outdated_lines + new_lines).mapped('balance'))

    @api.depends('balance')
    def _compute_debit_credit(self):
        for line in self:
            line.debit = line.balance if line.balance > 0.0 else 0.0
            line.credit = -line.balance if line.balance < 0.0 else 0.0

    @api.onchange('debit')
    def _inverse_debit(self):
        for line in self:
            if line.debit:
                line.credit = 0
            line.balance = line.debit - line.credit

    @api.onchange('credit')
    def _inverse_credit(self):
        for line in self:
            if line.credit:
                line.debit = 0
            line.balance = line.debit - line.credit

    @api.depends('account', 'partner_id', 'date')
    def _compute_analytic_tag_ids(self):
        for record in self:
            rec = self.env['account.analytic.default'].account_get(
                partner_id=record.partner_id.commercial_partner_id.id,
                account_id=record.account.id,
                user_id=record.env.uid,
                date=record.date,
                company_id=record.company_id.id
            )
            if rec:
                record.analytic_tag_ids = rec.analytic_tag_ids

    @api.depends('account', 'partner_id', 'date')
    def _compute_analytic_account_id(self):
        for record in self:
            rec = self.env['account.analytic.default'].account_get(
                partner_id=record.partner_id.commercial_partner_id.id,
                account_id=record.account.id,
                user_id=record.env.uid,
                date=record.date,
                company_id=record.company_id.id
            )
            if rec:
                record.analytic_account_id = rec.analytic_id

    @api.onchange('company_id')
    def _onchange_company(self):
        if self.account:
            self.account = False
        if self.journal:
            self.journal = False

    def prepare_move_values(self):
        values = {
            'ref': self.transfer_id.ref,
            'account_amount_transfer_id': self.transfer_id.id,
            'date': self.transfer_id.date,
            'journal_id': self.journal.id,
            'line_ids': [],
            'company_id': self.company_id.id,
            'currency_id': self.currency_id.id
        }
        return values

    def prepare_move_line_values(self):
        values = {
            'name': self.name,
            'partner_id': self.partner_id.id,
            'account_id': self.account.id,
            'debit': self.debit,
            'credit': self.credit,
            'account_amount_transfer_line_id': self.id,
            'analytic_distribution': self.analytic_distribution,
            'currency_id': self.currency_id.id,
        }
        return values

    @api.onchange('journal')
    def _onchange_journal(self):
        if self.journal:
            transfer_id = self.transfer_id
            company = transfer_id.transfer_lines.filtered(lambda line: line.company_id.id == self.company_id.id and
                                    line.id != self.id).mapped('journal')
            if len(company) > 1:
                raise UserError(_('You can not different journal than other lines of the same company.'))

    def unlink(self):
        for line in self:
            if line.journal_item_id:
                line.with_context(check_move_validity=False).journal_item_id.unlink()
        return super(AccountAmountTransferLine, self).unlink()
