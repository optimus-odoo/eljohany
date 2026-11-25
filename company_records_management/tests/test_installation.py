import base64
import io
import zipfile
from datetime import date, timedelta
from unittest.mock import patch

from odoo import Command, fields
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestInstallation(TransactionCase):
    """Exercise the installed module through its ordinary user entry points."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = new_test_user(
            cls.env, login='records_install_test',
            groups='base.group_user,company_records_management.group_records_user',
        )
        cls.manager = new_test_user(
            cls.env, login='records_install_manager',
            groups='base.group_user,company_records_management.group_records_manager',
        )
        cls.today = fields.Date.today()
        cls.expiry = cls.today + timedelta(days=30)
        cls.company = cls.env['crm.company.record'].with_user(cls.user).create({
            'name': 'Installation Test Company',
        })
        cls.branch = cls.env['crm.company.branch'].with_user(cls.user).create({
            'name': 'Installation Test Branch', 'company_id': cls.company.id,
        })
        cls.registration = cls.env['crm.commercial.registration'].with_user(cls.user).create({
            'name': 'INSTALL-CR', 'company_id': cls.company.id,
            'branch_ids': [Command.link(cls.branch.id)],
            'issue_date': cls.today, 'expiration_date': cls.expiry,
        })
        cls.lease = cls.env['crm.lease.contract'].with_user(cls.user).create({
            'name': 'INSTALL-LEASE', 'company_id': cls.company.id,
            'branch_id': cls.branch.id, 'signing_date': cls.today,
            'date_start': cls.today, 'date_end': cls.expiry,
            'lessor_name': 'Test Lessor', 'tenant_name': 'Test Tenant',
        })

    def test_views_and_menu_actions(self):
        views = self.env['ir.model.data'].search([
            ('module', '=', 'company_records_management'),
            ('model', '=', 'ir.ui.view'),
        ])
        for data in views:
            view = self.env['ir.ui.view'].browse(data.res_id)
            if view.type == 'qweb':
                continue
            user = self.manager if view.model == 'crm.audit.log' else self.user
            self.env[view.model].with_user(user).get_view(view.id, view.type)
        menu = self.env.ref('company_records_management.menu_pdf')
        self.assertEqual(menu.action, self.env.ref('company_records_management.action_records_pdf'))
        self.assertNotEqual(self.branch.code, 'New')
        root = self.env.ref('company_records_management.menu_root')
        self.assertEqual(root.action, self.env.ref('company_records_management.action_dashboard'))
        self.assertFalse(self.env['ir.ui.menu'].search_count([('parent_id', '=', root.id)]))

    def test_record_workflow_and_audit(self):
        self.registration.action_submit()
        self.assertEqual(self.registration.workflow_state, 'submitted')
        self.lease.action_submit()
        self.assertEqual(self.lease.approval_state, 'submitted')
        self.assertTrue(self.env['crm.audit.log'].search_count([
            ('record_model', '=', self.registration._name),
            ('record_id', '=', self.registration.id), ('operation', '=', 'state'),
        ]))

    def test_audit_supports_multiple_attachments(self):
        attachments = self.env['ir.attachment'].sudo().create([
            {
                'name': 'Audit Attachment A',
                'type': 'binary',
                'datas': base64.b64encode(b'attachment-a'),
                'res_model': self.registration._name,
                'res_id': self.registration.id,
            },
            {
                'name': 'Audit Attachment B',
                'type': 'binary',
                'datas': base64.b64encode(b'attachment-b'),
                'res_model': self.registration._name,
                'res_id': self.registration.id,
            },
        ])
        registration = self.registration.with_user(self.user)
        registration.write({
            'attachment_ids': [Command.set(attachments.ids)],
        })

        registration.write({
            'attachment_ids': [Command.set(attachments[:1].ids)],
        })

        audit = self.env['crm.audit.log'].sudo().search([
            ('record_model', '=', registration._name),
            ('record_id', '=', registration.id),
            ('operation', '=', 'write'),
            ('field_name', '=', registration._fields['attachment_ids'].string),
        ], order='id desc', limit=1)
        self.assertTrue(audit)
        self.assertIn('Audit Attachment A', audit.old_value)
        self.assertIn('Audit Attachment B', audit.old_value)
        self.assertIn('Audit Attachment A', audit.new_value)
        self.assertNotIn('Audit Attachment B', audit.new_value)

    def test_dashboard(self):
        rows = self.env['crm.dashboard'].with_user(self.user).get_data()
        self.assertEqual(len(rows), 4)
        self.assertGreaterEqual(rows[0]['soon'], 1)
        self.assertGreaterEqual(rows[3]['soon'], 1)
        alerts = self.env['crm.dashboard'].with_user(self.user).get_expiry_alerts(
            company_id=self.company.id,
            branch_id=self.branch.id,
        )
        self.assertEqual({alert['record_name'] for alert in alerts}, {'INSTALL-CR', 'INSTALL-LEASE'})
        self.assertTrue(all(alert['expiry_date'] == str(self.expiry) for alert in alerts))
        self.assertTrue(all(alert['days_remaining'] == 30 for alert in alerts))

    def test_countdown_recomputes_each_day_for_every_expiring_record_type(self):
        expiry = date(2026, 12, 31)
        municipality = self.env['crm.municipality.license'].with_user(
            self.user
        ).create({
            'name': 'INSTALL-MUNICIPALITY',
            'branch_id': self.branch.id,
            'expiration_date': expiry,
        })
        civil_defense = self.env['crm.civil.defense.license'].with_user(
            self.user
        ).create({
            'name': 'INSTALL-CIVIL',
            'branch_id': self.branch.id,
            'issue_date': date(2026, 1, 1),
            'expiration_date': expiry,
        })
        self.registration.expiration_date = expiry
        self.lease.date_end = expiry

        expirable_records = (
            self.registration,
            municipality,
            civil_defense,
        )
        for today, expected_days, expected_status in (
            (date(2026, 9, 1), 121, 'valid'),
            (date(2026, 11, 14), 47, 'soon'),
            (date(2026, 11, 15), 46, 'soon'),
            (date(2026, 12, 31), 0, 'soon'),
            (date(2027, 1, 1), -1, 'expired'),
        ):
            with patch('odoo.fields.Date.context_today', return_value=today):
                for record in expirable_records:
                    record.invalidate_recordset(['status', 'days_remaining'])
                self.lease.invalidate_recordset(['state', 'days_remaining'])
                self.assertTrue(
                    all(
                        record.days_remaining == expected_days
                        for record in expirable_records
                    )
                )
                self.assertEqual(self.lease.days_remaining, expected_days)
                self.assertTrue(
                    all(
                        record.status == expected_status
                        for record in expirable_records
                    )
                )
                expected_lease_state = (
                    'active' if expected_status == 'valid' else expected_status
                )
                self.assertEqual(self.lease.state, expected_lease_state)

    def test_compliance_dashboard_uses_lease_end_date(self):
        data = self.env['crm.compliance.dashboard'].with_user(
            self.user
        ).get_data()
        self.assertGreaterEqual(data['leases'], 1)
        self.assertGreaterEqual(
            data['expired'] + data['d30'] + data['d60'] + data['d90'],
            2,
        )

    def test_workspace_scope(self):
        other_branch = self.env['crm.company.branch'].with_user(self.user).create({
            'name': 'Other Branch', 'company_id': self.company.id,
        })
        dashboard = self.env['crm.dashboard'].with_user(self.user)
        rows = dashboard.get_data(company_id=self.company.id, branch_id=self.branch.id)
        self.assertEqual(rows[0]['total'], 1)
        self.assertEqual(rows[3]['total'], 1)
        rows = dashboard.get_data(company_id=self.company.id, branch_id=other_branch.id)
        self.assertTrue(all(row['total'] == 0 for row in rows))
        other_company = self.env['crm.company.record'].with_user(self.user).create({'name': 'Other Company'})
        rows = dashboard.get_data(company_id=other_company.id)
        self.assertTrue(all(row['total'] == 0 for row in rows))

    def test_scoped_export_includes_leases(self):
        wizard = self.env['crm.records.xlsx.wizard'].with_user(self.user)
        for company_id, expected in ((self.company.id, True), (-1, False)):
            action = wizard.with_context(records_company_id=company_id, records_branch_id=self.branch.id).action_export()
            attachment_id = int(action['url'].split('/')[3].split('?')[0])
            attachment = self.env['ir.attachment'].with_user(self.user).browse(attachment_id)
            with zipfile.ZipFile(io.BytesIO(base64.b64decode(attachment.datas))) as workbook:
                strings = workbook.read('xl/sharedStrings.xml')
                self.assertEqual(b'INSTALL-CR' in strings, expected)
                self.assertEqual(b'INSTALL-LEASE' in strings, expected)

    def test_expiry_cron_is_recurring_and_idempotent(self):
        cron = self.env.ref('company_records_management.ir_cron_expiry_notifications')
        self.assertEqual(cron.numbercall, -1)
        service = self.env['crm.expiry.service'].with_user(self.user)
        service.cron_send_expiry_notifications()
        service.cron_send_expiry_notifications()
        activity_type = self.env.ref('company_records_management.mail_activity_type_record_expiry')
        for record in (self.registration, self.lease):
            self.assertEqual(self.env['crm.expiry.notification'].search_count([
                ('model_name', '=', record._name), ('record_id', '=', record.id),
                ('days_before', '=', 30),
            ]), 1)
            self.assertEqual(self.env['mail.activity'].search_count([
                ('res_model', '=', record._name), ('res_id', '=', record.id),
                ('activity_type_id', '=', activity_type.id),
                ('user_id', '=', self.user.id),
            ]), 1)
            activity = self.env['mail.activity'].search([
                ('res_model', '=', record._name), ('res_id', '=', record.id),
                ('activity_type_id', '=', activity_type.id),
            ])
            self.assertEqual(activity.date_deadline, self.today)
            self.assertIn(record.display_name, activity.summary)
            self.assertIn(str(self.expiry), activity.summary)

    def test_dashboard_test_notification_creates_clear_activity_for_current_user(self):
        result = self.env['crm.expiry.service'].with_user(self.user).action_send_test_notification(
            company_id=self.company.id,
            branch_id=self.branch.id,
        )
        self.assertTrue(result['success'])
        activity = self.env['mail.activity'].search([
            ('res_model', '=', self.company._name),
            ('res_id', '=', self.company.id),
            ('user_id', '=', self.user.id),
            ('summary', 'ilike', 'Installation Test Company'),
        ], limit=1)
        self.assertTrue(activity)
        self.assertEqual(activity.date_deadline, self.today)
        self.assertIn('Installation Test Branch', activity.note)
        self.assertIn(self.user.display_name, activity.note)

    def test_current_expiry_notifications_are_for_creator_and_idempotent(self):
        service = self.env['crm.expiry.service'].with_user(self.manager)
        first = service.action_send_current_expiry_notifications(company_id=self.company.id)
        second = service.action_send_current_expiry_notifications(company_id=self.company.id)
        self.assertEqual(first['sent'], 2)
        self.assertEqual(second['sent'], 0)
        self.assertEqual(second['skipped'], 2)
        activities = self.env['mail.activity'].search([
            ('res_model', 'in', [self.registration._name, self.lease._name]),
            ('res_id', 'in', [self.registration.id, self.lease.id]),
            ('user_id', '=', self.user.id),
        ])
        self.assertEqual(len(activities), 2)
        self.assertTrue(all(str(self.expiry) in activity.note for activity in activities))

    def test_expiry_notification_is_recreated_after_renewal(self):
        service = self.env['crm.expiry.service'].with_user(self.user)
        service.cron_send_expiry_notifications()
        renewed_expiry = self.today + timedelta(days=60)
        self.registration.expiration_date = renewed_expiry
        service.cron_send_expiry_notifications()
        notifications = self.env['crm.expiry.notification'].search([
            ('model_name', '=', self.registration._name),
            ('record_id', '=', self.registration.id),
        ])
        self.assertEqual(len(notifications), 2)
        self.assertEqual(set(notifications.mapped('expiry_date')), {self.expiry, renewed_expiry})

    def test_xlsx_export_as_records_user(self):
        wizard = self.env['crm.records.xlsx.wizard'].with_user(self.user).create({})
        action = wizard.action_export()
        attachment_id = int(action['url'].split('/')[3].split('?')[0])
        attachment = self.env['ir.attachment'].with_user(self.user).browse(attachment_id)
        with zipfile.ZipFile(io.BytesIO(base64.b64decode(attachment.datas))) as workbook:
            self.assertIn(b'INSTALL-CR', workbook.read('xl/sharedStrings.xml'))

    def test_report_html(self):
        html, _ = self.env['ir.actions.report'].with_user(self.user)._render_qweb_html(
            'company_records_management.action_records_pdf', self.company.ids,
        )
        self.assertIn(b'Installation Test Company', html)
        self.assertIn(b'Installation Test Branch', html)
