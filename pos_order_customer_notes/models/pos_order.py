from odoo import api, fields, models


class PosOrder(models.Model):
    _inherit = "pos.order"

    customer_notes_summary = fields.Text(
        string="Customer Notes",
        compute="_compute_customer_notes",
        store=True,
        readonly=True,
    )
    customer_notes_list = fields.Char(
        string="Customer Notes",
        compute="_compute_customer_notes",
        store=True,
        readonly=True,
    )

    @api.depends(
        "lines.customer_note",
        "lines.full_product_name",
        "lines.product_id",
        "lines.product_id.name",
    )
    def _compute_customer_notes(self):
        for order in self:
            note_items = []
            for line in order.lines:
                note = (line.customer_note or "").strip()
                if not note:
                    continue
                product_name = (
                    line.full_product_name
                    or line.product_id.with_context(
                        display_default_code=False
                    ).display_name
                )
                note_items.append((product_name, note))
            summary, list_value = self._format_customer_notes(note_items)
            order.customer_notes_summary = summary
            order.customer_notes_list = list_value

    @api.model
    def _format_customer_notes(self, note_items):
        notes = [
            f"{product_name}: {note}" if product_name else note
            for product_name, note in note_items
            if note
        ]
        return "\n".join(notes) or False, " | ".join(notes) or False
