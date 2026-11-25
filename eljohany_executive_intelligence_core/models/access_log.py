from odoo import api, fields, models, _
from odoo.exceptions import AccessError


class ExecutiveIntelligenceAccessLog(models.Model):
    _name = "executive.intelligence.access.log"
    _description = "Executive Intelligence Access Change Log"
    _order = "change_date desc, id desc"

    target_user_id = fields.Many2one(
        "res.users",
        string="Target User",
        required=True,
        readonly=True,
        ondelete="restrict",
    )
    changed_by_id = fields.Many2one(
        "res.users",
        string="Changed By",
        required=True,
        readonly=True,
        default=lambda self: self.env.user,
        ondelete="restrict",
    )
    change_date = fields.Datetime(
        string="Change Date",
        required=True,
        readonly=True,
        default=fields.Datetime.now,
    )
    operation = fields.Selection(
        [("create", "Initial Configuration"), ("write", "Access Changed")],
        required=True,
        readonly=True,
        string="Operation",
    )
    previous_configuration = fields.Text(
        string="Previous Configuration", readonly=True
    )
    new_configuration = fields.Text(
        string="New Configuration", required=True, readonly=True
    )

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get("_ei_access_log_internal_create"):
            raise AccessError(
                _("Intelligence access logs can only be created automatically.")
            )
        return super().create(vals_list)

    def write(self, values):
        raise AccessError(_("Intelligence access audit logs are immutable."))

    @api.ondelete(at_uninstall=False)
    def _unlink_except_module_uninstall(self):
        raise AccessError(_("Intelligence access audit logs are immutable."))

