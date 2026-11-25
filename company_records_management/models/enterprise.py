from odoo import api, fields, models, _
from odoo.exceptions import UserError

from .expiry_utils import (
    EXPIRY_MODEL_FIELDS,
    EXPIRY_WARNING_DAYS,
    get_days_remaining,
)

class CrmRecordAudit(models.Model):
    _name = 'crm.record.audit'
    _description = 'تدقيق سجلات الشركات'
    _order = 'create_date desc'

    model_name = fields.Char(string='اسم النموذج', required=True, index=True)
    record_id = fields.Integer(string='رقم السجل', required=True, index=True)
    record_name = fields.Char(string='اسم السجل')
    action = fields.Selection([
        ('create','إنشاء'), ('write','تعديل'), ('state','تغيير حالة'),
        ('archive','أرشفة'), ('restore','إلغاء الأرشفة'), ('delete','حذف')
    ], string='الإجراء', required=True)
    user_id = fields.Many2one('res.users', string='المستخدم', required=True, default=lambda self: self.env.user)
    field_name = fields.Char(string='اسم الحقل')
    old_value = fields.Text(string='القيمة السابقة')
    new_value = fields.Text(string='القيمة الجديدة')
    note = fields.Text(string='ملاحظات')
    create_date = fields.Datetime(string='تاريخ الإنشاء', readonly=True)

class CrmApprovalMixin(models.AbstractModel):
    _name = 'crm.approval.mixin'
    _description = 'مسار اعتماد السجلات'

    approval_state = fields.Selection([
        ('draft','مسودة'), ('submitted','قيد المراجعة'),
        ('approved','معتمد'), ('rejected','مرفوض'), ('archived','مؤرشف')
    ], string='حالة الاعتماد', default='draft', tracking=True)
    submitted_by = fields.Many2one('res.users', string='أرسله للاعتماد', readonly=True)
    submitted_at = fields.Datetime(string='تاريخ الإرسال للاعتماد', readonly=True)
    approved_by = fields.Many2one('res.users', string='اعتمده', readonly=True)
    approved_at = fields.Datetime(string='تاريخ الاعتماد', readonly=True)
    rejected_by = fields.Many2one('res.users', string='رفضه', readonly=True)
    rejection_reason = fields.Text(string='سبب الرفض')
    active = fields.Boolean(string='نشط', default=True)

    def action_submit(self):
        for rec in self:
            rec.write({'approval_state':'submitted','submitted_by':self.env.user,'submitted_at':fields.Datetime.now()})
            rec._audit('state', note='تم إرسال السجل للاعتماد')

    def action_approve(self):
        if not self.env.user.has_group('company_records_management.group_records_manager'):
            raise UserError(_('اعتماد السجل متاح لمدير إدارة السجلات فقط.'))
        for rec in self:
            rec.write({'approval_state':'approved','approved_by':self.env.user,'approved_at':fields.Datetime.now()})
            rec._audit('state', note='تم اعتماد السجل')

    def action_reject(self, reason=None):
        if not self.env.user.has_group('company_records_management.group_records_manager'):
            raise UserError(_('رفض السجل متاح لمدير إدارة السجلات فقط.'))
        for rec in self:
            rec.write({'approval_state':'rejected','rejected_by':self.env.user,'rejection_reason':reason or 'لم يتم تحديد السبب'})
            rec._audit('state', note=rec.rejection_reason)

    def action_archive_record(self):
        if not self.env.user.has_group('company_records_management.group_records_manager'):
            raise UserError(_('أرشفة السجل متاحة لمدير إدارة السجلات فقط.'))
        for rec in self:
            rec.write({'approval_state':'archived','active':False})
            rec._audit('archive')

    def action_restore_record(self):
        if not self.env.user.has_group('company_records_management.group_records_manager'):
            raise UserError(_('إلغاء الأرشفة متاح لمدير إدارة السجلات فقط.'))
        for rec in self:
            rec.write({'approval_state':'approved','active':True})
            rec._audit('restore')

    def _audit(self, action, field_name=None, old_value=None, new_value=None, note=None):
        for rec in self:
            self.env['crm.record.audit'].sudo().create({
                'model_name': rec._name,
                'record_id': rec.id,
                'record_name': rec.display_name,
                'action': action,
                'user_id': self.env.user.id,
                'field_name': field_name,
                'old_value': old_value,
                'new_value': new_value,
                'note': note,
            })

class CrmComplianceDashboard(models.AbstractModel):
    _name = 'crm.compliance.dashboard'
    _description = 'لوحة متابعة الامتثال'

    @api.model
    def get_data(self):
        today = fields.Date.context_today(self)
        data = {'companies':0,'branches':0,'registrations':0,'municipality':0,'civil':0,'leases':0,
                'expired':0,'d30':0,'d60':0,'d90':0}
        models = [
            ('companies','crm.company.record'), ('branches','crm.company.branch'),
            ('registrations','crm.commercial.registration'),
            ('municipality','crm.municipality.license'),
            ('civil','crm.civil.defense.license'), ('leases','crm.lease.contract')
        ]
        for key, model in models:
            data[key] = self.env[model].search_count([])
        for model, date_field in EXPIRY_MODEL_FIELDS:
            records = self.env[model].search([(date_field, '!=', False)])
            for r in records:
                days = get_days_remaining(r[date_field], today)
                if days < 0: data['expired'] += 1
                elif days <= 30: data['d30'] += 1
                elif days <= 60: data['d60'] += 1
                elif days <= 90: data['d90'] += 1
        return data

class CrmComplianceCron(models.AbstractModel):
    _name = 'crm.compliance.cron'
    _description = 'مهمة متابعة الامتثال المجدولة'

    @api.model
    def cron_check_expiry(self):
        today = fields.Date.context_today(self)
        activity_type = self.env.ref('company_records_management.mail_activity_type_record_expiry', raise_if_not_found=False)
        if not activity_type:
            return
        for model, date_field in EXPIRY_MODEL_FIELDS:
            records = self.env[model].search([
                (date_field, '!=', False),
                (
                    date_field,
                    '<=',
                    today + __import__('datetime').timedelta(
                        days=EXPIRY_WARNING_DAYS
                    ),
                ),
            ])
            for rec in records:
                days = get_days_remaining(rec[date_field], today)
                if days in (90,60,30,0):
                    user = rec.create_uid or self.env.user
                    self.env['mail.activity'].sudo().create({
                        'activity_type_id': activity_type.id,
                        'res_model_id': self.env['ir.model']._get(model).id,
                        'res_id': rec.id,
                        'user_id': user.id,
                        'summary': 'تنبيه انتهاء مستند',
                        'note': 'المستند %s يستحق المراجعة. الأيام المتبقية: %s' % (rec.display_name, days),
                        'date_deadline': today,
                    })
