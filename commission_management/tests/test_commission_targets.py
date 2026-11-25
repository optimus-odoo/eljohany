# -*- coding: utf-8 -*-

from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestCommissionTargets(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({'name': 'Commission Customer'})
        cls.salesperson = cls.env.user
        cls.income_account = cls.env['account.account'].search([
            ('company_id', '=', cls.env.company.id),
            ('account_type', '=', 'income'),
            ('deprecated', '=', False),
        ], limit=1)
        if not cls.income_account:
            cls.income_account = cls.env['account.account'].create({
                'name': 'Commission Income',
                'code': 'COMMINC',
                'account_type': 'income',
                'company_id': cls.env.company.id,
            })
        cls.plan = cls.env['commission.plan'].create({
            'name': 'Monthly Target Plan',
            'company_id': cls.env.company.id,
            'date_start': '2026-01-01',
            'trigger_type': 'invoice_posted',
            'base_type': 'invoice_untaxed',
            'payment_frequency': 'monthly',
        })
        cls.rule = cls.env['commission.rule'].create({
            'name': 'Target Rule',
            'plan_id': cls.plan.id,
            'calculation_method': 'percentage',
            'rate': 10.0,
            'beneficiary_type': 'salesperson',
            'target_min_amount': 100.0,
            'target_max_amount': 120.0,
        })
        cls.plan.action_activate()

    def _create_invoice(self, amount, invoice_date):
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'invoice_user_id': self.salesperson.id,
            'invoice_date': invoice_date,
            'invoice_line_ids': [(0, 0, {
                'name': 'Commission Product',
                'quantity': 1.0,
                'price_unit': amount,
                'account_id': self.income_account.id,
            })],
        })
        invoice.action_post()
        return invoice

    def _create_statement(self):
        return self.env['commission.statement'].create({
            'company_id': self.env.company.id,
            'plan_id': self.plan.id,
            'beneficiary_type': 'user',
            'user_id': self.salesperson.id,
            'period_start': '2026-05-01',
        })

    def test_min_and_max_target_thresholds_use_statement_period_total(self):
        invoice_1 = self._create_invoice(60.0, '2026-05-01')
        invoice_2 = self._create_invoice(50.0, '2026-05-02')
        statement = self._create_statement()
        statement.action_calculate_from_registered_invoices()

        line_1 = self.env['commission.line'].search([('invoice_id', '=', invoice_1.id)])
        line_2 = self.env['commission.line'].search([('invoice_id', '=', invoice_2.id)])

        self.assertEqual(len(line_1), 1, 'The full period total should qualify the first invoice too.')
        self.assertEqual(len(line_2), 1, 'The second invoice should qualify from the same period total.')
        self.assertAlmostEqual(line_1.commission_amount, 6.0, places=2)
        self.assertAlmostEqual(line_2.commission_amount, 5.0, places=2)
        self.assertEqual(statement.line_ids, line_1 | line_2)

        invoice_3 = self._create_invoice(20.0, '2026-05-03')
        statement.action_calculate_from_registered_invoices()

        all_lines = self.env['commission.line'].search([
            ('invoice_id', 'in', (invoice_1 | invoice_2 | invoice_3).ids),
        ])
        self.assertFalse(all_lines, 'When the period total exceeds the maximum target, no invoice in the period should qualify.')
        self.assertFalse(statement.line_ids)
