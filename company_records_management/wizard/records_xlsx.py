from odoo import fields, models
from odoo.exceptions import UserError
import io, base64

from ..models.expiry_utils import get_days_remaining
try:
    import xlsxwriter
except ImportError:
    xlsxwriter = None

class RecordsXlsxWizard(models.TransientModel):
    _name='crm.records.xlsx.wizard'
    _description='تصدير السجلات إلى Excel'

    def action_export(self):
        self = self.sudo()
        if not xlsxwriter:
            raise UserError('مكتبة xlsxwriter غير مثبتة على خادم Odoo.')
        output=io.BytesIO()
        wb=xlsxwriter.Workbook(output, {'in_memory': True})
        ws=wb.add_worksheet('السجلات')
        headers=['النوع','الرقم/الاسم','الفرع/الشركة','تاريخ الانتهاء','الحالة','الأيام المتبقية']
        for c,h in enumerate(headers): ws.write(0,c,h)
        row=1
        datasets=[
            ('السجل التجاري','crm.commercial.registration','company_id'),
            ('الرخصة البلدية','crm.municipality.license','branch_id'),
            ('الدفاع المدني','crm.civil.defense.license','branch_id'),
            ('عقود الإيجار','crm.lease.contract','branch_id'),
        ]
        for label,model,owner in datasets:
            domain = []
            company_id = self.env.context.get('records_company_id')
            branch_id = self.env.context.get('records_branch_id')
            if company_id:
                company_field = 'company_id' if owner == 'company_id' else 'branch_id.company_id'
                domain.append((company_field, '=', company_id))
            if branch_id:
                domain.append(('branch_ids', 'in', [branch_id]) if model == 'crm.commercial.registration' else ('branch_id', '=', branch_id))
            for r in self.env[model].search(domain):
                is_lease = model == 'crm.lease.contract'
                expiry = r.date_end if is_lease else r.expiration_date
                ws.write(row,0,label); ws.write(row,1,r.display_name)
                ws.write(row,2,r[owner].display_name if r[owner] else '')
                ws.write(row,3,str(expiry or ''))
                ws.write(row,4,(r.state if is_lease else r.status) or '')
                ws.write(
                    row,
                    5,
                    get_days_remaining(expiry, fields.Date.context_today(r)),
                )
                row+=1
        wb.close(); output.seek(0)
        attachment=self.env['ir.attachment'].sudo().create({
            'name':'company_records.xlsx','type':'binary',
            'datas':base64.b64encode(output.read()),
            'mimetype':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        })
        return {'type':'ir.actions.act_url','url':f'/web/content/{attachment.id}?download=true','target':'self'}
