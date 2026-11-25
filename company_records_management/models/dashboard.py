from odoo import api, fields, models, _
from odoo.exceptions import AccessError
from datetime import timedelta

from .expiry_utils import (
    EXPIRY_WARNING_DAYS,
    get_days_remaining,
)

class CrmDashboard(models.AbstractModel):
    _name = 'crm.dashboard'
    _description = 'لوحة متابعة السجلات'

    @api.model
    def get_data(self, company_id=False, branch_id=False):
        today = fields.Date.context_today(self)
        models_map = [
            ('السجلات التجارية','crm.commercial.registration'),
            ('الرخص البلدية','crm.municipality.license'),
            ('الدفاع المدني','crm.civil.defense.license'),
            ('عقود الإيجار','crm.lease.contract'),
        ]
        result=[]
        for label, model in models_map:
            Model=self.env[model]
            domain = []
            if company_id:
                owner = 'company_id' if 'company_id' in Model._fields else 'branch_id.company_id'
                domain.append((owner, '=', company_id))
            if branch_id:
                domain.append(('branch_ids', 'in', [branch_id]) if model == 'crm.commercial.registration' else ('branch_id', '=', branch_id))
            date_field = 'expiration_date' if 'expiration_date' in Model._fields else 'date_end'
            total=Model.search_count(domain)
            soon=Model.search_count(domain + [(date_field,'>=',today),(date_field,'<=',today+timedelta(days=EXPIRY_WARNING_DAYS))])
            expired=Model.search_count(domain + [(date_field,'<',today)])
            result.append({'label':label,'total':total,'soon':soon,'expired':expired})
        return result

    @api.model
    def get_expiry_alerts(self, company_id=False, branch_id=False, limit=20):
        """Return a clear, date-ordered list for the workspace overview."""
        today = fields.Date.context_today(self)
        horizon = today + timedelta(days=EXPIRY_WARNING_DAYS)
        configs = [
            ('crm.commercial.registration', 'expiration_date', 'company_id', 'branch_ids'),
            ('crm.municipality.license', 'expiration_date', 'branch_id.company_id', 'branch_id'),
            ('crm.civil.defense.license', 'expiration_date', 'branch_id.company_id', 'branch_id'),
            ('crm.lease.contract', 'date_end', 'company_id', 'branch_id'),
        ]
        alerts = []
        for model_name, date_field, company_field, branch_field in configs:
            Model = self.env[model_name]
            domain = [(date_field, '<=', horizon)]
            if company_id:
                domain.append((company_field, '=', company_id))
            if branch_id:
                operator = 'in' if branch_field == 'branch_ids' else '='
                domain.append((branch_field, operator, [branch_id] if operator == 'in' else branch_id))
            for rec in Model.search(domain):
                expiry_date = rec[date_field]
                if not expiry_date:
                    continue
                branch = rec.branch_id if 'branch_id' in rec._fields else False
                company = rec.company_id if 'company_id' in rec._fields else branch.company_id
                alerts.append({
                    'model': model_name,
                    'record_id': rec.id,
                    'record_type': rec._description,
                    'record_name': rec.display_name,
                    'company_name': company.display_name if company else '',
                    'branch_name': branch.display_name if branch else '',
                    'expiry_date': fields.Date.to_string(expiry_date),
                    'days_remaining': get_days_remaining(expiry_date, today),
                })
        alerts.sort(key=lambda alert: (alert['expiry_date'], alert['record_type'], alert['record_name']))
        return alerts[:limit]

class CrmExpiryNotification(models.Model):
    _name = 'crm.expiry.notification'
    _description = 'إشعار انتهاء الصلاحية'
    _order = 'date desc'

    model_name = fields.Char(string='اسم النموذج', required=True)
    record_id = fields.Integer(string='رقم السجل', required=True)
    record_name = fields.Char(string='اسم السجل')
    expiry_date = fields.Date(string='تاريخ الانتهاء', required=True)
    days_before = fields.Integer(string='عدد الأيام قبل الانتهاء', required=True)
    user_id = fields.Many2one('res.users', string='المستخدم', required=True)
    date = fields.Datetime(string='التاريخ', default=fields.Datetime.now)
    notification_type = fields.Selection([
        ('90', '90 يوم'), ('60', '60 يوم'), ('30', '30 يوم'),
        ('current', 'تنبيه الحالة الحالية'),
    ], string='نوع الإشعار', required=True)

    _sql_constraints = [
        ('uniq_notification','unique(model_name,record_id,expiry_date,days_before)','تم إنشاء تنبيه لهذا السجل وتاريخ الانتهاء والفترة مسبقًا.')
    ]

class CrmExpiryService(models.AbstractModel):
    _name = 'crm.expiry.service'
    _description = 'خدمة متابعة انتهاء الصلاحية'

    @api.model
    def action_send_test_notification(self, company_id, branch_id=False):
        """Create a real activity for the caller without waiting for the cron dates."""
        company = self.env['crm.company.record'].browse(company_id).exists()
        if not company:
            return {'success': False, 'message': _('اختر شركة صحيحة أولاً.')}

        branch = self.env['crm.company.branch'].browse(branch_id).exists() if branch_id else False
        if branch and branch.company_id != company:
            branch = False

        user = company.create_uid if company.create_uid and company.create_uid.active else self.env.user
        now = fields.Datetime.context_timestamp(self, fields.Datetime.now())
        branch_name = branch.display_name if branch else _('جميع الفروع')
        summary = _('اختبار إشعار سجلات الشركة — %s') % company.display_name
        note = (
            '<b>%s</b><br/>' % _('هذا إشعار اختباري للتأكد من وصول تنبيهات سجلات الشركة.')
            + '%s: <b>%s</b><br/>' % (_('الشركة'), company.display_name)
            + '%s: <b>%s</b><br/>' % (_('الفرع'), branch_name)
            + '%s: <b>%s</b><br/>' % (_('المستخدم المستلم'), user.display_name)
            + '%s: <b>%s</b><br/>' % (_('وقت الاختبار'), fields.Datetime.to_string(now))
            + '%s<br/>' % _('النتيجة المتوقعة: ظهور هذا النشاط في قائمة أنشطتك وفي سجل الشركة المحددة.')
            + _('التنبيهات الفعلية تُنشأ تلقائياً قبل الانتهاء بـ 90 و60 و30 يوماً.')
        )
        company.activity_schedule(
            'company_records_management.mail_activity_type_record_expiry',
            user_id=user.id,
            date_deadline=fields.Date.context_today(self),
            summary=summary,
            note=note,
        )
        return {
            'success': True,
            'message': _('تم إرسال إشعار اختباري إلى %s وإنشاء نشاط على شركة %s.') % (
                user.display_name, company.display_name,
            ),
        }

    @api.model
    def action_send_current_expiry_notifications(self, company_id=False, branch_id=False):
        """Backfill one activity per current expiry date for expired/near records."""
        if not self.env.user.has_group('company_records_management.group_records_manager'):
            raise AccessError(_('إرسال التنبيهات الحالية متاح لمدير إدارة السجلات فقط.'))
        today = fields.Date.context_today(self)
        horizon = today + timedelta(days=EXPIRY_WARNING_DAYS)
        configs = [
            ('crm.commercial.registration', 'expiration_date', 'company_id', 'branch_ids'),
            ('crm.municipality.license', 'expiration_date', 'branch_id.company_id', 'branch_id'),
            ('crm.civil.defense.license', 'expiration_date', 'branch_id.company_id', 'branch_id'),
            ('crm.lease.contract', 'date_end', 'company_id', 'branch_id'),
        ]
        Notification = self.env['crm.expiry.notification'].sudo()
        sent = skipped = 0
        recipients = set()
        for model_name, date_field, company_field, branch_field in configs:
            Model = self.env[model_name].sudo()
            domain = [(date_field, '<=', horizon)]
            if company_id:
                domain.append((company_field, '=', company_id))
            if branch_id:
                operator = 'in' if branch_field == 'branch_ids' else '='
                domain.append((branch_field, operator, [branch_id] if operator == 'in' else branch_id))
            for rec in Model.search(domain):
                expiry_date = rec[date_field]
                if not expiry_date:
                    continue
                if Notification.search_count([
                    ('model_name', '=', model_name),
                    ('record_id', '=', rec.id),
                    ('expiry_date', '=', expiry_date),
                    ('notification_type', '=', 'current'),
                ]):
                    skipped += 1
                    continue
                user = rec.create_uid if rec.create_uid and rec.create_uid.active else self.env.user
                branch = rec.branch_id if 'branch_id' in rec._fields else False
                company = rec.company_id if 'company_id' in rec._fields else branch.company_id
                days_remaining = get_days_remaining(expiry_date, today)
                status = (
                    _('منتهي منذ %s يوم') % abs(days_remaining)
                    if days_remaining < 0 else
                    (_('ينتهي اليوم') if days_remaining == 0 else _('متبقي %s يوم') % days_remaining)
                )
                summary = _('%s «%s» — %s') % (rec._description, rec.display_name, status)
                note = (
                    '<b>%s</b><br/>' % _('تنبيه متابعة صلاحية سجل')
                    + '%s: %s<br/>' % (_('نوع السجل'), rec._description)
                    + '%s: <b>%s</b><br/>' % (_('السجل'), rec.display_name)
                    + '%s: %s<br/>' % (_('الشركة'), company.display_name if company else '—')
                    + '%s: %s<br/>' % (_('الفرع'), branch.display_name if branch else _('جميع الفروع'))
                    + '%s: <b>%s</b><br/>' % (_('تاريخ الانتهاء'), expiry_date)
                    + '%s: <b>%s</b>' % (_('الحالة'), status)
                )
                Notification.create({
                    'model_name': model_name,
                    'record_id': rec.id,
                    'record_name': rec.display_name,
                    'expiry_date': expiry_date,
                    'days_before': 0,
                    'user_id': user.id,
                    'notification_type': 'current',
                })
                rec.activity_schedule(
                    'company_records_management.mail_activity_type_record_expiry',
                    user_id=user.id,
                    date_deadline=today,
                    summary=summary,
                    note=note,
                )
                recipients.add(user.display_name)
                sent += 1
        return {
            'sent': sent,
            'skipped': skipped,
            'recipients': sorted(recipients),
            'message': _('تم إنشاء %s إشعار، وتم تجاوز %s إشعار موجود مسبقاً.') % (sent, skipped),
        }

    @api.model
    def cron_send_expiry_notifications(self):
        today = fields.Date.context_today(self)
        configs = [
            ('crm.commercial.registration', 'expiration_date', 'company_id'),
            ('crm.municipality.license', 'expiration_date', 'branch_id'),
            ('crm.civil.defense.license', 'expiration_date', 'branch_id'),
            ('crm.lease.contract', 'date_end', 'branch_id'),
        ]
        Notification = self.env['crm.expiry.notification'].sudo()
        for model_name, date_field, owner_field in configs:
            Model = self.env[model_name].sudo()
            for days in (90, 60, 30):
                target = today + timedelta(days=days)
                recs = Model.search([(date_field, '=', target)])
                for rec in recs:
                    if Notification.search_count([
                        ('model_name', '=', model_name),
                        ('record_id', '=', rec.id),
                        ('expiry_date', '=', target),
                        ('days_before', '=', days),
                    ]):
                        continue
                    owner = rec[owner_field]
                    company = owner.company_id if owner and owner._name == 'crm.company.branch' else owner
                    branch = owner if owner and owner._name == 'crm.company.branch' else False
                    # The scheduled action normally runs as an administrator.  Assigning
                    # the activity to the record creator makes it visible to the person
                    # responsible for the business record instead of the cron user.
                    user = rec.create_uid if rec.create_uid and rec.create_uid.active else self.env.user
                    record_type = rec._description
                    context_parts = []
                    if company:
                        context_parts.append(f'الشركة: {company.display_name}')
                    if branch:
                        context_parts.append(f'الفرع: {branch.display_name}')
                    context_text = ' — '.join(context_parts)
                    summary = f'{record_type} «{rec.display_name}» ينتهي بتاريخ {target}'
                    note = (
                        f'<b>تنبيه قبل {days} يومًا</b><br/>'
                        f'نوع السجل: {record_type}<br/>'
                        f'السجل: {rec.display_name}<br/>'
                        f'{context_text + "<br/>" if context_text else ""}'
                        f'تاريخ الانتهاء: <b>{target}</b><br/>'
                        f'المتبقي: {days} يومًا.'
                    )
                    Notification.create({
                        'model_name': model_name,
                        'record_id': rec.id,
                        'record_name': rec.display_name,
                        'expiry_date': target,
                        'days_before': days,
                        'user_id': user.id,
                        'notification_type': str(days),
                    })
                    rec.activity_schedule(
                        'company_records_management.mail_activity_type_record_expiry',
                        user_id=user.id,
                        # It is actionable on the notification day; the expiry date is
                        # stated explicitly in the title and body.
                        date_deadline=today,
                        summary=summary,
                        note=note,
                    )
