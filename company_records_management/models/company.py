from odoo import api, fields, models
from odoo.exceptions import ValidationError

class CrmCompanyRecord(models.Model):
    _name = 'crm.company.record'
    _description = 'الشركة'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'crm.audit.mixin', 'crm.workflow.mixin']
    _order = 'name'

    name = fields.Char(string='اسم الشركة', required=True, tracking=True)
    name_en = fields.Char(string='الاسم بالإنجليزية')
    company_type = fields.Selection([
        ('single', 'شركة شخص واحد'),
        ('individual', 'فردية / مؤسسة'),
        ('partners', 'شركاء'),
    ], string='نوع الشركة', required=True, default='single', tracking=True)
    state = fields.Selection([
        ('active', 'نشطة'), ('inactive', 'غير نشطة'),
        ('suspended', 'موقوفة'), ('closed', 'منتهية')
    ], string='الحالة', default='active', tracking=True)
    partner_ids = fields.One2many('crm.company.partner', 'company_id', string='الشركاء')
    branch_ids = fields.One2many('crm.company.branch', 'company_id', string='الفروع')
    active = fields.Boolean(string='نشط', default=True)
    note = fields.Text(string='ملاحظات')
    attachment_ids = fields.Many2many('ir.attachment', string='المستندات')

    @api.constrains('partner_ids')
    def _check_partner_shares(self):
        for rec in self:
            total = sum(rec.partner_ids.mapped('ownership_percent'))
            if total > 100.000001:
                raise ValidationError('إجمالي نسب الشركاء لا يمكن أن يتجاوز 100%.')

class CrmCompanyPartner(models.Model):
    _name = 'crm.company.partner'
    _description = 'شريك الشركة'
    _order = 'company_id, name'

    company_id = fields.Many2one('crm.company.record', string='الشركة', required=True, ondelete='cascade')
    name = fields.Char(string='اسم الشريك', required=True)
    nationality = fields.Char(string='الجنسية')
    identity_type = fields.Selection([
        ('national_id', 'هوية وطنية'), ('iqama', 'إقامة'),
        ('passport', 'جواز سفر'), ('other', 'أخرى')
    ], string='نوع الهوية')
    identity_no = fields.Char(string='رقم الهوية')
    mobile = fields.Char(string='رقم الجوال')
    email = fields.Char(string='البريد الإلكتروني')
    birth_date = fields.Date(string='تاريخ الميلاد')
    ownership_percent = fields.Float(string='نسبة الملكية %', digits=(16, 4))
    share_value = fields.Monetary(string='قيمة الحصة')
    currency_id = fields.Many2one('res.currency', string='العملة', default=lambda self: self.env.company.currency_id.id)
    start_date = fields.Date(string='تاريخ البداية')
    end_date = fields.Date(string='تاريخ النهاية')
    active = fields.Boolean(string='نشط', default=True)

    @api.constrains('ownership_percent')
    def _check_percent(self):
        for rec in self:
            if rec.ownership_percent < 0 or rec.ownership_percent > 100:
                raise ValidationError('نسبة الملكية يجب أن تكون بين 0 و100.')

class CrmCompanyBranch(models.Model):
    _name = 'crm.company.branch'
    _description = 'فرع الشركة'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'crm.audit.mixin', 'crm.workflow.mixin']
    _order = 'company_id, name'

    name = fields.Char(string='اسم الفرع', required=True, tracking=True)
    code = fields.Char(string='الرمز', default='New', copy=False, readonly=True)
    company_id = fields.Many2one('crm.company.record', string='الشركة', required=True, ondelete='cascade', tracking=True)
    state = fields.Selection([
        ('active', 'نشط'), ('inactive', 'غير نشط'), ('closed', 'مغلق')
    ], string='الحالة', default='active', tracking=True)
    manager = fields.Char(string='المسؤول')
    city = fields.Char(string='المدينة')
    phone = fields.Char(string='رقم الهاتف')
    email = fields.Char(string='البريد الإلكتروني')
    note = fields.Text(string='ملاحظات')
    commercial_registration_ids = fields.Many2many(
        'crm.commercial.registration', 'crm_registration_branch_rel',
        'branch_id', 'registration_id', string='السجلات التجارية')
    municipality_license_ids = fields.One2many('crm.municipality.license', 'branch_id', string='الرخص البلدية')
    national_address_ids = fields.One2many('crm.national.address', 'branch_id', string='العناوين الوطنية')
    electricity_meter_ids = fields.One2many('crm.electricity.meter', 'branch_id', string='عدادات الكهرباء')
    civil_defense_ids = fields.One2many('crm.civil.defense.license', 'branch_id', string='رخص الدفاع المدني')
    bank_account_ids = fields.One2many('crm.branch.bank.account', 'branch_id', string='الحسابات البنكية')
    lease_contract_ids = fields.One2many('crm.lease.contract', 'branch_id', string='عقود الإيجار')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('code', 'New') == 'New':
                vals['code'] = self.env['ir.sequence'].next_by_code('crm.company.branch') or 'New'
        return super().create(vals_list)
