# -*- coding: utf-8 -*-

import calendar

from odoo import api, fields, models
from odoo.exceptions import UserError


class CommissionStatement(models.Model):
    _name = 'commission.statement'
    _description = 'Commission Statement'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'period_start desc, id desc'

    name = fields.Char(default='New', copy=False, readonly=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
        ('accrued', 'Accrued'),
        ('paid', 'Paid'),
        ('cancelled', 'Cancelled'),
    ], default='draft', tracking=True)
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company,
        tracking=True)
    currency_id = fields.Many2one(related='company_id.currency_id', store=True, readonly=True)
    plan_id = fields.Many2one('commission.plan', required=True)
    beneficiary_type = fields.Selection([
        ('user', 'Employee/User'),
        ('partner', 'External Partner/Agent'),
    ], default='user', required=True)
    user_id = fields.Many2one('res.users', string='Salesperson/User')
    employee_id = fields.Many2one('hr.employee')
    partner_id = fields.Many2one('res.partner', string='External Partner/Agent')
    period_start = fields.Date(required=True, default=lambda self: self._default_period_start())
    period_end = fields.Date(required=True, default=lambda self: self._default_period_end())
    line_ids = fields.One2many('commission.line', 'statement_id', string='Commission Lines')
    amount_total = fields.Monetary(compute='_compute_amount_total', store=True, currency_field='currency_id')
    move_id = fields.Many2one('account.move', string='Accrual Entry', readonly=True)
    notes = fields.Text()

    _sql_constraints = [
        ('period_check', 'CHECK(period_end >= period_start)',
         'The period end date must be after the period start date.'),
    ]

    def _get_month_period(self, date_value):
        last_day = calendar.monthrange(date_value.year, date_value.month)[1]
        period_start = date_value.replace(day=1)
        period_end = date_value.replace(day=last_day)
        return period_start, period_end

    def _default_period_start(self):
        today = fields.Date.context_today(self)
        return self._get_month_period(today)[0]

    def _default_period_end(self):
        today = fields.Date.context_today(self)
        return self._get_month_period(today)[1]

    @api.onchange('period_start')
    def _onchange_period_start(self):
        for statement in self:
            if statement.period_start:
                statement.period_start, statement.period_end = statement._get_month_period(
                    statement.period_start)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('commission.statement') or 'New'
            if vals.get('period_start'):
                period_start, period_end = self._get_month_period(
                    fields.Date.to_date(vals['period_start']))
                vals['period_start'] = period_start
                vals['period_end'] = period_end
        statements = super().create(vals_list)
        return statements

    def write(self, vals):
        sync_fields = {
            'company_id', 'plan_id', 'beneficiary_type', 'user_id', 'partner_id',
            'period_start', 'period_end',
        }
        should_sync = bool(sync_fields & set(vals))
        if should_sync:
            self.filtered(lambda statement: statement.state == 'draft').line_ids.write({'statement_id': False})
        if vals.get('period_start'):
            period_start, period_end = self._get_month_period(
                fields.Date.to_date(vals['period_start']))
            vals['period_start'] = period_start
            vals['period_end'] = period_end
        res = super().write(vals)
        return res

    @api.depends('line_ids.commission_amount')
    def _compute_amount_total(self):
        for statement in self:
            statement.amount_total = sum(statement.line_ids.mapped('commission_amount'))

    def _has_required_statement_filters(self):
        self.ensure_one()
        if not self.plan_id or not self.period_start or not self.period_end:
            return False
        if self.beneficiary_type == 'partner':
            return bool(self.partner_id)
        return bool(self.user_id)

    def _generate_invoice_commissions_for_period(self):
        for statement in self:
            if not statement._has_required_statement_filters():
                continue
            Move = self.env['account.move'].sudo()
            if statement.plan_id.trigger_type == 'invoice_paid':
                moves = statement._get_paid_candidate_moves()
            else:
                moves = Move.search(statement._get_candidate_move_domain())
                credit_notes = Move.search(statement._get_credit_note_candidate_domain())
                moves |= credit_notes
            period_target_totals = statement._get_period_target_totals(moves)
            context = {
                'commission_plan_id': statement.plan_id.id,
                'commission_use_statement_dates': True,
                'commission_skip_source_fallback': True,
                'commission_target_period_start': statement.period_start,
                'commission_target_period_end': statement.period_end,
                'commission_period_target_totals': period_target_totals,
                'commission_payment_period_start': statement.period_start,
                'commission_payment_period_end': statement.period_end,
            }
            if statement.beneficiary_type == 'partner':
                context['commission_target_partner_id'] = statement.partner_id.id
            else:
                context['commission_target_user_id'] = statement.user_id.id
            moves.with_context(**context).action_generate_commission_lines()

    def _get_paid_candidate_moves(self):
        self.ensure_one()
        self.env.cr.execute("""
            SELECT DISTINCT move_id
              FROM (
                    SELECT aml.move_id
                      FROM account_partial_reconcile apr
                      JOIN account_move_line aml
                        ON aml.id = apr.debit_move_id
                      JOIN account_move am
                        ON am.id = aml.move_id
                     WHERE apr.max_date >= %s
                       AND apr.max_date <= %s
                       AND am.company_id = %s
                       AND am.move_type IN ('out_invoice', 'out_refund')
                       AND am.state = 'posted'
                    UNION
                    SELECT aml.move_id
                      FROM account_partial_reconcile apr
                      JOIN account_move_line aml
                        ON aml.id = apr.credit_move_id
                      JOIN account_move am
                        ON am.id = aml.move_id
                     WHERE apr.max_date >= %s
                       AND apr.max_date <= %s
                       AND am.company_id = %s
                       AND am.move_type IN ('out_invoice', 'out_refund')
                       AND am.state = 'posted'
              ) paid_moves
        """, (
            self.period_start, self.period_end, self.company_id.id,
            self.period_start, self.period_end, self.company_id.id,
        ))
        move_ids = [row[0] for row in self.env.cr.fetchall()]
        moves = self.env['account.move'].sudo().browse(move_ids).filtered(
            lambda move: move.company_id == self.company_id
            and move.move_type in ('out_invoice', 'out_refund')
            and move.state == 'posted'
        )
        return self._filter_paid_candidate_moves_by_beneficiary(moves)

    def _filter_paid_candidate_moves_by_beneficiary(self, moves):
        self.ensure_one()
        relevant_rules = self.plan_id.rule_ids.filtered(lambda rule: rule.active)
        if self.beneficiary_type == 'partner':
            partner_rules = relevant_rules.filtered(
                lambda rule: rule.beneficiary_type == 'partner'
                and rule.partner_id == self.partner_id)
            return moves if partner_rules else self.env['account.move']

        specific_user_rules = relevant_rules.filtered(
            lambda rule: rule.beneficiary_type == 'specific_user'
            and rule.user_id == self.user_id)
        if specific_user_rules:
            return moves

        salesperson_rules = relevant_rules.filtered(lambda rule: rule.beneficiary_type == 'salesperson')
        team_leader_rules = relevant_rules.filtered(lambda rule: rule.beneficiary_type == 'team_leader')
        if salesperson_rules and team_leader_rules:
            return moves.filtered(
                lambda move: move.invoice_user_id == self.user_id
                or move.team_id.user_id == self.user_id
                or move.reversed_entry_id.invoice_user_id == self.user_id
                or move.reversed_entry_id.team_id.user_id == self.user_id
            )
        if salesperson_rules:
            return moves.filtered(
                lambda move: move.invoice_user_id == self.user_id
                or move.reversed_entry_id.invoice_user_id == self.user_id
            )
        if team_leader_rules:
            return moves.filtered(
                lambda move: move.team_id.user_id == self.user_id
                or move.reversed_entry_id.team_id.user_id == self.user_id
            )
        return self.env['account.move']

    def _get_period_target_totals(self, moves):
        self.ensure_one()
        totals = {}
        invoice_moves = moves.filtered(lambda move: move.move_type == 'out_invoice' and move.state == 'posted')
        target_rules = self.plan_id.rule_ids.filtered(
            lambda rule: rule.active and rule._has_target_thresholds())
        if not invoice_moves or not target_rules:
            return totals
        for rule in target_rules:
            period_total = 0.0
            beneficiary_values = {
                'user_id': self.user_id.id if self.beneficiary_type == 'user' else False,
                'partner_id': self.partner_id.id if self.beneficiary_type == 'partner' else False,
            }
            for move in invoice_moves:
                if not rule._matches_invoice(move):
                    continue
                candidate_beneficiary = rule._get_beneficiary_values(move)
                if (
                    (beneficiary_values.get('user_id') or False) != (candidate_beneficiary.get('user_id') or False)
                    or (beneficiary_values.get('partner_id') or False) != (candidate_beneficiary.get('partner_id') or False)
                ):
                    continue
                if self.plan_id.trigger_type == 'invoice_paid':
                    for event in move.with_context(
                        commission_payment_period_start=self.period_start,
                        commission_payment_period_end=self.period_end,
                    )._get_commission_payment_events():
                        period_total += move._get_paid_commission_base_amount(rule, event['amount'])
                else:
                    period_total += rule._get_base_amount(move)
            rule_with_period = rule.with_context(
                commission_target_period_start=self.period_start,
                commission_target_period_end=self.period_end,
            )
            totals[rule_with_period._get_period_target_context_key(
                invoice_moves[0],
                beneficiary_values,
            )] = period_total
        return totals

    def _get_candidate_move_domain(self):
        self.ensure_one()
        domain = [
            ('company_id', '=', self.company_id.id),
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('invoice_date', '>=', self.period_start),
            ('invoice_date', '<=', self.period_end),
        ]
        relevant_rules = self.plan_id.rule_ids.filtered(lambda rule: rule.active)
        if self.beneficiary_type == 'partner':
            partner_rules = relevant_rules.filtered(
                lambda rule: rule.beneficiary_type == 'partner'
                and rule.partner_id == self.partner_id)
            return domain if partner_rules else [('id', '=', 0)]

        specific_user_rules = relevant_rules.filtered(
            lambda rule: rule.beneficiary_type == 'specific_user'
            and rule.user_id == self.user_id)
        if specific_user_rules:
            return domain

        salesperson_rules = relevant_rules.filtered(lambda rule: rule.beneficiary_type == 'salesperson')
        team_leader_rules = relevant_rules.filtered(lambda rule: rule.beneficiary_type == 'team_leader')
        if salesperson_rules and team_leader_rules:
            return domain + [
                '|', '|', '|',
                ('invoice_user_id', '=', self.user_id.id),
                ('reversed_entry_id.invoice_user_id', '=', self.user_id.id),
                ('team_id.user_id', '=', self.user_id.id),
                ('reversed_entry_id.team_id.user_id', '=', self.user_id.id),
            ]
        if salesperson_rules:
            return domain + [
                '|',
                ('invoice_user_id', '=', self.user_id.id),
                ('reversed_entry_id.invoice_user_id', '=', self.user_id.id),
            ]
        if team_leader_rules:
            return domain + [
                '|',
                ('team_id.user_id', '=', self.user_id.id),
                ('reversed_entry_id.team_id.user_id', '=', self.user_id.id),
            ]
        return [('id', '=', 0)]

    def _get_credit_note_candidate_domain(self):
        self.ensure_one()
        relevant_rules = self.plan_id.rule_ids.filtered(lambda rule: rule.active)
        if not relevant_rules:
            return [('id', '=', 0)]
        domain = [
            ('company_id', '=', self.company_id.id),
            ('move_type', '=', 'out_refund'),
            ('state', '=', 'posted'),
            ('invoice_date', '>=', self.period_start),
            ('invoice_date', '<=', self.period_end),
        ]
        if self.beneficiary_type == 'partner':
            partner_rules = relevant_rules.filtered(
                lambda rule: rule.beneficiary_type == 'partner'
                and rule.partner_id == self.partner_id)
            return domain if partner_rules else [('id', '=', 0)]

        specific_user_rules = relevant_rules.filtered(
            lambda rule: rule.beneficiary_type == 'specific_user'
            and rule.user_id == self.user_id)
        if specific_user_rules:
            return domain

        salesperson_rules = relevant_rules.filtered(lambda rule: rule.beneficiary_type == 'salesperson')
        team_leader_rules = relevant_rules.filtered(lambda rule: rule.beneficiary_type == 'team_leader')
        if salesperson_rules and team_leader_rules:
            return domain + [
                '|', '|',
                ('invoice_user_id', '=', self.user_id.id),
                ('reversed_entry_id.invoice_user_id', '=', self.user_id.id),
                ('reversed_entry_id.team_id.user_id', '=', self.user_id.id),
            ]
        if salesperson_rules:
            return domain + [
                '|',
                ('invoice_user_id', '=', self.user_id.id),
                ('reversed_entry_id.invoice_user_id', '=', self.user_id.id),
            ]
        if team_leader_rules:
            return domain + [
                ('reversed_entry_id.team_id.user_id', '=', self.user_id.id),
            ]
        return [('id', '=', 0)]

    def _get_available_line_domain(self):
        self.ensure_one()
        domain = [
            ('plan_id', '=', self.plan_id.id),
            ('company_id', '=', self.company_id.id),
            ('date', '>=', self.period_start),
            ('date', '<=', self.period_end),
            ('state', 'in', ('calculated', 'approved')),
            ('statement_id', '=', False),
        ]
        if self.plan_id.trigger_type == 'invoice_paid':
            domain.append(('partial_reconcile_id', '!=', False))
        if self.beneficiary_type == 'partner':
            domain.append(('partner_id', '=', self.partner_id.id))
        else:
            domain.append(('user_id', '=', self.user_id.id))
        return domain

    def _sync_lines_from_registered_invoices(self):
        for statement in self:
            if statement.state != 'draft' or not statement._has_required_statement_filters():
                continue
            statement.line_ids.write({'statement_id': False})
            statement._generate_invoice_commissions_for_period()
            lines = self.env['commission.line'].search(statement._get_available_line_domain())
            lines.write({'statement_id': statement.id})

    def action_calculate_from_registered_invoices(self):
        self._sync_lines_from_registered_invoices()

    def action_submit(self):
        for statement in self:
            statement._sync_lines_from_registered_invoices()
            if not statement.line_ids:
                raise UserError('No commission lines were calculated from registered invoices for this statement period and beneficiary.')
            statement.state = 'submitted'

    def action_approve(self):
        for statement in self:
            statement.line_ids.filtered(lambda line: line.state == 'calculated').action_approve()
            statement.state = 'approved'

    def action_post_accrual(self):
        for statement in self:
            if statement.state != 'approved':
                raise UserError('Only approved commission statements can be accrued.')
            if statement.move_id:
                raise UserError('This commission statement already has an accrual entry.')
            plan = statement.plan_id
            if not plan.journal_id or not plan.expense_account_id or not plan.liability_account_id:
                raise UserError('Configure accrual journal, expense account, and liability account on the plan.')
            amount = statement.amount_total
            if not amount:
                raise UserError('Cannot accrue a zero amount statement.')
            debit = amount if amount > 0 else 0.0
            credit = -amount if amount < 0 else 0.0
            move = self.env['account.move'].create({
                'move_type': 'entry',
                'company_id': statement.company_id.id,
                'journal_id': plan.journal_id.id,
                'date': fields.Date.context_today(self),
                'ref': statement.name,
                'line_ids': [
                    (0, 0, {
                        'name': statement.name,
                        'account_id': plan.expense_account_id.id,
                        'debit': debit,
                        'credit': credit,
                    }),
                    (0, 0, {
                        'name': statement.name,
                        'account_id': plan.liability_account_id.id,
                        'debit': credit,
                        'credit': debit,
                    }),
                ],
            })
            move.action_post()
            statement.move_id = move.id
            statement.line_ids.write({'state': 'accrued'})
            statement.state = 'accrued'

    def action_mark_paid(self):
        for statement in self:
            if statement.state not in ('approved', 'accrued'):
                raise UserError('Only approved or accrued statements can be marked paid.')
            statement.line_ids.write({'state': 'paid'})
            statement.state = 'paid'

    def action_cancel(self):
        for statement in self:
            if statement.state in ('accrued', 'paid'):
                raise UserError('Accrued or paid statements cannot be cancelled.')
            statement.line_ids.write({'statement_id': False})
            statement.state = 'cancelled'

    def action_reset_to_draft(self):
        for statement in self:
            if statement.state in ('accrued', 'paid'):
                raise UserError('Accrued or paid statements cannot be reset.')
            statement.state = 'draft'

    def action_view_lines(self):
        self.ensure_one()
        action = self.env.ref('commission_management.action_commission_line').read()[0]
        action['domain'] = [('statement_id', '=', self.id)]
        action['context'] = {'default_statement_id': self.id}
        return action
