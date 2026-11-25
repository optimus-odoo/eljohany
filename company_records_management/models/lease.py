from odoo import api, fields, models
from odoo.exceptions import ValidationError

from .expiry_utils import get_days_remaining, get_expiry_state

class CrmLeaseContract(models.Model):
    _name = 'crm.lease.contract'
    _description = 'عقد الإيجار'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'crm.approval.mixin']
    _order = 'date_end desc'

    name = fields.Char(string='رقم العقد', required=True, copy=False, tracking=True)
    company_id = fields.Many2one('crm.company.record', string='الشركة', required=True, ondelete='cascade')
    branch_id = fields.Many2one('crm.company.branch', string='الفرع', required=True, ondelete='cascade')
    signing_date = fields.Date(string='تاريخ توقيع العقد', required=True)
    date_start = fields.Date(string='تاريخ البداية', required=True)
    date_end = fields.Date(string='تاريخ النهاية', required=True, tracking=True)
    conditional = fields.Boolean(string='معلق بشرط')
    state = fields.Selection([
        ('draft','مسودة'), ('active','ساري'), ('soon','قريب الانتهاء'),
        ('expired','منتهي'), ('suspended','معلق'), ('cancelled','ملغى')
    ], string='الحالة', compute='_compute_state')
    days_remaining = fields.Integer(
        string='الأيام المتبقية',
        compute='_compute_state',
    )

    lessor_name = fields.Char(string='اسم المؤجر', required=True)
    lessor_unified_no = fields.Char(string='الرقم الموحد للمؤجر')
    lessor_cr_no = fields.Char(string='رقم السجل التجاري للمؤجر')
    lessor_cr_date = fields.Date(string='تاريخ السجل التجاري للمؤجر')
    lessor_rep_name = fields.Char(string='اسم ممثل المؤجر')
    lessor_rep_nationality = fields.Char(string='جنسية ممثل المؤجر')
    lessor_rep_identity = fields.Char(string='رقم هوية ممثل المؤجر')
    lessor_rep_mobile = fields.Char(string='جوال ممثل المؤجر')
    lessor_rep_email = fields.Char(string='البريد الإلكتروني لممثل المؤجر')
    lessor_rep_address = fields.Text(string='عنوان ممثل المؤجر')

    tenant_name = fields.Char(string='اسم المستأجر', required=True)
    tenant_nationality = fields.Char(string='جنسية المستأجر')
    tenant_cr_no = fields.Char(string='رقم السجل التجاري للمستأجر')
    tenant_unified_no = fields.Char(string='الرقم الموحد للمستأجر')
    tenant_cr_date = fields.Date(string='تاريخ السجل التجاري للمستأجر')
    tenant_rep_name = fields.Char(string='اسم ممثل المستأجر')
    tenant_rep_nationality = fields.Char(string='جنسية ممثل المستأجر')
    tenant_rep_identity = fields.Char(string='رقم هوية ممثل المستأجر')
    tenant_rep_email = fields.Char(string='البريد الإلكتروني لممثل المستأجر')
    tenant_rep_address = fields.Text(string='عنوان ممثل المستأجر')

    unit_type = fields.Char(string='نوع الوحدة')
    national_address = fields.Text(string='العنوان الوطني')
    area = fields.Float(string='المساحة')
    rent_total_excl_tax = fields.Monetary(string='إجمالي الإيجار قبل الضريبة')
    tax_total = fields.Monetary(string='إجمالي الضريبة', compute='_compute_amounts', store=True)
    rent_total_incl_tax = fields.Monetary(string='إجمالي الإيجار شامل الضريبة', compute='_compute_amounts', store=True)
    annual_rent_excl_tax = fields.Monetary(string='الإيجار السنوي قبل الضريبة')
    annual_tax = fields.Monetary(string='الضريبة السنوية', compute='_compute_amounts', store=True)
    annual_rent_incl_tax = fields.Monetary(string='الإيجار السنوي شامل الضريبة', compute='_compute_amounts', store=True)
    tax_rate = fields.Float(string='نسبة الضريبة', default=15.0)
    currency_id = fields.Many2one('res.currency', string='العملة', default=lambda self: self.env.company.currency_id.id)
    active = fields.Boolean(string='نشط', default=True)
    attachment_ids = fields.Many2many('ir.attachment', string='المستندات')
    note = fields.Text(string='ملاحظات')

    @api.depends('date_end')
    def _compute_state(self):
        today = fields.Date.context_today(self)
        for rec in self:
            if not rec.date_end:
                rec.state = 'draft'
            else:
                expiry_state = get_expiry_state(rec.date_end, today)
                rec.state = 'active' if expiry_state == 'valid' else expiry_state
            rec.days_remaining = get_days_remaining(rec.date_end, today)

    @api.depends('rent_total_excl_tax','annual_rent_excl_tax','tax_rate')
    def _compute_amounts(self):
        for rec in self:
            rate = rec.tax_rate / 100.0
            rec.tax_total = rec.rent_total_excl_tax * rate
            rec.rent_total_incl_tax = rec.rent_total_excl_tax + rec.tax_total
            rec.annual_tax = rec.annual_rent_excl_tax * rate
            rec.annual_rent_incl_tax = rec.annual_rent_excl_tax + rec.annual_tax

    @api.constrains('date_start','date_end')
    def _check_dates(self):
        for rec in self:
            if rec.date_start and rec.date_end and rec.date_end < rec.date_start:
                raise ValidationError('تاريخ انتهاء الإيجار يجب أن يكون بعد تاريخ البداية.')
