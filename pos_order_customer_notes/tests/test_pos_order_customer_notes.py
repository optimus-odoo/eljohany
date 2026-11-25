from pathlib import Path

from lxml import etree

from odoo.tests.common import TransactionCase


class TestPosOrderCustomerNotes(TransactionCase):
    def test_all_customer_notes_are_preserved_in_both_formats(self):
        summary, list_value = self.env["pos.order"]._format_customer_notes(
            [
                ("Burger", "No onions"),
                ("Fries", "Extra crispy"),
            ]
        )
        self.assertEqual(summary, "Burger: No onions\nFries: Extra crispy")
        self.assertEqual(list_value, "Burger: No onions | Fries: Extra crispy")

    def test_empty_notes_remain_hidden(self):
        summary, list_value = self.env["pos.order"]._format_customer_notes([])
        self.assertFalse(summary)
        self.assertFalse(list_value)

    def test_form_and_list_views_include_customer_notes(self):
        view_path = Path(__file__).parents[1] / "views" / "pos_order_views.xml"
        source = view_path.read_text(encoding="utf-8")
        etree.fromstring(source.encode("utf-8"))
        self.assertIn('name="customer_note"', source)
        self.assertIn('name="customer_notes_summary"', source)
        self.assertIn('name="customer_notes_list"', source)
        self.assertIn('invisible="not customer_notes_summary"', source)
