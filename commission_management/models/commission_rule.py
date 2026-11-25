# -*- coding: utf-8 -*-

import calendar
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class CommissionRule(models.Model):
    _name = 'commission.rule'
    _description = 'Commission Rule'
    _order = 'plan_id, sequence, id'

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    plan_id = fields.Many2one('commission.plan', required=True, ondelete='cascade')
    company_id = fields.Many2one(related='plan_id.company_id', store=True, readonly=True)
    currency_id = fields.Many2one(related='plan_id.currency_id', store=True, readonly=True)
    calculation_method = fields.Selection([
        ('percentage', 'Percentage'),
        ('fixed', 'Fixed Amount'),
        ('tier', 'Tiered'),
    ], default='percentage', required=True)
    rate = fields.Float(string='Rate (%)', digits='Discount')
    fixed_amount = fields.Monetary(currency_field='currency_id')
    tier_mode = fields.Selection([
        ('matched', 'Matched Tier'),
        ('progressive', 'Progressive Tiers'),
    ], default='matched')
    tier_ids = fields.One2many('commission.tier', 'rule_id', string='Tiers')
    beneficiary_type = fields.Selection([
        ('salesperson', 'Invoice Salesperson'),
        ('specific_user', 'Specific User'),
        ('team_leader', 'Sales Team Leader'),
        ('partner', 'External Partner/Agent'),
    ], default='salesperson', required=True)
    user_id = fields.Many2one('res.users', string='Specific User')
    partner_id = fields.Many2one('res.partner', string='External Partner/Agent')
    employee_id = fields.Many2one(
        'hr.employee', string='Employee',
        compute='_compute_employee_id', store=True, readonly=False)
    team_id = fields.Many2one('crm.team', string='Sales Team')
    product_id = fields.Many2one('product.product')
    product_categ_id = fields.Many2one('product.category', string='Product Category')
    customer_id = fields.Many2one('res.partner', string='Customer')
    customer_tag_ids = fields.Many2many('res.partner.category', string='Customer Tags')
    min_base_amount = fields.Monetary(currency_field='currency_id')
    max_base_amount = fields.Monetary(currency_field='currency_id')
    min_margin_percent = fields.Float(
        help='Minimum gross margin percentage required. Only applies when product cost is available.')
    cap_amount = fields.Monetary(
        string='Maximum Commission Amount', currency_field='currency_id',
        help='Optional cap per source invoice.')
    target_min_amount = fields.Monetary(
        string='Min Period Target', currency_field='currency_id',
        help='Minimum cumulative achievement in the plan period before this rule applies.')
    target_max_amount = fields.Monetary(
        string='Max Period Target', currency_field='currency_id',
        help='Maximum cumulative achievement in the plan period for which this rule still applies.')

    @api.depends('user_id')
    def _compute_employee_id(self):
        employees = self.env['hr.employee'].sudo()
        for rule in self:
            rule.employee_id = employees.search([('user_id', '=', rule.user_id.id)], limit=1) if rule.user_id else False

    @api.constrains('calculation_method', 'rate', 'fixed_amount', 'tier_ids')
    def _check_calculation_values(self):
        for rule in self:
            if rule.calculation_method == 'percentage' and rule.rate < 0:
                raise ValidationError('Commission rate cannot be negative.')
            if rule.calculation_method == 'fixed' and rule.fixed_amount < 0:
                raise ValidationError('Fixed commission cannot be negative.')
            if rule.calculation_method == 'tier' and not rule.tier_ids:
                raise ValidationError('Tiered commission rules require at least one tier.')

    @api.constrains('target_min_amount', 'target_max_amount')
    def _check_target_amounts(self):
        for rule in self:
            if rule.target_min_amount < 0 or rule.target_max_amount < 0:
                raise ValidationError('Target amounts cannot be negative.')
            if (
                rule.target_min_amount
                and rule.target_max_amount
                and rule.target_max_amount < rule.target_min_amount
            ):
                raise ValidationError('The maximum target must be greater than or equal to the minimum target.')

    @api.constrains('beneficiary_type', 'user_id', 'partner_id')
    def _check_beneficiary(self):
        for rule in self:
            if rule.beneficiary_type == 'specific_user' and not rule.user_id:
                raise ValidationError('Specific user rules require a user.')
            if rule.beneficiary_type == 'partner' and not rule.partner_id:
                raise ValidationError('Partner rules require an external partner/agent.')

    def _get_invoice_product_lines(self, move):
        return move.invoice_line_ids.filtered(lambda line: not line.display_type and line.product_id)

    def _get_source_move(self, move):
        self.ensure_one()
        if hasattr(move, '_get_commission_source_move'):
            return move._get_commission_source_move()
        return move.reversed_entry_id if move.move_type == 'out_refund' and move.reversed_entry_id else move

    def _get_matching_product_lines(self, move):
        self.ensure_one()
        product_lines = self._get_invoice_product_lines(move)
        if self.product_id:
            product_lines = product_lines.filtered(lambda line: line.product_id == self.product_id)
        if self.product_categ_id:
            categories = self.env['product.category'].search([
                ('id', 'child_of', self.product_categ_id.id),
            ])
            product_lines = product_lines.filtered(lambda line: line.product_id.categ_id in categories)
        return product_lines

    def _has_product_filter(self):
        self.ensure_one()
        return bool(self.product_id or self.product_categ_id)

    def _matches_product_filter(self, move):
        if not self._has_product_filter():
            return True
        return bool(self._get_matching_product_lines(move))

    def _matches_invoice(self, move):
        self.ensure_one()
        source_move = self._get_source_move(move)
        if move.company_id != self.company_id:
            return False
        if self.team_id and source_move.team_id != self.team_id:
            return False
        if self.customer_id and source_move.commercial_partner_id != self.customer_id.commercial_partner_id:
            return False
        if self.customer_tag_ids and not (source_move.partner_id.category_id & self.customer_tag_ids):
            return False
        if not self._matches_product_filter(move):
            return False
        base_amount = self._get_base_amount(move)
        if self.min_base_amount and base_amount < self.min_base_amount:
            return False
        if self.max_base_amount and base_amount > self.max_base_amount:
            return False
        if self.min_margin_percent:
            margin_percent = self._get_margin_percent(move)
            if margin_percent < self.min_margin_percent:
                return False
        return True

    def _get_beneficiary_values(self, move):
        self.ensure_one()
        user = False
        partner = False
        employee = False
        source_move = self._get_source_move(move)
        if self.beneficiary_type == 'salesperson':
            user = move.invoice_user_id or source_move.invoice_user_id
        elif self.beneficiary_type == 'specific_user':
            user = self.user_id
        elif self.beneficiary_type == 'team_leader':
            user = move.team_id.user_id or source_move.team_id.user_id
        elif self.beneficiary_type == 'partner':
            partner = self.partner_id
        if user:
            employee = self.employee_id or self.env['hr.employee'].sudo().search(
                [('user_id', '=', user.id)], limit=1)
        return {
            'beneficiary_type': self.beneficiary_type,
            'user_id': user.id if user else False,
            'employee_id': employee.id if employee else False,
            'partner_id': partner.id if partner else False,
        }

    def _get_move_commission_date(self, move):
        self.ensure_one()
        return move.invoice_date or move.date or fields.Date.context_today(move)

    def _has_target_thresholds(self):
        self.ensure_one()
        return bool(self.target_min_amount or self.target_max_amount)

    def _get_target_period_range(self, move_date):
        self.ensure_one()
        period_start = self.env.context.get('commission_target_period_start')
        period_end = self.env.context.get('commission_target_period_end')
        if period_start and period_end:
            return (
                fields.Date.to_date(period_start),
                fields.Date.to_date(period_end),
            )
        frequency = self.plan_id.payment_frequency
        if frequency == 'weekly':
            period_start = move_date - timedelta(days=move_date.weekday())
            period_end = period_start + timedelta(days=6)
        elif frequency == 'quarterly':
            start_month = ((move_date.month - 1) // 3) * 3 + 1
            end_month = start_month + 2
            period_start = move_date.replace(month=start_month, day=1)
            period_end = move_date.replace(
                month=end_month,
                day=calendar.monthrange(move_date.year, end_month)[1],
            )
        elif frequency == 'yearly':
            period_start = move_date.replace(month=1, day=1)
            period_end = move_date.replace(month=12, day=31)
        elif frequency == 'manual':
            period_start = self.plan_id.date_start
            period_end = self.plan_id.date_end or move_date
        else:
            period_start = move_date.replace(day=1)
            period_end = move_date.replace(
                day=calendar.monthrange(move_date.year, move_date.month)[1],
            )
        period_start = max(period_start, self.plan_id.date_start)
        if self.plan_id.date_end:
            period_end = min(period_end, self.plan_id.date_end)
        if period_end < period_start:
            period_end = period_start
        return period_start, period_end

    def _is_same_beneficiary(self, beneficiary_values, candidate_values):
        self.ensure_one()
        return (
            (beneficiary_values.get('user_id') or False) == (candidate_values.get('user_id') or False)
            and (beneficiary_values.get('partner_id') or False) == (candidate_values.get('partner_id') or False)
        )

    def _get_period_target_cache_key(self, move, beneficiary_values):
        self.ensure_one()
        move_date = self._get_move_commission_date(move)
        period_start, period_end = self._get_target_period_range(move_date)
        return (
            self.id,
            move.company_id.id,
            period_start,
            period_end,
            beneficiary_values.get('user_id') or False,
            beneficiary_values.get('partner_id') or False,
        )

    def _get_period_target_context_key(self, move, beneficiary_values):
        self.ensure_one()
        period_start, period_end = self._get_target_period_range(self._get_move_commission_date(move))
        return '%s|%s|%s|%s|%s|%s' % (
            self.id,
            move.company_id.id,
            period_start,
            period_end,
            beneficiary_values.get('user_id') or 0,
            beneficiary_values.get('partner_id') or 0,
        )

    def _get_period_target_amount(self, move, beneficiary_values, target_total_cache=None):
        self.ensure_one()
        context_totals = self.env.context.get('commission_period_target_totals') or {}
        context_key = self._get_period_target_context_key(move, beneficiary_values)
        if context_key in context_totals:
            return context_totals[context_key]
        cache_key = self._get_period_target_cache_key(move, beneficiary_values)
        if target_total_cache is not None and cache_key in target_total_cache:
            return target_total_cache[cache_key]
        move_date = self._get_move_commission_date(move)
        period_start, period_end = self._get_target_period_range(move_date)
        candidate_moves = self.env['account.move'].sudo().search([
            ('company_id', '=', move.company_id.id),
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('invoice_date', '>=', period_start),
            ('invoice_date', '<=', period_end),
        ])
        period_total = 0.0
        for candidate_move in candidate_moves:
            if not self._matches_invoice(candidate_move):
                continue
            candidate_beneficiary = self._get_beneficiary_values(candidate_move)
            if not self._is_same_beneficiary(beneficiary_values, candidate_beneficiary):
                continue
            period_total += self._get_base_amount(candidate_move)
        if target_total_cache is not None:
            target_total_cache[cache_key] = period_total
        return period_total

    def _matches_target_thresholds(self, move, beneficiary_values, target_total_cache=None):
        self.ensure_one()
        if not self._has_target_thresholds():
            return True
        if move.move_type == 'out_refund':
            return True
        period_total = self._get_period_target_amount(
            move, beneficiary_values, target_total_cache=target_total_cache)
        if self.target_min_amount and period_total < self.target_min_amount:
            return False
        if self.target_max_amount and period_total > self.target_max_amount:
            return False
        return True

    def _get_base_amount(self, move):
        self.ensure_one()
        sign = -1 if move.move_type == 'out_refund' else 1
        scoped_lines = self._get_matching_product_lines(move) if self._has_product_filter() else self._get_invoice_product_lines(move)
        if self.plan_id.base_type == 'invoice_total':
            base_amount = sum(abs(line.price_total) for line in scoped_lines) if self._has_product_filter() else abs(move.amount_total)
        elif self.plan_id.base_type in ('invoice_untaxed', 'invoice_line_subtotal'):
            base_amount = sum(abs(line.price_subtotal) for line in scoped_lines) if self._has_product_filter() else abs(move.amount_untaxed)
        elif self.plan_id.base_type == 'margin':
            base_amount = self._get_margin_amount(move, scoped_lines)
        elif self.plan_id.base_type == 'quantity':
            base_amount = sum(scoped_lines.mapped('quantity'))
        else:
            base_amount = abs(move.amount_untaxed)
        return sign * base_amount

    def _get_margin_amount(self, move, lines=None):
        lines = lines or self._get_invoice_product_lines(move)
        margin = 0.0
        for line in lines:
            cost = line.product_id.standard_price * line.quantity
            margin += abs(line.price_subtotal) - cost
        return margin

    def _get_margin_percent(self, move):
        scoped_lines = self._get_matching_product_lines(move) if self._has_product_filter() else self._get_invoice_product_lines(move)
        subtotal = sum(abs(line.price_subtotal) for line in scoped_lines) if self._has_product_filter() else abs(move.amount_untaxed)
        if not subtotal:
            return 0.0
        margin = self._get_margin_amount(move, scoped_lines)
        return (margin / subtotal) * 100

    def _compute_commission_amount(self, move):
        self.ensure_one()
        base_amount = self._get_base_amount(move)
        return self._compute_commission_amount_from_base(base_amount)

    def _compute_commission_amount_from_base(self, base_amount):
        self.ensure_one()
        sign = -1 if base_amount < 0 else 1
        unsigned_base = abs(base_amount)
        rate = self.rate
        if self.calculation_method == 'fixed':
            amount = self.fixed_amount
            rate = 0.0
        elif self.calculation_method == 'tier':
            amount, rate = self._compute_tier_amount(unsigned_base)
        else:
            amount = unsigned_base * self.rate / 100
        if self.cap_amount:
            amount = min(amount, self.cap_amount)
        return sign * amount, rate, base_amount

    def _compute_tier_amount(self, base_amount):
        self.ensure_one()
        tiers = self.tier_ids.sorted(lambda tier: (tier.amount_from, tier.amount_to or 0.0))
        if self.tier_mode == 'progressive':
            total = 0.0
            last_rate = 0.0
            for tier in tiers:
                upper = tier.amount_to or base_amount
                taxable = max(min(base_amount, upper) - tier.amount_from, 0.0)
                if taxable:
                    total += taxable * tier.rate / 100 + tier.fixed_bonus
                    last_rate = tier.rate
                if tier.amount_to and base_amount <= tier.amount_to:
                    break
            return total, last_rate
        for tier in tiers:
            if base_amount >= tier.amount_from and (not tier.amount_to or base_amount <= tier.amount_to):
                return base_amount * tier.rate / 100 + tier.fixed_bonus, tier.rate
        return 0.0, 0.0


class CommissionTier(models.Model):
    _name = 'commission.tier'
    _description = 'Commission Tier'
    _order = 'rule_id, amount_from'

    rule_id = fields.Many2one('commission.rule', required=True, ondelete='cascade')
    currency_id = fields.Many2one(related='rule_id.currency_id', store=True, readonly=True)
    amount_from = fields.Monetary(required=True, currency_field='currency_id')
    amount_to = fields.Monetary(currency_field='currency_id')
    rate = fields.Float(string='Rate (%)', digits='Discount')
    fixed_bonus = fields.Monetary(currency_field='currency_id')

    @api.constrains('amount_from', 'amount_to', 'rate', 'fixed_bonus')
    def _check_tier_values(self):
        for tier in self:
            if tier.amount_from < 0 or tier.rate < 0 or tier.fixed_bonus < 0:
                raise ValidationError('Tier values cannot be negative.')
            if tier.amount_to and tier.amount_to <= tier.amount_from:
                raise ValidationError('Tier amount to must be greater than amount from.')
