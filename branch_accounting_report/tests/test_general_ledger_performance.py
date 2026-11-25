from pathlib import Path

from odoo.tests.common import TransactionCase


class _ReportQueryStub:
    def _split_options_per_column_group(self, options):
        return {'current': options}

    def _query_get(self, options, domain=None, date_scope=None):
        if domain:
            return (
                'account_move_line',
                'account_move_line.account_id IN %s',
                [tuple(domain[0][2])],
            )
        return 'account_move_line', 'TRUE', []

    def _get_query_currency_table(self, options):
        return (
            '(VALUES (1, 1.0, 2)) '
            'AS currency_table(company_id, rate, precision)'
        )


class TestGeneralLedgerPerformance(TransactionCase):
    def test_loading_notifications_remain_until_user_dismisses_them(self):
        script_path = (
            Path(__file__).resolve().parents[1]
            / 'static'
            / 'src'
            / 'js'
            / 'general_ledger_safe_unfold.js'
        )
        script = script_path.read_text(encoding='utf-8')

        self.assertNotIn('closeProgressNotification', script)
        self.assertIn('{ type: "success", sticky: true }', script)
        self.assertEqual(script.count('sticky: true'), 3)

    def test_general_ledger_enables_safe_unfold_option(self):
        handler = self.env['account.general.ledger.report.handler']
        report = self.env.ref('account_reports.general_ledger_report')
        options = {}

        handler._custom_options_initializer(report, options, {})

        self.assertTrue(options['branch_gl_safe_unfold'])

    def test_aml_query_does_not_aggregate_individual_journal_items(self):
        handler = self.env['account.general.ledger.report.handler']

        query, params = handler._get_query_amls(
            _ReportQueryStub(),
            {},
            expanded_account_ids=[41, 42],
            limit=81,
        )

        normalized_query = ' '.join(query.upper().split())
        self.assertNotIn(' GROUP BY ', normalized_query)
        self.assertNotIn('MIN(', normalized_query)
        self.assertNotIn('SUM(', normalized_query)
        self.assertIn(
            "ACCOUNT_MOVE_LINE.ACCOUNT_ID IN %S",
            normalized_query,
        )
        self.assertIn('BRANCH.NAME AS BRANCH_NAME', normalized_query)
        self.assertEqual(params[-1], 81)

    def test_branch_ledger_index_exists(self):
        self.env.cr.execute(
            """
                SELECT 1
                  FROM pg_indexes
                 WHERE schemaname = current_schema()
                   AND indexname = 'account_move_line_branch_account_date_idx'
            """
        )
        self.assertTrue(self.env.cr.fetchone())
