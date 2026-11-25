from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ResCompany(models.Model):
    _inherit = "res.company"

    pos_receipt_use_alias = fields.Boolean(
        string="إظهار اسم مستعار في إيصال نقطة البيع",
        help="عند التفعيل يظهر الاسم المستعار بدلاً من اسم الشركة في رأس إيصال نقطة البيع.",
    )
    pos_receipt_alias = fields.Char(
        string="الاسم المستعار في الإيصال",
        translate=True,
    )

    @api.constrains("pos_receipt_use_alias", "pos_receipt_alias")
    def _check_pos_receipt_alias(self):
        for company in self:
            if company.pos_receipt_use_alias and not (
                company.pos_receipt_alias or ""
            ).strip():
                raise ValidationError(
                    _("يجب إدخال الاسم المستعار عند تفعيله في إيصال نقطة البيع.")
                )
