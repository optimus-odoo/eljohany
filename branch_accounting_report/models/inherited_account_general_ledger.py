# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.

from odoo import api, models
from odoo.tools import get_lang


class AccountGeneralLedger(models.AbstractModel):
    _inherit = "account.general.ledger.report.handler"

    def _custom_options_initializer(self, report, options, previous_options=None):
        """Mark the general ledger for the bounded client-side unfold flow.

        Odoo's native ``unfold_all`` path asks the server to materialize every
        journal item of every account in one RPC.  That is precisely the wrong
        shape for a full-year ledger: a single worker owns the complete Python
        result, JSON payload and browser response until they are all ready.

        The web patch shipped by this module uses this private option as a
        capability flag.  It expands accounts sequentially through Odoo's
        regular ``get_expanded_lines`` endpoint, which keeps the native
        ``load_more_limit`` pagination and therefore bounds every request.
        """
        super()._custom_options_initializer(report, options, previous_options)
        options['branch_gl_safe_unfold'] = True

    @api.model
    def _get_options_domain(self, options):
        domain = super()._get_options_domain(options)
        domain += self._get_options_branch_domain(options)
        return domain
    
    @api.model
    def _get_options_branch_domain(self, options):
        domain = []
        if options.get('branch_ids'):
            branch_ids = [int(branch) for branch in options['branch_ids']]
            domain.append(('branch_id', 'in', branch_ids))
        return domain


    def _get_query_amls(self, report, options, expanded_account_ids, offset=0, limit=None):
        """ Construct a query retrieving the account.move.lines when expanding a report line with or without the load
        more.
        :param options:               The report options.
        :param expanded_account_ids:  The account.account ids corresponding to consider. If None, match every account.
        :param offset:                The offset of the query (used by the load more).
        :param limit:                 The limit of the query (used by the load more).
        :return:                      (query, params)
        """
        additional_domain = (
            [('account_id', 'in', expanded_account_ids)]
            if expanded_account_ids is not None
            else None
        )
        queries = []
        all_params = []
        lang = self.env.user.lang or get_lang(self.env).code
        journal_name = (
            f"COALESCE(journal.name->>'{lang}', journal.name->>'en_US')"
            if self.pool['account.journal'].name.translate
            else 'journal.name'
        )
        account_name = (
            f"COALESCE(account.name->>'{lang}', account.name->>'en_US')"
            if self.pool['account.account'].name.translate
            else 'account.name'
        )
        partner_name = (
            f"COALESCE(partner.name->>'{lang}', partner.name->>'en_US')"
            if self.pool['res.partner'].name.translate
            else 'partner.name'
        )
        for column_group_key, group_options in report._split_options_per_column_group(options).items():
            tables, where_clause, where_params = report._query_get(
                group_options,
                domain=additional_domain,
                date_scope='strict_range',
            )
            ct_query = report._get_query_currency_table(group_options)

            # Every joined relation below is many-to-one and the currency table
            # contains one row per company.  The previous implementation still
            # grouped every journal item by its own id and wrapped every selected
            # value in MIN/SUM.  On a full-year ledger this forced PostgreSQL to
            # aggregate and sort the complete result even though the operation
            # could not change a single value.  Select the row directly instead;
            # this keeps the exact report semantics and lets LIMIT/OFFSET as well
            # as the standard (account_id, date) index do their work.
            query = f'''
                (SELECT
                    account_move_line.id,
                    account_move_line.date,
                    account_move_line.date_maturity,
                    account_move_line.name,
                    account_move_line.ref,
                    account_move_line.company_id,
                    account_move_line.account_id,
                    account_move_line.payment_id,
                    account_move_line.partner_id,
                    account_move_line.currency_id,
                    account_move_line.amount_currency,
                    COALESCE(account_move_line.invoice_date, account_move_line.date) AS invoice_date,
                    ROUND(account_move_line.debit * currency_table.rate, currency_table.precision) AS debit,
                    ROUND(account_move_line.credit * currency_table.rate, currency_table.precision) AS credit,
                    ROUND(account_move_line.balance * currency_table.rate, currency_table.precision) AS balance,
                    move.name AS move_name,
                    account_move_line.company_currency_id AS company_currency_id,
                    {partner_name} AS partner_name,
                    move.move_type AS move_type,
                    account.code AS account_code,
                    {account_name} AS account_name,
                    journal.code AS journal_code,
                    {journal_name} AS journal_name,
                    account_move_line.full_reconcile_id AS full_rec_name,
                    %s AS column_group_key,
                    branch.name AS branch_name
                FROM {tables}
                JOIN account_move move                      ON move.id = account_move_line.move_id
                LEFT JOIN {ct_query}                        ON currency_table.company_id = account_move_line.company_id
                LEFT JOIN res_partner partner               ON partner.id = account_move_line.partner_id
                LEFT JOIN account_account account           ON account.id = account_move_line.account_id
                LEFT JOIN account_journal journal           ON journal.id = account_move_line.journal_id
                LEFT JOIN res_branch branch                 ON branch.id = account_move_line.branch_id
                WHERE {where_clause}
                ORDER BY account_move_line.date, move_name, account_move_line.id)
            '''

            queries.append(query)
            all_params.append(column_group_key)
            all_params += where_params

        full_query = " UNION ALL ".join(queries)

        if offset:
            full_query += ' OFFSET %s '
            all_params.append(offset)
        if limit:
            full_query += ' LIMIT %s '
            all_params.append(limit)

        return full_query, all_params
