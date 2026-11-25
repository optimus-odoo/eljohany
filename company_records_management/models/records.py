from odoo import api, fields, models
from odoo.exceptions import ValidationError

from .expiry_utils import get_days_remaining, get_expiry_state

class CrmExpirable(models.AbstractModel):
    _name = 'crm.expirable.mixin'
    _description = 'سجل محدد الصلاحية'
    expiration_date = fields.Date(string='تاريخ الانتهاء', required=True, tracking=True)
    status = fields.Selection([('valid','ساري'),('soon','قريب الانتهاء'),('expired','منتهي')],
                              string='حالة الصلاحية', compute='_compute_status')
    days_remaining = fields.Integer(string='الأيام المتبقية', compute='_compute_status')

    @api.depends('expiration_date')
    def _compute_status(self):
        today = fields.Date.context_today(self)
        for rec in self:
            rec.days_remaining = get_days_remaining(rec.expiration_date, today)
            rec.status = get_expiry_state(rec.expiration_date, today)

class CrmCommercialRegistration(models.Model):
    _name='crm.commercial.registration'; _description='السجل التجاري'
    _inherit=['mail.thread','mail.activity.mixin','crm.expirable.mixin','crm.audit.mixin','crm.workflow.mixin']
    name=fields.Char(string='رقم السجل التجاري',required=True,tracking=True)
    company_id=fields.Many2one('crm.company.record',string='الشركة',required=True,ondelete='cascade')
    branch_ids=fields.Many2many('crm.company.branch','crm_registration_branch_rel','registration_id','branch_id',string='الفروع')
    unified_no=fields.Char(string='الرقم الموحد'); social_insurance_no=fields.Char(string='رقم التأمينات الاجتماعية')
    quwa_no=fields.Char(string='رقم المنشأة في قوى'); issue_date=fields.Date(string='تاريخ الإصدار',required=True)
    active=fields.Boolean(string='نشط',default=True)
    attachment_ids=fields.Many2many('ir.attachment',string='المستندات')

    @api.model_create_multi
    def create(self, vals_list):
        recs=super().create(vals_list)
        for r in recs: r._audit('create', vals_list[recs.ids.index(r.id)] if r.id in recs.ids else {})
        return recs
    def write(self, vals):
        old_values = self._audit_snapshot(vals)
        result = super().write(vals)
        for record in self:
            record._audit('write', vals, old_values.get(record.id, {}))
        return result

class CrmMunicipalityLicense(models.Model):
    _name='crm.municipality.license'; _description='الرخصة البلدية'
    _inherit=['mail.thread','mail.activity.mixin','crm.expirable.mixin','crm.audit.mixin','crm.workflow.mixin']
    name=fields.Char(string='رقم الرخصة',required=True); branch_id=fields.Many2one('crm.company.branch',string='الفرع',required=True,ondelete='cascade')
    owner_name=fields.Char(string='اسم المالك'); owner_identity_no=fields.Char(string='رقم هوية المالك'); issue_date=fields.Date(string='تاريخ الإصدار'); isic_code=fields.Char(string='رمز النشاط الاقتصادي (ISIC)')
    isic_description=fields.Char(string='وصف النشاط الاقتصادي'); municipality=fields.Char(string='البلدية'); secretariat=fields.Char(string='الأمانة'); district=fields.Char(string='الحي'); street=fields.Char(string='الشارع')
    sign_type=fields.Char(string='نوع اللوحة'); sign_area=fields.Float(string='مساحة اللوحة'); shop_area=fields.Float(string='مساحة المحل'); active=fields.Boolean(string='نشط',default=True)
    attachment_ids=fields.Many2many('ir.attachment',string='المستندات')

class CrmNationalAddress(models.Model):
    _name='crm.national.address'; _description='العنوان الوطني'
    _inherit=['mail.thread','crm.audit.mixin','crm.workflow.mixin']
    name=fields.Char(string='اسم الشركة في العنوان الوطني'); branch_id=fields.Many2one('crm.company.branch',string='الفرع',required=True,ondelete='cascade')
    account_no=fields.Char(string='رقم الحساب'); registration_date=fields.Date(string='تاريخ التسجيل'); short_address=fields.Char(string='العنوان المختصر'); building_no=fields.Char(string='رقم المبنى')
    street=fields.Char(string='الشارع'); district=fields.Char(string='الحي'); secondary_no=fields.Char(string='الرقم الفرعي'); postal_code=fields.Char(string='الرمز البريدي'); city=fields.Char(string='المدينة')
    active=fields.Boolean(string='نشط',default=True); attachment_ids=fields.Many2many('ir.attachment',string='المستندات')

class CrmElectricityMeter(models.Model):
    _name='crm.electricity.meter'; _description='عداد الكهرباء'
    _inherit=['mail.thread','crm.audit.mixin','crm.workflow.mixin']
    name=fields.Char(string='رقم الحساب',required=True); branch_id=fields.Many2one('crm.company.branch',string='الفرع',required=True,ondelete='cascade')
    monthly_payment_day=fields.Integer(string='يوم السداد الشهري'); service_start_date=fields.Date(string='تاريخ بدء الخدمة')
    state=fields.Selection([('active','نشط'),('inactive','غير نشط')],string='الحالة',default='active')
    active=fields.Boolean(string='نشط',default=True); attachment_ids=fields.Many2many('ir.attachment',string='المستندات')

class CrmCivilDefenseLicense(models.Model):
    _name='crm.civil.defense.license'; _description='رخصة الدفاع المدني'
    _inherit=['mail.thread','mail.activity.mixin','crm.expirable.mixin','crm.audit.mixin','crm.workflow.mixin']
    name=fields.Char(string='رقم الرخصة',required=True); branch_id=fields.Many2one('crm.company.branch',string='الفرع',required=True,ondelete='cascade')
    issue_date=fields.Date(string='تاريخ الإصدار',required=True); facility_classification=fields.Char(string='تصنيف المنشأة'); isic_activity=fields.Char(string='النشاط الاقتصادي (ISIC)')
    classification_no=fields.Char(string='رقم التصنيف'); activity_description=fields.Text(string='وصف النشاط'); active=fields.Boolean(string='نشط',default=True)
    attachment_ids=fields.Many2many('ir.attachment',string='المستندات')

class CrmBranchBankAccount(models.Model):
    _name='crm.branch.bank.account'; _description='الحساب البنكي للفرع'
    _inherit=['mail.thread','crm.audit.mixin','crm.workflow.mixin']
    name=fields.Char(string='اسم الحساب',required=True); branch_id=fields.Many2one('crm.company.branch',string='الفرع',required=True,ondelete='cascade')
    bank_name=fields.Char(string='اسم البنك',required=True); account_no=fields.Char(string='رقم الحساب'); iban=fields.Char(string='رقم الآيبان',required=True)
    currency_id=fields.Many2one('res.currency',string='العملة',default=lambda self:self.env.company.currency_id.id)
    opening_date=fields.Date(string='تاريخ فتح الحساب'); closing_date=fields.Date(string='تاريخ إغلاق الحساب'); state=fields.Selection([('active','نشط'),('closed','مغلق')],string='الحالة',default='active')
    active=fields.Boolean(string='نشط',default=True); note=fields.Text(string='ملاحظات')
    @api.constrains('iban')
    def _check_iban(self):
        for r in self:
            if r.iban and len(r.iban.replace(' ',''))<10: raise ValidationError('IBAN غير صحيح.')
