from odoo import models, api
import os, base64

class CustomInvoiceReport(models.AbstractModel):
    _name = 'report.hn_account_customizations.report_custom_invoice'
    _description = 'Custom Invoice Report'


    @api.model
    def _get_processed_image(self, image_name):
        """Get QR code image from static folder"""
        try:
            module_path = os.path.dirname(os.path.dirname(__file__))
            image_path = os.path.join(module_path, 'static', 'img', image_name)
            
            with open(image_path, 'rb') as image_file:
                image_data = base64.b64encode(image_file.read())
                return image_data
        except Exception as e:
            return False


    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env['account.move'].browse(docids)

        note_record = self.env['custom.invoice.notes'].get_singleton()

        return {
            'doc_ids': docids,
            'doc_model': 'account.move',
            'docs': docs,
            'notes': note_record.html_note,
            'alignment': note_record.alignment,
            'qrcode': self._get_processed_image(image_name="qrcode.png"),
            'bottom_qrcode': self._get_processed_image(image_name="bottom_qrcode.png"),
        }


