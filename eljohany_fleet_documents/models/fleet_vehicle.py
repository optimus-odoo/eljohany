from odoo import _, api, fields, models


class FleetVehicle(models.Model):
    _inherit = "fleet.vehicle"

    x_periodic_inspection_expiry_date = fields.Date(
        string="Periodic Inspection Expiry Date",
        tracking=True,
    )
    x_registration_expiry_date = fields.Date(
        string="Vehicle Registration Expiry Date",
        tracking=True,
    )
    x_operation_card_expiry_date = fields.Date(
        string="Operation Card Expiry Date",
        tracking=True,
    )
    x_insurance_expiry_date = fields.Date(
        string="Insurance Expiry Date",
        tracking=True,
    )
    x_driver_branch_id = fields.Many2one(
        "res.branch",
        string="Driver Branch",
        tracking=True,
        domain="[('company_id', '=', company_id)]",
    )
    x_vehicle_model = fields.Char(string="Vehicle Model", tracking=True)
    x_vehicle_type = fields.Char(string="Additional Vehicle Type", tracking=True)
    x_serial_number = fields.Char(string="Serial Number", tracking=True)
    x_chassis_number = fields.Char(string="Additional Chassis Number", tracking=True)
    x_owner_id = fields.Many2one(
        "res.partner",
        string="Vehicle Owner",
        tracking=True,
    )
    x_vehicle_color = fields.Char(string="Vehicle Color", tracking=True)
    x_vehicle_attachment_ids = fields.Many2many(
        "ir.attachment",
        "fleet_vehicle_document_attachment_rel",
        "vehicle_id",
        "attachment_id",
        string="Vehicle Files",
        copy=False,
    )
    x_accident_ids = fields.One2many(
        "fleet.vehicle.accident",
        "vehicle_id",
        string="Accident Records",
        copy=False,
    )
    x_accident_count = fields.Integer(
        string="Accident Count",
        compute="_compute_x_accident_count",
    )

    @api.depends("x_accident_ids")
    def _compute_x_accident_count(self):
        for vehicle in self:
            vehicle.x_accident_count = len(vehicle.x_accident_ids)

    def action_view_accidents(self):
        self.ensure_one()
        action = self.env.ref(
            "eljohany_fleet_documents.action_fleet_vehicle_accident"
        ).read()[0]
        action["domain"] = [("vehicle_id", "=", self.id)]
        action["context"] = {
            "default_vehicle_id": self.id,
            "default_driver_id": self.driver_id.id,
        }
        return action

    @api.model
    def _cron_create_document_expiry_activities(self):
        today = fields.Date.context_today(self)
        warning_limit = fields.Date.add(today, days=60)
        date_fields = [
            (
                "x_periodic_inspection_expiry_date",
                _("Periodic inspection expiry reminder"),
                _("Periodic inspection expires on %(date)s"),
            ),
            (
                "x_registration_expiry_date",
                _("Vehicle registration expiry reminder"),
                _("Vehicle registration expires on %(date)s"),
            ),
            (
                "x_operation_card_expiry_date",
                _("Operation card expiry reminder"),
                _("Operation card expires on %(date)s"),
            ),
            (
                "x_insurance_expiry_date",
                _("Insurance expiry reminder"),
                _("Insurance expires on %(date)s"),
            ),
        ]
        activity_type = self.env.ref("mail.mail_activity_data_todo", raise_if_not_found=False)
        if not activity_type:
            return
        model_id = self.env["ir.model"]._get_id("fleet.vehicle")
        vehicles = self.with_context(active_test=False).search([])
        for vehicle in vehicles:
            for field_name, summary, note_template in date_fields:
                expiry_date = vehicle[field_name]
                if not expiry_date or expiry_date > warning_limit:
                    continue
                note = _(
                    "%(document_note)s. The document date is within 60 days "
                    "of expiry or already expired."
                ) % {"document_note": note_template % {"date": expiry_date}}
                user = vehicle.manager_id or vehicle.create_uid
                domain = [
                    ("res_model_id", "=", model_id),
                    ("res_id", "=", vehicle.id),
                    ("activity_type_id", "=", activity_type.id),
                    ("summary", "=", summary),
                ]
                existing_activity = self.env["mail.activity"].search(domain, limit=1)
                values = {
                    "res_model_id": model_id,
                    "res_id": vehicle.id,
                    "activity_type_id": activity_type.id,
                    "summary": summary,
                    "note": note,
                    "date_deadline": expiry_date,
                    "user_id": user.id,
                }
                if existing_activity:
                    existing_activity.write(values)
                else:
                    self.env["mail.activity"].create(values)

    @api.model
    def _disable_missing_rate_view(self):
        if "rate_ids" in self._fields:
            return
        view = self.env.ref(
            "account_disallowed_expenses_fleet.fleet_vehicle_view_form",
            raise_if_not_found=False,
        )
        if view and view.active:
            view.active = False
