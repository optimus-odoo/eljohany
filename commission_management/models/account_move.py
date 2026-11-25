# -*- coding: utf-8 -*-

from odoo import api, fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    commission_line_ids = fields.One2many('commission.line', 'invoice_id', string='Commission Lines')
    commission_line_count = fields.Integer(compute='_compute_commission_line_count')

    def _compute_commission_line_count(self):
        for move in self:
            move.commission_line_count = len(move.commission_line_ids)

    def action_post(self):
        res = super().action_post()
        self.filtered(
            lambda move: move.move_type in ('out_invoice', 'out_refund')
            and move.state == 'posted'
        ).action_generate_commission_lines()
        return res

    def _get_commission_source_move(self):
        self.ensure_one()
        if self.move_type != 'out_refund':
            return self
        if self.reversed_entry_id:
            return self.reversed_entry_id
        if self.env.context.get('commission_skip_source_fallback'):
            return self
        source_text = ' '.join(filter(None, [
            self.ref,
            self.invoice_origin,
            self.payment_reference,
        ]))
        if not source_text:
            return self
        candidates = self.search([
            ('company_id', '=', self.company_id.id),
            ('commercial_partner_id', '=', self.commercial_partner_id.id),
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
        ], order='invoice_date desc, id desc', limit=20)
        return candidates.filtered(lambda move: move.name and move.name in source_text)[:1] or self

    def _get_commission_payment_events(self):
        self.ensure_one()
        payment_period_start = self.env.context.get('commission_payment_period_start')
        payment_period_end = self.env.context.get('commission_payment_period_end')
        payment_period_start = fields.Date.to_date(payment_period_start) if payment_period_start else False
        payment_period_end = fields.Date.to_date(payment_period_end) if payment_period_end else False
        receivable_lines = self.line_ids.filtered(lambda line: line.account_id.account_type == 'asset_receivable')
        events = []
        seen_partials = set()
        for line in receivable_lines:
            for partial in line.matched_debit_ids | line.matched_credit_ids:
                if partial.id in seen_partials:
                    continue
                seen_partials.add(partial.id)
                counterpart_line = partial.debit_move_id if partial.debit_move_id != line else partial.credit_move_id
                payment_move = counterpart_line.move_id
                payment_date = payment_move.date or partial.max_date
                if payment_period_start and payment_date < payment_period_start:
                    continue
                if payment_period_end and payment_date > payment_period_end:
                    continue
                events.append({
                    'partial_reconcile': partial,
                    'payment_move': payment_move,
                    'payment_date': payment_date,
                    'amount': partial.amount,
                })
        events.sort(key=lambda event: (event['payment_date'], event['partial_reconcile'].id))
        return events

    def _get_paid_commission_base_amount(self, rule, paid_amount):
        self.ensure_one()
        invoice_base = rule._get_base_amount(self)
        if not self.amount_total:
            return 0.0
        return invoice_base * (abs(paid_amount) / abs(self.amount_total))

    def action_generate_commission_lines(self):
        CommissionLine = self.env['commission.line'].sudo()
        target_total_cache = {}
        use_statement_dates = bool(self.env.context.get('commission_use_statement_dates'))
        target_plan_id = self.env.context.get('commission_plan_id')
        target_user_id = self.env.context.get('commission_target_user_id')
        target_partner_id = self.env.context.get('commission_target_partner_id')
        stale_domain = [
            ('invoice_id', 'in', self.ids),
            ('statement_id', '=', False),
            ('state', 'in', ('draft', 'calculated')),
        ]
        if target_plan_id:
            stale_domain.append(('plan_id', '=', target_plan_id))
        if target_user_id:
            stale_domain.append(('user_id', '=', target_user_id))
        if target_partner_id:
            stale_domain.append(('partner_id', '=', target_partner_id))
        CommissionLine.search(stale_domain).unlink()
        existing_domain = [('invoice_id', 'in', self.ids)]
        if target_plan_id:
            existing_domain.append(('plan_id', '=', target_plan_id))
        if target_user_id:
            existing_domain.append(('user_id', '=', target_user_id))
        if target_partner_id:
            existing_domain.append(('partner_id', '=', target_partner_id))
        existing_keys = set(CommissionLine.search(existing_domain).mapped('unique_key'))
        for move in self:
            if move.move_type not in ('out_invoice', 'out_refund') or move.state != 'posted':
                continue
            move_date = move.invoice_date or move.date or fields.Date.context_today(move)
            payment_events = move._get_commission_payment_events()
            trigger_types = ['invoice_posted']
            if move.payment_state in ('partial', 'paid', 'in_payment'):
                trigger_types.append('invoice_paid')
            if self.env.context.get('manual_commission_generation'):
                trigger_types.append('manual')
            if target_plan_id:
                plans = self.env['commission.plan'].sudo().browse(target_plan_id).filtered(
                    lambda plan: plan.company_id == move.company_id
                    and plan.state == 'active'
                    and plan.trigger_type in trigger_types
                    and (
                        use_statement_dates
                        or (plan.trigger_type != 'invoice_paid' and plan._is_effective_for_date(move_date))
                        or plan.trigger_type == 'invoice_paid'
                    ))
            else:
                plans = self.env['commission.plan'].sudo().search([
                    ('company_id', '=', move.company_id.id),
                    ('state', '=', 'active'),
                    ('trigger_type', 'in', trigger_types),
                    ('date_start', '<=', move_date),
                    '|', ('date_end', '=', False), ('date_end', '>=', move_date),
                ])
                if 'invoice_paid' in trigger_types:
                    plans |= self.env['commission.plan'].sudo().search([
                        ('company_id', '=', move.company_id.id),
                        ('state', '=', 'active'),
                        ('trigger_type', '=', 'invoice_paid'),
                    ])
            invoice_lines = move.invoice_line_ids.filtered(
                lambda line: not line.display_type and line.product_id)
            for plan in plans:
                for rule in plan._get_matching_rules(move):
                    source_move = move._get_commission_source_move()
                    beneficiary_values = rule._get_beneficiary_values(move)
                    if not beneficiary_values.get('user_id') and not beneficiary_values.get('partner_id'):
                        continue
                    if target_user_id and beneficiary_values.get('user_id') != target_user_id:
                        continue
                    if target_partner_id and beneficiary_values.get('partner_id') != target_partner_id:
                        continue
                    if not rule._matches_target_thresholds(
                        move,
                        beneficiary_values,
                        target_total_cache=target_total_cache,
                    ):
                        continue
                    line_type = 'clawback' if move.move_type == 'out_refund' else 'commission'
                    sale_lines = invoice_lines.mapped('sale_line_ids')
                    reversed_line = False
                    if move.move_type == 'out_refund' and source_move != move:
                        reversed_line = CommissionLine.search([
                            ('invoice_id', '=', source_move.id),
                            ('plan_id', '=', plan.id),
                            ('rule_id', '=', rule.id),
                            ('user_id', '=', beneficiary_values.get('user_id') or False),
                            ('partner_id', '=', beneficiary_values.get('partner_id') or False),
                            ('state', '!=', 'cancelled'),
                        ], limit=1)
                    if plan.trigger_type == 'invoice_paid':
                        for event in payment_events:
                            if not use_statement_dates and not plan._is_effective_for_date(event['payment_date']):
                                continue
                            unique_key = CommissionLine._make_payment_unique_key(
                                plan, rule, move, event['partial_reconcile'], beneficiary_values)
                            if unique_key in existing_keys:
                                continue
                            base_amount = move._get_paid_commission_base_amount(rule, event['amount'])
                            amount, rate, base_amount = rule._compute_commission_amount_from_base(base_amount)
                            if not amount:
                                continue
                            CommissionLine.create({
                                'unique_key': unique_key,
                                'line_type': line_type,
                                'plan_id': plan.id,
                                'rule_id': rule.id,
                                'company_id': move.company_id.id,
                                'date': event['payment_date'],
                                'sales_team_id': (move.team_id or source_move.team_id).id,
                                'customer_id': (move.commercial_partner_id or source_move.commercial_partner_id).id,
                                'invoice_id': move.id,
                                'payment_move_id': event['payment_move'].id,
                                'partial_reconcile_id': event['partial_reconcile'].id,
                                'sale_order_id': sale_lines[:1].order_id.id if sale_lines else False,
                                'base_amount': base_amount,
                                'commission_rate': rate,
                                'commission_amount': amount,
                                'reversed_line_id': reversed_line.id if reversed_line else False,
                                **beneficiary_values,
                            })
                            existing_keys.add(unique_key)
                    else:
                        amount, rate, base_amount = rule._compute_commission_amount(move)
                        if not amount:
                            continue
                        unique_key = CommissionLine._make_invoice_unique_key(
                            plan, rule, move, beneficiary_values)
                        if unique_key in existing_keys:
                            continue
                        CommissionLine.create({
                            'unique_key': unique_key,
                            'line_type': line_type,
                            'plan_id': plan.id,
                            'rule_id': rule.id,
                            'company_id': move.company_id.id,
                            'date': move_date,
                            'sales_team_id': (move.team_id or source_move.team_id).id,
                            'customer_id': (move.commercial_partner_id or source_move.commercial_partner_id).id,
                            'invoice_id': move.id,
                            'sale_order_id': sale_lines[:1].order_id.id if sale_lines else False,
                            'base_amount': base_amount,
                            'commission_rate': rate,
                            'commission_amount': amount,
                            'reversed_line_id': reversed_line.id if reversed_line else False,
                            **beneficiary_values,
                        })
                        existing_keys.add(unique_key)

    def action_view_commission_lines(self):
        self.ensure_one()
        action = self.env.ref('commission_management.action_commission_line').read()[0]
        action['domain'] = [('invoice_id', '=', self.id)]
        action['context'] = {'default_invoice_id': self.id}
        return action

    def _cron_generate_paid_invoice_commissions(self, limit=500):
        moves = self.search([
            ('move_type', 'in', ('out_invoice', 'out_refund')),
            ('state', '=', 'posted'),
            ('payment_state', 'in', ('partial', 'paid', 'in_payment')),
        ], order='date desc, id desc', limit=limit)
        moves.action_generate_commission_lines()


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    receipt_ids = fields.Many2many(
        'stock.picking',
        string='Receipts',
        compute='_compute_receipt_info',
    )
    receipt_status = fields.Selection([
        ('no_receipt', 'No Receipt'),
        ('waiting', 'Waiting'),
        ('ready', 'Ready'),
        ('partially_received', 'Partially Received'),
        ('received', 'Received'),
        ('cancelled', 'Cancelled'),
    ], string='Receipt Status', compute='_compute_receipt_info')

    @api.depends(
        'move_id.move_type',
        'purchase_line_id.move_ids.state',
        'purchase_line_id.move_ids.picking_id.state',
        'purchase_line_id.move_ids.picking_id.picking_type_id.code',
    )
    def _compute_receipt_info(self):
        purchase_move_types = ('in_invoice', 'in_refund', 'in_receipt')
        for line in self:
            line.receipt_ids = False
            line.receipt_status = False
            if (
                line.move_id.move_type not in purchase_move_types
                or not line.purchase_line_id
            ):
                continue

            receipts = line.purchase_line_id.move_ids.mapped('picking_id').filtered(
                lambda picking: picking.picking_type_id.code == 'incoming'
            ).sorted('id')
            line.receipt_ids = receipts
            if not receipts:
                line.receipt_status = 'no_receipt'
                continue

            active_receipts = receipts.filtered(lambda picking: picking.state != 'cancel')
            if not active_receipts:
                line.receipt_status = 'cancelled'
                continue

            states = set(active_receipts.mapped('state'))
            if states == {'done'}:
                line.receipt_status = 'received'
            elif 'done' in states:
                line.receipt_status = 'partially_received'
            elif 'assigned' in states:
                line.receipt_status = 'ready'
            else:
                line.receipt_status = 'waiting'
