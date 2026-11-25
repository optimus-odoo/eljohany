# -*- coding: utf-8 -*-

from odoo import models, fields, api
from datetime import datetime, date, timedelta
from dateutil.relativedelta import relativedelta
from markupsafe import Markup


class EmployeeDocument(models.Model):
    _name = 'employee.document'
    _description = 'Employee Document Tap'

    name = fields.Char(string="Description", required=False, )
    d_attachment_ids = fields.Many2many('ir.attachment', 'attachment_rel1', 'passport_ref2', 'attach_ref13',
                                        string="Attachment", )
    expiration_date = fields.Date(string="Expiration Date", required=False, )
    days_to_notify = fields.Integer(string="", required=False, )
    notify_ids = fields.Many2many(comodel_name="res.users", string="", required=False, )
    employee_id = fields.Many2one(comodel_name="hr.employee", string="", required=False, )

    def send_notify_using_date(self):
        records = self.env["employee.document"].search([])
        for rec in records:
            duration_day = rec.days_to_notify
            future_date = datetime.today().date() + relativedelta(days=int(duration_day))
            if future_date == rec.expiration_date:
                partners = [user.partner_id.id for user in rec.notify_ids]
                if partners:
                    thread_pool = self.env['mail.thread']
                    thread_pool.sudo().message_notify(
                        partner_ids=partners,
                        subject="  Notify For Upcoming Employee Document  ",
                        body=Markup(
                            " Employee  %s  Has Upcoming Document  " % rec.employee_id.name + '<a target=_BLANK href="/web?#id=' + str(
                                rec.employee_id.id) + '&view_type=form&model=hr.employee&action=" style="font-weight: bold">' + str(
                                rec.name) + '</a>' + "  And will Expiration In  %s " % rec.expiration_date),
                        email_from=self.env.user.email, )
class HrEmployeeInh(models.Model):
    _inherit = 'hr.employee'

    employee_document_ids = fields.One2many(comodel_name="employee.document", inverse_name="employee_id", string="",
                                            required=False, )
    name_translate = fields.Char(string="", required=False, )

