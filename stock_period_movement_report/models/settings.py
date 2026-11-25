# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    spr_label_opening = fields.Char(string="تسمية الرصيد الافتتاحي", config_parameter="spr.label_opening", default="الرصيد الافتتاحي")
    spr_label_closing = fields.Char(string="تسمية الرصيد الختامي", config_parameter="spr.label_closing", default="الرصيد الختامي")
    spr_label_in = fields.Char(string="تسمية الوارد", config_parameter="spr.label_in", default="وارد")
    spr_label_out = fields.Char(string="تسمية الصادر", config_parameter="spr.label_out", default="صادر")
    spr_label_internal = fields.Char(string="تسمية التحويل الداخلي", config_parameter="spr.label_internal", default="تحويل داخلي")

    spr_xlsx_title = fields.Char(string="عنوان ملف Excel", config_parameter="spr.xlsx_title", default="تقرير حركة المخزون بين فترتين")
