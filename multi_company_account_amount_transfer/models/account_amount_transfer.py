# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError

class AccountAmountTransfer(models.Model):
    _name = 'account.amount.transfer'
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = 'Account Amount Transfer'
    _rec_name = 'name'

    name = fields.Char(string='Name', default=lambda self: _("New"))
    ref = fields.Char(string='Reference')
    date = fields.Date(string='Date')
    journal_entry_ids = fields.One2many('account.move', 'account_amount_transfer_id', string='Journal Entries')
    entries_count = fields.Integer(string='Entries Count', compute='_compute_entry_ids', store=True)
    transfer_lines = fields.One2many(
        'account.amount.transfer.line',
        'transfer_id',
        string='Transfer Lines',
        copy=True,
        readonly=False,
    )
    state = fields.Selection(selection=[
        ('draft', 'Draft'),
        ('posted', 'Posted'),
        ('cancel', 'Cancelled'),
    ], string='Status', required=True, readonly=True, copy=False, tracking=True,
        default='draft')
    user_id = fields.Many2one('res.users', string='User', required=True, default=lambda self: self.env.user,
                              tracking=True)

    @api.depends('journal_entry_ids')
    def _compute_entry_ids(self):
        for entry in self:
            entry.entries_count = len(entry.journal_entry_ids)

    def check_journal_entry(self):
        journal_entries = self.journal_entry_ids.mapped('company_id')
        companies = self.transfer_lines.mapped('company_id')
        diff = list(set(companies).difference(journal_entries))
        if diff:
            return diff
        else:
            return False

    def post_internal_transfer(self):
        self.ensure_one()
        if self.state == 'draft':
            companies = self.transfer_lines.mapped('company_id')
            entries = {}
            entries_ids = []
            if not self.journal_entry_ids:
                for company in companies:
                    company_lines = self.transfer_lines.filtered(lambda line: line.company_id.id == company.id)
                    for line in company_lines:
                        if company.id not in entries:
                            vals = line.prepare_move_values()
                            entries[company.id] = vals
                        entry_line = line.prepare_move_line_values()
                        entries[company.id]['line_ids'].append((0, 0, entry_line))
                    entry = self.journal_entry_ids.create(vals)
                    entries_ids.append(entry.id)
                    entry.action_post()
            else:
                companies_dont_exist = self.check_journal_entry()
                if companies_dont_exist:
                    for company in companies_dont_exist:
                        company_lines = self.transfer_lines.filtered(lambda line: line.company_id.id == company.id)
                        for line in company_lines:
                            if company.id not in entries:
                                vals = line.prepare_move_values()
                                entries[company.id] = vals
                            entry_line = line.prepare_move_line_values()
                            entries[company.id]['line_ids'].append((0, 0, entry_line))
                        entry = self.journal_entry_ids.create(vals)
                        entries_ids.append(entry.id)
                for line in self.transfer_lines:
                    line_values = line.prepare_move_line_values()
                    if line.journal_item_id:
                        line.journal_item_id.with_context(check_move_validity=False).write(line_values)
                    else:
                        item = line_values
                        entry = self.journal_entry_ids.filtered(lambda journal_entry: journal_entry.company_id.id == line.company_id.id)
                        entry.with_context(check_move_validity=False).line_ids = [(0, 0, item)]
                for entry in self.journal_entry_ids:
                    entry.action_post()
            self.state = 'posted'

    def reset_to_draft(self):
        self.ensure_one()
        self.state = 'draft'
        for entry in self.journal_entry_ids:
            entry.button_draft()

    def cancel_entries(self):
        self.ensure_one()
        self.state = 'cancel'
        for entry in self.journal_entry_ids:
            entry.button_cancel()

    @api.model
    def _get_default_name(self):
        return self.env["ir.sequence"].next_by_code("account.amount.transfer")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self._get_default_name()
        return super().create(vals_list)

    def unlink(self):
        for transfer in self:
            if transfer.state != 'draft':
                raise UserError(_('You can not delete non draft record.'))
            transfer.journal_entry_ids.unlink()
        return super(AccountAmountTransfer, self).unlink()

    def copy(self):
        res = super(AccountAmountTransfer, self).copy()
        res.name = res._get_default_name()
        if res.journal_entry_ids:
            res.journal_entry_ids = False
        return res

    def action_view_journal_entries(self):
        action = self.env["ir.actions.actions"]._for_xml_id("account.action_move_journal_line")
        action['domain'] = [('id', 'in', self.journal_entry_ids.ids)]
        return action
