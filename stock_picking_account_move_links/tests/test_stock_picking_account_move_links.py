# -*- coding: utf-8 -*-

from odoo.tests.common import TransactionCase


class TestStockPickingAccountMoveLinks(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.journal = cls.env["account.journal"].create(
            {
                "name": "Picking Links Test",
                "code": "PLT",
                "type": "general",
                "company_id": cls.company.id,
            }
        )
        cls.entry_1, cls.entry_2, cls.entry_3, cls.entry_4 = cls.env[
            "account.move"
        ].create(
            [
                {"journal_id": cls.journal.id, "move_type": "entry"},
                {"journal_id": cls.journal.id, "move_type": "entry"},
                {"journal_id": cls.journal.id, "move_type": "entry"},
                {"journal_id": cls.journal.id, "move_type": "entry"},
            ]
        )

    def test_sources_are_unique_and_classified(self):
        valuation_moves = self.entry_1 | self.entry_2
        sale_moves = self.entry_2 | self.entry_3
        purchase_moves = self.entry_3 | self.entry_4
        all_moves, source_by_move_id = self.env[
            "stock.picking"
        ]._classify_linked_account_moves(
            valuation_moves, sale_moves, purchase_moves
        )

        self.assertEqual(len(all_moves), 4)
        self.assertEqual(source_by_move_id[self.entry_1.id], "valuation")
        self.assertEqual(source_by_move_id[self.entry_2.id], "multiple")
        self.assertEqual(source_by_move_id[self.entry_3.id], "multiple")
        self.assertEqual(source_by_move_id[self.entry_4.id], "purchase")
