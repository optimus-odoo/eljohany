from odoo import models


class Base(models.AbstractModel):
    _inherit = "base"

    def export_data(self, fields_to_export, raw_data=False):
        """Export selected records without record-rule or field access failures."""
        return super(Base, self.sudo()).export_data(
            fields_to_export,
            raw_data=raw_data,
        )
