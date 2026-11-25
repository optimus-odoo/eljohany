from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class FleetVehicleAccident(models.Model):
    _name = "fleet.vehicle.accident"
    _description = "Vehicle Accident"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "accident_date desc, id desc"

    name = fields.Char(
        string="Reference",
        default=lambda self: _("New Accident"),
        required=True,
        tracking=True,
    )
    vehicle_id = fields.Many2one(
        "fleet.vehicle",
        string="Vehicle",
        required=True,
        ondelete="cascade",
        tracking=True,
    )
    accident_date = fields.Date(string="Accident Date", required=True, tracking=True)
    fault_percentage = fields.Float(string="Fault Percentage", tracking=True)
    driver_id = fields.Many2one("res.partner", string="Driver", tracking=True)
    driver_details = fields.Text(string="Driver Details")
    description = fields.Text(string="Accident Notes")
    attachment_ids = fields.Many2many(
        "ir.attachment",
        "fleet_vehicle_accident_attachment_rel",
        "accident_id",
        "attachment_id",
        string="Accident Files",
        copy=False,
    )

    @api.constrains("fault_percentage")
    def _check_fault_percentage(self):
        for accident in self:
            if accident.fault_percentage < 0 or accident.fault_percentage > 100:
                raise ValidationError(_("Fault percentage must be between 0 and 100."))

    @api.onchange("vehicle_id")
    def _onchange_vehicle_id(self):
        if self.vehicle_id and not self.driver_id:
            self.driver_id = self.vehicle_id.driver_id
