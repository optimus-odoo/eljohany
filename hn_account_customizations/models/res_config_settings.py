from odoo import models, fields, api


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'
    
    custom_invoice_note_id = fields.Many2one('custom.invoice.notes', string="Custom Invoice Note")
    custom_invoice_html_note = fields.Html(related='custom_invoice_note_id.html_note', string="Invoice Note", readonly=False)
    custom_invoice_alignment = fields.Selection(related='custom_invoice_note_id.alignment', string="Alignment", readonly=False, default='left', required=True)

    @api.model
    def get_values(self):
        res = super(ResConfigSettings, self).get_values()
        note_record = self.env['custom.invoice.notes'].get_singleton()
        res.update({
            'custom_invoice_note_id': note_record.id,
            'custom_invoice_html_note': note_record.html_note,
            'custom_invoice_alignment': note_record.alignment,
        })
        return res

