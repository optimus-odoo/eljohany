from odoo import api, fields, models

class CrmAuditLog(models.Model):
    _name = 'crm.audit.log'
    _description = 'سجل تدقيق سجلات الشركات'
    _order = 'create_date desc'
    _rec_name = 'display_name'

    display_name = fields.Char(string='الاسم المعروض', compute='_compute_display_name', store=True)
    model_name = fields.Char(string='اسم النموذج', required=True, index=True)
    record_model = fields.Char(string='النموذج الفني للسجل', required=True)
    record_id = fields.Integer(string='رقم السجل', required=True, index=True)
    record_name = fields.Char(string='اسم السجل')
    operation = fields.Selection([
        ('create','إنشاء'),('write','تعديل'),('state','تغيير حالة'),('archive','أرشفة'),
        ('unarchive','إلغاء الأرشفة')
    ], string='العملية', required=True)
    field_name = fields.Char(string='اسم الحقل')
    old_value = fields.Text(string='القيمة السابقة')
    new_value = fields.Text(string='القيمة الجديدة')
    user_id = fields.Many2one('res.users', string='المستخدم', required=True, default=lambda s: s.env.user)
    create_date = fields.Datetime(string='تاريخ الإنشاء', readonly=True)

    @api.depends('record_model','record_name','operation')
    def _compute_display_name(self):
        for r in self:
            r.display_name = f'{r.record_model} - {r.record_name or r.record_id} - {r.operation}'

class CrmAuditMixin(models.AbstractModel):
    _name = 'crm.audit.mixin'
    _description = 'خصائص التدقيق'

    @api.model
    def _audit_value_to_text(self, value):
        """Render scalar and relational values without assuming a singleton."""
        if isinstance(value, models.BaseModel):
            if not value:
                return ''
            return '، '.join(
                str(record.display_name or record.id)
                for record in value.sudo().sorted('id')
            )
        if value in (False, None):
            return ''
        return str(value)

    def _audit_snapshot(self, vals):
        """Freeze old values before write, including records later unlinked."""
        ignored_fields = {'write_uid', 'write_date', 'create_uid', 'create_date'}
        field_names = [
            field_name
            for field_name in vals
            if field_name in self._fields and field_name not in ignored_fields
        ]
        return {
            rec.id: {
                field_name: rec._audit_value_to_text(rec[field_name])
                for field_name in field_names
            }
            for rec in self
        }

    def _audit(self, operation, vals=None, old=None):
        Audit = self.env['crm.audit.log'].sudo()
        vals = vals or {}
        old = old or {}
        for rec in self:
            for field, new in vals.items():
                field_obj = rec._fields.get(field)
                if not field_obj or field in ('write_uid','write_date','create_uid','create_date'):
                    continue
                old_value = rec._audit_value_to_text(old.get(field))
                new_value = rec._audit_value_to_text(
                    rec[field] if rec.exists() else new
                )
                if operation == 'write' and old_value == new_value:
                    continue
                Audit.create({
                    'model_name': rec._description or rec._name,
                    'record_model': rec._name,
                    'record_id': rec.id,
                    'record_name': rec.display_name,
                    'operation': operation,
                    'field_name': field_obj.string,
                    'old_value': old_value,
                    'new_value': new_value,
                    'user_id': self.env.user.id,
                })

class CrmWorkflowMixin(models.AbstractModel):
    _name = 'crm.workflow.mixin'
    _description = 'مسار الاعتماد والأرشفة'

    workflow_state = fields.Selection([
        ('draft','مسودة'), ('submitted','بانتظار الاعتماد'),
        ('approved','معتمد'), ('rejected','مرفوض'), ('archived','مؤرشف')
    ], string='حالة سير العمل', default='draft', tracking=True, index=True)

    def action_submit(self):
        self.write({'workflow_state':'submitted'})
        for rec in self:
            rec._audit('state', {'workflow_state':'submitted'}, {'workflow_state':'draft'})
        return True

    def action_approve(self):
        self.write({'workflow_state':'approved'})
        for rec in self:
            rec._audit('state', {'workflow_state':'approved'}, {'workflow_state':'submitted'})
        return True

    def action_reject(self):
        self.write({'workflow_state':'rejected'})
        for rec in self:
            rec._audit('state', {'workflow_state':'rejected'}, {'workflow_state':'submitted'})
        return True

    def action_archive_record(self):
        self.write({'active': False, 'workflow_state':'archived'})
        for rec in self:
            rec._audit('archive', {'active':False,'workflow_state':'archived'})
        return True

    def action_unarchive_record(self):
        self.write({'active': True, 'workflow_state':'approved'})
        for rec in self:
            rec._audit('unarchive', {'active':True,'workflow_state':'approved'})
        return True
