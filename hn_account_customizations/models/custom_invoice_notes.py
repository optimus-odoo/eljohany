from odoo import models, fields, api


class CustomInvoiceNotes(models.Model):
    _name = "custom.invoice.notes"
    _description = "Custom Invoice Notes"

    html_note = fields.Html(string="Custom Invoice Notes")
    alignment = fields.Selection([
        ('left', 'Left'),
        ('center', 'Center'),
        ('right', 'Right')
    ], string="Text Alignment", default='left', required=True)


    @api.model
    def get_singleton(self):
        record = self.search([], order="id asc", limit=1)
        if not record:
            record = self.create({})
        return record