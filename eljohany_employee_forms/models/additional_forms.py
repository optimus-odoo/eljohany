from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


def _employee_number(employee):
    if "registration_number" in employee._fields and employee.registration_number:
        return employee.registration_number
    return employee.barcode or str(employee.id)


class HrAdditionalFormMixin(models.AbstractModel):
    _name = "hr.additional.form.mixin"
    _description = "ضوابط النماذج الإضافية للموظفين"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    _sequence_code = False
    _editable_states = {"draft"}
    _editable_after_approval_fields = set()

    name = fields.Char(
        string="رقم النموذج",
        default="جديد",
        readonly=True,
        copy=False,
        tracking=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="الشركة",
        required=True,
        default=lambda self: self.env.company,
        tracking=True,
    )
    branch_id = fields.Many2one(
        "res.branch",
        string="الفرع",
        domain="[('company_id', '=', company_id)]",
        tracking=True,
    )
    document_date = fields.Date(
        string="تاريخ النموذج",
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    state = fields.Selection(
        [
            ("draft", "مسودة"),
            ("submitted", "مرسل للاعتماد"),
            ("approved", "معتمد"),
            ("rejected", "مرفوض"),
            ("cancelled", "ملغي"),
        ],
        string="الحالة",
        default="draft",
        required=True,
        readonly=True,
        copy=False,
        tracking=True,
    )
    submitted_by = fields.Many2one(
        "res.users", string="أرسله", readonly=True, copy=False
    )
    submitted_at = fields.Datetime(
        string="تاريخ الإرسال", readonly=True, copy=False
    )
    approved_by = fields.Many2one(
        "res.users", string="اعتمده", readonly=True, copy=False
    )
    approved_at = fields.Datetime(
        string="تاريخ الاعتماد", readonly=True, copy=False
    )
    rejection_reason = fields.Text(string="سبب الرفض", copy=False, tracking=True)
    cancellation_reason = fields.Text(string="سبب الإلغاء", copy=False, tracking=True)

    @api.model_create_multi
    def create(self, vals_list):
        protected_fields = {
            "state",
            "submitted_by",
            "submitted_at",
            "approved_by",
            "approved_at",
        }
        for vals in vals_list:
            if protected_fields.intersection(vals) and not self.env.context.get(
                "employee_forms_workflow"
            ):
                raise AccessError(
                    _("لا يمكن تعيين حالة الاعتماد أو بيانات التدقيق عند إنشاء النموذج.")
                )
            if vals.get("name", "جديد") == "جديد" and self._sequence_code:
                company = self.env["res.company"].browse(
                    vals.get("company_id") or self.env.company.id
                )
                vals["name"] = (
                    self.env["ir.sequence"]
                    .with_company(company)
                    .next_by_code(self._sequence_code)
                    or "جديد"
                )
        return super().create(vals_list)

    @api.constrains("company_id", "branch_id")
    def _check_branch_company(self):
        for record in self:
            if record.branch_id and record.branch_id.company_id != record.company_id:
                raise ValidationError(_("يجب أن يتبع الفرع الشركة المحددة."))

    def _check_manager(self):
        if not self.env.user.has_group(
            "eljohany_employee_forms.group_employee_forms_manager"
        ):
            raise AccessError(_("هذه العملية متاحة لمدير نماذج الموظفين فقط."))

    def _before_approve(self):
        return True

    def _after_approve(self):
        return True

    def _ensure_printable(self, allow_returned=False):
        allowed_states = {"approved", "returned"} if allow_returned else {"approved"}
        if any(record.state not in allowed_states for record in self):
            raise UserError(_("لا يمكن طباعة النموذج قبل اعتماده."))

    def action_submit(self):
        self._check_manager()
        for record in self:
            if record.state != "draft":
                raise UserError(_("يمكن إرسال النماذج المسودة فقط."))
            record.with_context(employee_forms_workflow=True).write(
                {
                    "state": "submitted",
                    "submitted_by": self.env.user.id,
                    "submitted_at": fields.Datetime.now(),
                }
            )

    def action_approve(self):
        self._check_manager()
        for record in self:
            if record.state != "submitted":
                raise UserError(_("يمكن اعتماد النماذج المرسلة فقط."))
            record._before_approve()
            record.with_context(employee_forms_workflow=True).write(
                {
                    "state": "approved",
                    "approved_by": self.env.user.id,
                    "approved_at": fields.Datetime.now(),
                    "rejection_reason": False,
                }
            )
            record._after_approve()

    def action_reject(self):
        self._check_manager()
        for record in self:
            if record.state != "submitted":
                raise UserError(_("يمكن رفض النماذج المرسلة فقط."))
            if not record.rejection_reason:
                raise ValidationError(_("أدخل سبب الرفض أولًا."))
            record.with_context(employee_forms_workflow=True).write(
                {"state": "rejected"}
            )

    def action_cancel(self):
        self._check_manager()
        for record in self:
            if record.state not in ("draft", "submitted"):
                raise UserError(_("يمكن إلغاء النموذج المسودة أو المرسل فقط."))
            record.with_context(employee_forms_workflow=True).write(
                {"state": "cancelled"}
            )

    def action_reset_to_draft(self):
        self._check_manager()
        for record in self:
            if record.state not in ("rejected", "cancelled"):
                raise UserError(_("يمكن إعادة النموذج المرفوض أو الملغي فقط للمسودة."))
            record.with_context(employee_forms_workflow=True).write(
                {
                    "state": "draft",
                    "submitted_by": False,
                    "submitted_at": False,
                    "approved_by": False,
                    "approved_at": False,
                    "rejection_reason": False,
                    "cancellation_reason": False,
                }
            )

    def write(self, vals):
        workflow_fields = {
            "state",
            "submitted_by",
            "submitted_at",
            "approved_by",
            "approved_at",
        }
        if workflow_fields.intersection(vals) and not self.env.context.get(
            "employee_forms_workflow"
        ):
            raise AccessError(_("حقول الاعتماد تُعدّل من أزرار الإجراءات فقط."))

        chatter_fields = {
            "message_follower_ids",
            "activity_ids",
            "message_ids",
            "rejection_reason",
            "cancellation_reason",
        }
        business_fields = set(vals) - chatter_fields - workflow_fields
        if business_fields and not self.env.context.get("employee_forms_workflow"):
            for record in self:
                allowed = (
                    set(record._editable_after_approval_fields)
                    if record.state == "approved"
                    else set()
                )
                blocked = business_fields - allowed
                if record.state not in set(record._editable_states) and blocked:
                    raise AccessError(_("لا يمكن تعديل بيانات النموذج بعد إرساله."))
        return super().write(vals)

    def unlink(self):
        self._check_manager()
        if any(record.state not in ("draft", "cancelled") for record in self):
            raise UserError(_("يمكن حذف النماذج المسودة أو الملغاة فقط."))
        return super().unlink()


class HrJobOffer(models.Model):
    _name = "hr.job.offer"
    _description = "عرض وظيفي"
    _inherit = "hr.additional.form.mixin"
    _order = "document_date desc, id desc"
    _sequence_code = "hr.job.offer"

    candidate_name = fields.Char(string="اسم المرشح", required=True, tracking=True)
    candidate_id_number = fields.Char(string="رقم الهوية / الإقامة", tracking=True)
    candidate_email = fields.Char(string="البريد الإلكتروني")
    candidate_phone = fields.Char(string="رقم الجوال")
    employee_id = fields.Many2one(
        "hr.employee",
        string="الموظف بعد التعيين",
        domain="[('company_id', '=', company_id)]",
        tracking=True,
    )
    department_id = fields.Many2one(
        "hr.department",
        string="الإدارة",
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        tracking=True,
    )
    job_id = fields.Many2one(
        "hr.job",
        string="المسمى الوظيفي",
        required=True,
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        tracking=True,
    )
    work_location = fields.Char(string="مقر العمل")
    expected_joining_date = fields.Date(string="تاريخ المباشرة المتوقع", required=True)
    contract_duration = fields.Char(string="مدة العقد", default="سنة واحدة")
    probation_days = fields.Integer(string="مدة التجربة بالأيام", default=90)
    working_hours = fields.Char(string="ساعات العمل", default="وفق نظام العمل المعتمد")
    currency_id = fields.Many2one(
        "res.currency",
        string="العملة",
        related="company_id.currency_id",
        readonly=True,
    )
    basic_salary = fields.Monetary(
        string="الراتب الأساسي", currency_field="currency_id", required=True, tracking=True
    )
    allowance_ids = fields.One2many(
        "hr.job.offer.allowance", "offer_id", string="البدلات والمزايا", copy=True
    )
    recurring_allowance_total = fields.Monetary(
        string="إجمالي البدلات الشهرية",
        currency_field="currency_id",
        compute="_compute_totals",
        store=True,
    )
    one_time_allowance_total = fields.Monetary(
        string="إجمالي المزايا لمرة واحدة",
        currency_field="currency_id",
        compute="_compute_totals",
        store=True,
    )
    monthly_total = fields.Monetary(
        string="الإجمالي الشهري",
        currency_field="currency_id",
        compute="_compute_totals",
        store=True,
    )
    offer_valid_until = fields.Date(string="العرض صالح حتى", required=True)
    terms = fields.Html(
        string="الشروط والأحكام",
        default=(
            "<p>يخضع هذا العرض للأنظمة والسياسات المعتمدة لدى الشركة، "
            "ولا يُعد عقد عمل نهائيًا إلا بعد استكمال المتطلبات وتوقيع العقد.</p>"
        ),
    )

    @api.depends("basic_salary", "allowance_ids.amount", "allowance_ids.frequency")
    def _compute_totals(self):
        for offer in self:
            recurring = sum(
                offer.allowance_ids.filtered(
                    lambda line: line.frequency == "monthly"
                ).mapped("amount")
            )
            one_time = sum(
                offer.allowance_ids.filtered(
                    lambda line: line.frequency == "one_time"
                ).mapped("amount")
            )
            offer.recurring_allowance_total = recurring
            offer.one_time_allowance_total = one_time
            offer.monthly_total = offer.basic_salary + recurring

    @api.constrains(
        "basic_salary",
        "probation_days",
        "offer_valid_until",
        "expected_joining_date",
        "document_date",
    )
    def _check_offer_values(self):
        for offer in self:
            if offer.basic_salary <= 0:
                raise ValidationError(_("يجب أن يكون الراتب الأساسي أكبر من صفر."))
            if offer.probation_days < 0:
                raise ValidationError(_("مدة التجربة لا يمكن أن تكون سالبة."))
            if offer.offer_valid_until and offer.offer_valid_until < offer.document_date:
                raise ValidationError(_("تاريخ انتهاء العرض يجب ألا يسبق تاريخ العرض."))
            if (
                offer.expected_joining_date
                and offer.expected_joining_date < offer.document_date
            ):
                raise ValidationError(_("تاريخ المباشرة المتوقع يجب ألا يسبق تاريخ العرض."))

    @api.constrains("employee_id", "company_id", "department_id", "job_id")
    def _check_offer_company(self):
        for offer in self.filtered("employee_id"):
            if offer.employee_id.company_id != offer.company_id:
                raise ValidationError(_("الموظف المرتبط لا يتبع شركة العرض."))
        for offer in self:
            if offer.department_id.company_id and (
                offer.department_id.company_id != offer.company_id
            ):
                raise ValidationError(_("الإدارة المحددة لا تتبع شركة العرض."))
            if offer.job_id.company_id and offer.job_id.company_id != offer.company_id:
                raise ValidationError(_("المسمى الوظيفي لا يتبع شركة العرض."))

    def _before_approve(self):
        self._check_offer_values()
        self._check_offer_company()
        return super()._before_approve()

    def action_print(self):
        self._ensure_printable()
        return self.env.ref(
            "eljohany_employee_forms.action_report_job_offer"
        ).report_action(self)


class HrJobOfferAllowance(models.Model):
    _name = "hr.job.offer.allowance"
    _description = "بدل عرض وظيفي"
    _order = "sequence, id"

    sequence = fields.Integer(default=10)
    offer_id = fields.Many2one(
        "hr.job.offer", required=True, ondelete="cascade", index=True
    )
    name = fields.Char(string="اسم البدل / الميزة", required=True)
    frequency = fields.Selection(
        [("monthly", "شهري"), ("one_time", "مرة واحدة")],
        string="الدورية",
        required=True,
        default="monthly",
    )
    amount = fields.Monetary(string="القيمة", required=True, currency_field="currency_id")
    currency_id = fields.Many2one(
        related="offer_id.currency_id", readonly=True, store=True
    )
    notes = fields.Char(string="ملاحظات")

    @api.constrains("amount")
    def _check_amount(self):
        if any(line.amount < 0 for line in self):
            raise ValidationError(_("قيمة البدل لا يمكن أن تكون سالبة."))

    @api.model_create_multi
    def create(self, vals_list):
        offers = self.env["hr.job.offer"].browse(
            [vals.get("offer_id") for vals in vals_list if vals.get("offer_id")]
        )
        if any(offer.state != "draft" for offer in offers):
            raise AccessError(_("لا يمكن إضافة بدلات بعد إرسال العرض للاعتماد."))
        return super().create(vals_list)

    def write(self, vals):
        if any(line.offer_id.state != "draft" for line in self):
            raise AccessError(_("لا يمكن تعديل البدلات بعد إرسال العرض للاعتماد."))
        return super().write(vals)

    def unlink(self):
        if any(line.offer_id.state != "draft" for line in self):
            raise AccessError(_("لا يمكن حذف البدلات بعد إرسال العرض للاعتماد."))
        return super().unlink()


class HrWorkCommencement(models.Model):
    _name = "hr.work.commencement"
    _description = "نموذج مباشرة عمل"
    _inherit = "hr.additional.form.mixin"
    _order = "commencement_date desc, id desc"
    _sequence_code = "hr.work.commencement"
    _editable_states = {"draft", "submitted", "approved", "rejected", "cancelled"}

    employee_id = fields.Many2one(
        "hr.employee",
        string="الموظف",
        required=True,
        domain="[('company_id', '=', company_id)]",
        tracking=True,
    )
    commencement_type = fields.Selection(
        [("new", "مباشرة موظف جديد"), ("after_leave", "مباشرة بعد العودة من الإجازة")],
        string="نوع المباشرة",
        required=True,
        default="new",
        tracking=True,
    )
    commencement_date = fields.Date(
        string="تاريخ المباشرة", required=True, default=fields.Date.context_today, tracking=True
    )
    leave_id = fields.Many2one(
        "hr.leave",
        string="الإجازة المرتبطة",
        domain="[('employee_id', '=', employee_id), ('state', '=', 'validate')]",
    )
    department_id = fields.Many2one("hr.department", string="الإدارة", readonly=True)
    job_id = fields.Many2one("hr.job", string="المسمى الوظيفي", readonly=True)
    manager_id = fields.Many2one("hr.employee", string="المدير المباشر", readonly=True)
    employee_number = fields.Char(string="الرقم الوظيفي", readonly=True)
    work_location = fields.Char(string="مقر العمل")
    notes = fields.Text(string="ملاحظات")

    @api.model
    def _employee_values(self, employee):
        employee = employee.sudo()
        return {
            "company_id": employee.company_id.id,
            "branch_id": employee.branch_id.id,
            "department_id": employee.department_id.id,
            "job_id": employee.job_id.id,
            "manager_id": employee.parent_id.id,
            "employee_number": _employee_number(employee),
        }

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            employee = self.env["hr.employee"].sudo().browse(vals.get("employee_id"))
            if employee:
                for key, value in self._employee_values(employee).items():
                    vals.setdefault(key, value)
        return super().create(vals_list)

    @api.onchange("employee_id")
    def _onchange_employee(self):
        if self.employee_id:
            self.update(self._employee_values(self.employee_id))

    @api.onchange("commencement_type")
    def _onchange_commencement_type(self):
        if self.commencement_type != "after_leave":
            self.leave_id = False

    @api.constrains(
        "employee_id",
        "company_id",
        "leave_id",
        "commencement_type",
        "commencement_date",
    )
    def _check_commencement(self):
        for record in self:
            if record.employee_id.company_id != record.company_id:
                raise ValidationError(_("يجب أن يتبع الموظف الشركة المحددة."))
            if record.commencement_type == "after_leave":
                if not record.leave_id:
                    raise ValidationError(_("يجب تحديد الإجازة عند المباشرة بعد الإجازة."))
                if record.leave_id.employee_id != record.employee_id:
                    raise ValidationError(_("الإجازة المحددة لا تخص الموظف."))
                if record.leave_id.state != "validate":
                    raise ValidationError(_("يجب أن تكون الإجازة المرتبطة معتمدة."))
                if (
                    record.leave_id.request_date_to
                    and record.commencement_date < record.leave_id.request_date_to
                ):
                    raise ValidationError(
                        _("تاريخ المباشرة لا يمكن أن يسبق تاريخ نهاية الإجازة.")
                    )
            elif record.leave_id:
                raise ValidationError(
                    _("لا تُحدد إجازة مرتبطة إلا لنموذج المباشرة بعد الإجازة.")
                )

    def _before_approve(self):
        self._check_commencement()
        for record in self:
            employee_values = record._employee_values(record.employee_id)
            employee_values["branch_id"] = record.branch_id.id
            record.with_context(employee_forms_workflow=True).write(
                employee_values
            )
        return super()._before_approve()

    def action_print(self):
        self._ensure_printable()
        return self.env.ref(
            "eljohany_employee_forms.action_report_work_commencement"
        ).report_action(self)


class HrVehicleHandover(models.Model):
    _name = "hr.vehicle.handover"
    _description = "نموذج استلام سيارة"
    _inherit = "hr.additional.form.mixin"
    _order = "handover_date desc, id desc"
    _sequence_code = "hr.vehicle.handover"
    _editable_after_approval_fields = {
        "return_date",
        "return_odometer",
        "return_condition",
    }

    employee_id = fields.Many2one(
        "hr.employee",
        string="الموظف المستلم",
        required=True,
        domain="[('company_id', '=', company_id)]",
        tracking=True,
    )
    vehicle_id = fields.Many2one(
        "fleet.vehicle",
        string="السيارة",
        required=True,
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        tracking=True,
    )
    handover_date = fields.Date(
        string="تاريخ الاستلام", required=True, default=fields.Date.context_today, tracking=True
    )
    odometer = fields.Float(string="قراءة العداد عند الاستلام", required=True)
    fuel_level = fields.Selection(
        [("empty", "فارغ"), ("quarter", "ربع"), ("half", "نصف"), ("three_quarters", "ثلاثة أرباع"), ("full", "ممتلئ")],
        string="مستوى الوقود",
        required=True,
    )
    keys_count = fields.Integer(string="عدد المفاتيح", default=1, required=True)
    vehicle_condition = fields.Text(string="حالة السيارة عند الاستلام", required=True)
    accessories = fields.Text(string="الملحقات المسلمة")
    responsibility_terms = fields.Html(
        string="إقرار ومسؤوليات المستلم",
        required=True,
        default=(
            "<p>أقر باستلام السيارة والملحقات الموضحة أعلاه بالحالة المبينة، "
            "وأتعهد بالمحافظة عليها واستخدامها في الأغراض المصرح بها، والالتزام "
            "بأنظمة المرور وسياسات الشركة، والإبلاغ فورًا عن أي حادث أو عطل أو فقد.</p>"
        ),
    )
    expected_return_date = fields.Date(string="تاريخ الإعادة المتوقع")
    return_date = fields.Date(string="تاريخ الإعادة")
    return_odometer = fields.Float(string="قراءة العداد عند الإعادة")
    return_condition = fields.Text(string="حالة السيارة عند الإعادة")
    state = fields.Selection(selection_add=[("returned", "تمت إعادة السيارة")], ondelete={"returned": "set default"})

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            employee = self.env["hr.employee"].sudo().browse(vals.get("employee_id"))
            if employee:
                vals.setdefault("company_id", employee.company_id.id)
                vals.setdefault("branch_id", employee.branch_id.id)
        return super().create(vals_list)

    @api.onchange("employee_id")
    def _onchange_employee(self):
        if self.employee_id:
            self.company_id = self.employee_id.company_id
            self.branch_id = self.employee_id.branch_id

    @api.constrains(
        "employee_id",
        "company_id",
        "vehicle_id",
        "odometer",
        "keys_count",
        "handover_date",
        "expected_return_date",
        "return_date",
    )
    def _check_vehicle_handover(self):
        for record in self:
            if record.employee_id.company_id != record.company_id:
                raise ValidationError(_("يجب أن يتبع الموظف الشركة المحددة."))
            if record.vehicle_id.company_id and record.vehicle_id.company_id != record.company_id:
                raise ValidationError(_("السيارة المحددة لا تتبع الشركة."))
            if record.odometer < 0 or record.keys_count < 0:
                raise ValidationError(_("قراءة العداد وعدد المفاتيح لا يمكن أن يكونا سالبين."))
            if (
                record.expected_return_date
                and record.expected_return_date < record.handover_date
            ):
                raise ValidationError(
                    _("تاريخ الإعادة المتوقع لا يمكن أن يسبق تاريخ الاستلام.")
                )
            if record.return_date and record.return_date < record.handover_date:
                raise ValidationError(_("تاريخ الإعادة لا يمكن أن يسبق تاريخ الاستلام."))

    def _before_approve(self):
        self._check_vehicle_handover()
        for record in self:
            self.env.cr.execute(
                "SELECT id FROM fleet_vehicle WHERE id = %s FOR UPDATE",
                [record.vehicle_id.id],
            )
            conflict = self.search_count(
                [
                    ("id", "!=", record.id),
                    ("vehicle_id", "=", record.vehicle_id.id),
                    ("state", "=", "approved"),
                ]
            )
            if conflict:
                raise ValidationError(_("السيارة مسلمة حاليًا في نموذج آخر معتمد."))
        return super()._before_approve()

    def action_mark_returned(self):
        self._check_manager()
        for record in self:
            if record.state != "approved":
                raise UserError(_("يمكن تسجيل الإعادة للنماذج المعتمدة فقط."))
            if not record.return_date or not record.return_condition:
                raise ValidationError(_("أدخل تاريخ الإعادة وحالة السيارة عند الإعادة."))
            if record.return_odometer < record.odometer:
                raise ValidationError(_("قراءة عداد الإعادة لا يمكن أن تقل عن قراءة الاستلام."))
            record.with_context(employee_forms_workflow=True).write(
                {"state": "returned"}
            )

    def action_print(self):
        self._ensure_printable(allow_returned=True)
        return self.env.ref(
            "eljohany_employee_forms.action_report_vehicle_handover"
        ).report_action(self)


class FleetVehicle(models.Model):
    _inherit = "fleet.vehicle"

    employee_handover_ids = fields.One2many(
        "hr.vehicle.handover",
        "vehicle_id",
        string="نماذج استلام الموظفين",
        groups="eljohany_employee_forms.group_employee_forms_manager",
    )
    employee_handover_count = fields.Integer(
        string="عدد نماذج الاستلام",
        compute="_compute_employee_handover_count",
        groups="eljohany_employee_forms.group_employee_forms_manager",
    )

    def _compute_employee_handover_count(self):
        grouped = self.env["hr.vehicle.handover"]._read_group(
            [("vehicle_id", "in", self.ids)],
            ["vehicle_id"],
            ["__count"],
        )
        count_by_vehicle = {vehicle.id: count for vehicle, count in grouped}
        for vehicle in self:
            vehicle.employee_handover_count = count_by_vehicle.get(vehicle.id, 0)

    def action_open_employee_handovers(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "eljohany_employee_forms.vehicle_handover_action"
        )
        action["domain"] = [("vehicle_id", "=", self.id)]
        action["context"] = {
            "default_vehicle_id": self.id,
            "default_company_id": self.company_id.id,
        }
        return action


class HrMobileSimCategory(models.Model):
    _name = "hr.mobile.sim.category"
    _description = "فئة شريحة جوال"
    _order = "name"

    name = fields.Char(string="الفئة", required=True)
    company_id = fields.Many2one(
        "res.company", string="الشركة", required=True, default=lambda self: self.env.company
    )
    currency_id = fields.Many2one(related="company_id.currency_id", readonly=True)
    monthly_price = fields.Monetary(
        string="السعر الشهري", currency_field="currency_id", required=True
    )
    description = fields.Text(string="الوصف")
    active = fields.Boolean(string="نشط", default=True)

    _sql_constraints = [
        ("category_company_unique", "unique(name, company_id)", "فئة الشريحة موجودة مسبقًا في الشركة."),
        ("monthly_price_nonnegative", "check(monthly_price >= 0)", "سعر الفئة لا يمكن أن يكون سالبًا."),
    ]


class HrMobileSim(models.Model):
    _name = "hr.mobile.sim"
    _description = "ملف شريحة جوال"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _rec_name = "mobile_number"
    _order = "mobile_number"

    mobile_number = fields.Char(string="رقم الشريحة", required=True, tracking=True)
    serial_number = fields.Char(string="الرقم التسلسلي / ICCID", tracking=True)
    company_id = fields.Many2one(
        "res.company", string="الشركة", required=True, default=lambda self: self.env.company
    )
    category_id = fields.Many2one(
        "hr.mobile.sim.category",
        string="الفئة",
        required=True,
        domain="[('company_id', '=', company_id)]",
        tracking=True,
    )
    currency_id = fields.Many2one(related="company_id.currency_id", readonly=True)
    monthly_price = fields.Monetary(
        string="السعر الشهري",
        related="category_id.monthly_price",
        currency_field="currency_id",
        readonly=True,
        store=True,
    )
    employee_id = fields.Many2one(
        "hr.employee",
        string="حامل الشريحة",
        domain="[('company_id', '=', company_id)]",
        tracking=True,
    )
    carrier = fields.Char(string="شركة الاتصالات")
    activation_date = fields.Date(string="تاريخ التفعيل")
    status = fields.Selection(
        [
            ("available", "متاحة"),
            ("assigned", "مسلمة"),
            ("suspended", "موقوفة"),
            ("lost", "مفقودة"),
            ("closed", "ملغاة"),
        ],
        string="الحالة",
        required=True,
        default="available",
        tracking=True,
    )
    notes = fields.Text(string="ملاحظات")
    active = fields.Boolean(default=True)
    handover_ids = fields.One2many(
        "hr.mobile.sim.handover", "sim_id", string="نماذج الاستلام"
    )
    handover_count = fields.Integer(
        string="عدد نماذج الاستلام", compute="_compute_handover_count"
    )

    _sql_constraints = [
        ("mobile_number_company_unique", "unique(mobile_number, company_id)", "رقم الشريحة موجود مسبقًا في الشركة."),
        ("serial_number_company_unique", "unique(serial_number, company_id)", "الرقم التسلسلي للشريحة موجود مسبقًا في الشركة."),
    ]

    @api.constrains("employee_id", "company_id", "category_id", "status")
    def _check_sim_company(self):
        for sim in self:
            if sim.employee_id and sim.employee_id.company_id != sim.company_id:
                raise ValidationError(_("حامل الشريحة لا يتبع الشركة المحددة."))
            if sim.category_id.company_id != sim.company_id:
                raise ValidationError(_("فئة الشريحة لا تتبع الشركة المحددة."))
            if sim.status == "assigned" and not sim.employee_id:
                raise ValidationError(_("يجب تحديد حامل الشريحة عندما تكون حالتها مسلمة."))

    def _compute_handover_count(self):
        grouped = self.env["hr.mobile.sim.handover"]._read_group(
            [("sim_id", "in", self.ids)], ["sim_id"], ["__count"]
        )
        count_by_sim = {sim.id: count for sim, count in grouped}
        for sim in self:
            sim.handover_count = count_by_sim.get(sim.id, 0)

    def action_open_handovers(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "eljohany_employee_forms.mobile_sim_handover_action"
        )
        action["domain"] = [("sim_id", "=", self.id)]
        action["context"] = {
            "default_sim_id": self.id,
            "default_company_id": self.company_id.id,
        }
        return action


class HrMobileSimHandover(models.Model):
    _name = "hr.mobile.sim.handover"
    _description = "نموذج استلام شريحة إلكترونية"
    _inherit = "hr.additional.form.mixin"
    _order = "handover_date desc, id desc"
    _sequence_code = "hr.mobile.sim.handover"
    _editable_after_approval_fields = {"return_date", "return_notes"}

    employee_id = fields.Many2one(
        "hr.employee",
        string="الموظف المستلم",
        required=True,
        domain="[('company_id', '=', company_id)]",
        tracking=True,
    )
    sim_id = fields.Many2one(
        "hr.mobile.sim",
        string="الشريحة",
        required=True,
        domain="[('company_id', '=', company_id), ('status', 'in', ('available', 'assigned'))]",
        tracking=True,
    )
    handover_date = fields.Date(
        string="تاريخ الاستلام", required=True, default=fields.Date.context_today
    )
    purpose = fields.Char(string="الغرض من الاستلام", required=True)
    acknowledgement = fields.Html(
        string="إقرار المستلم",
        required=True,
        default=(
            "<p>أقر باستلام الشريحة الموضحة بياناتها أعلاه، وأتعهد بالمحافظة "
            "عليها واستخدامها للأغراض المصرح بها، وإبلاغ الشركة فورًا عند فقدها "
            "أو تعطلها، وإعادتها عند الطلب أو عند انتهاء الحاجة إليها.</p>"
        ),
    )
    return_date = fields.Date(string="تاريخ الإعادة")
    return_notes = fields.Text(string="ملاحظات الإعادة")
    state = fields.Selection(selection_add=[("returned", "تمت إعادة الشريحة")], ondelete={"returned": "set default"})

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            employee = self.env["hr.employee"].sudo().browse(vals.get("employee_id"))
            if employee:
                vals.setdefault("company_id", employee.company_id.id)
                vals.setdefault("branch_id", employee.branch_id.id)
        return super().create(vals_list)

    @api.onchange("employee_id")
    def _onchange_employee(self):
        if self.employee_id:
            self.company_id = self.employee_id.company_id
            self.branch_id = self.employee_id.branch_id

    @api.constrains(
        "employee_id", "company_id", "sim_id", "handover_date", "return_date"
    )
    def _check_handover_company(self):
        for record in self:
            if record.employee_id.company_id != record.company_id:
                raise ValidationError(_("يجب أن يتبع الموظف الشركة المحددة."))
            if record.sim_id.company_id != record.company_id:
                raise ValidationError(_("الشريحة لا تتبع الشركة المحددة."))
            if record.return_date and record.return_date < record.handover_date:
                raise ValidationError(_("تاريخ إعادة الشريحة لا يمكن أن يسبق استلامها."))

    def _before_approve(self):
        self._check_handover_company()
        for record in self:
            self.env.cr.execute(
                "SELECT id FROM hr_mobile_sim WHERE id = %s FOR UPDATE",
                [record.sim_id.id],
            )
            conflict = self.search_count(
                [
                    ("id", "!=", record.id),
                    ("sim_id", "=", record.sim_id.id),
                    ("state", "=", "approved"),
                ]
            )
            if conflict or (
                record.sim_id.status == "assigned"
                and record.sim_id.employee_id != record.employee_id
            ):
                raise ValidationError(_("الشريحة مسلمة حاليًا لموظف آخر."))
        return super()._before_approve()

    def _after_approve(self):
        for record in self:
            record.sim_id.write(
                {"employee_id": record.employee_id.id, "status": "assigned"}
            )
        return super()._after_approve()

    def action_mark_returned(self):
        self._check_manager()
        for record in self:
            if record.state != "approved":
                raise UserError(_("يمكن تسجيل الإعادة للنماذج المعتمدة فقط."))
            if not record.return_date:
                raise ValidationError(_("أدخل تاريخ إعادة الشريحة."))
            self.env.cr.execute(
                "SELECT id FROM hr_mobile_sim WHERE id = %s FOR UPDATE",
                [record.sim_id.id],
            )
            record.sim_id.invalidate_recordset(["employee_id", "status"])
            if (
                record.sim_id.status != "assigned"
                or record.sim_id.employee_id != record.employee_id
            ):
                raise ValidationError(
                    _("تعذر تسجيل الإعادة لأن حامل الشريحة الحالي لا يطابق النموذج.")
                )
            record.sim_id.write({"employee_id": False, "status": "available"})
            record.with_context(employee_forms_workflow=True).write(
                {"state": "returned"}
            )

    def action_print(self):
        self._ensure_printable(allow_returned=True)
        return self.env.ref(
            "eljohany_employee_forms.action_report_sim_handover"
        ).report_action(self)


class HrEmployeeInformationReport(models.Model):
    _name = "hr.employee.information.report"
    _description = "تقرير معلومات موظف"
    _inherit = "hr.additional.form.mixin"
    _order = "document_date desc, id desc"
    _sequence_code = "hr.employee.information.report"

    employee_id = fields.Many2one(
        "hr.employee",
        string="الموظف",
        required=True,
        domain="[('company_id', '=', company_id)]",
        tracking=True,
    )
    employee_name = fields.Char(string="اسم الموظف", readonly=True)
    purpose = fields.Char(string="الغرض من التقرير", required=True)
    department_id = fields.Many2one("hr.department", string="الإدارة", readonly=True)
    job_id = fields.Many2one("hr.job", string="المسمى الوظيفي", readonly=True)
    manager_id = fields.Many2one("hr.employee", string="المدير المباشر", readonly=True)
    manager_name = fields.Char(string="اسم المدير المباشر", readonly=True)
    identification_id = fields.Char(string="رقم الهوية / الإقامة", readonly=True)
    employee_number = fields.Char(string="الرقم الوظيفي", readonly=True)
    nationality = fields.Char(string="الجنسية", readonly=True)
    hire_date = fields.Date(string="تاريخ الالتحاق", readonly=True)
    work_email = fields.Char(string="البريد الوظيفي", readonly=True)
    work_phone = fields.Char(string="هاتف العمل", readonly=True)
    private_phone = fields.Char(string="رقم الجوال الشخصي", readonly=True)
    notes = fields.Text(string="ملاحظات التقرير")

    @api.model
    def _employee_snapshot(self, employee):
        employee = employee.sudo()
        hire_date = False
        if "first_contract_date" in employee._fields:
            hire_date = employee.first_contract_date
        return {
            "employee_name": employee.name,
            "company_id": employee.company_id.id,
            "branch_id": employee.branch_id.id,
            "department_id": employee.department_id.id,
            "job_id": employee.job_id.id,
            "manager_id": employee.parent_id.id,
            "manager_name": employee.parent_id.name,
            "identification_id": employee.identification_id,
            "employee_number": _employee_number(employee),
            "nationality": employee.country_id.name,
            "hire_date": hire_date,
            "work_email": employee.work_email,
            "work_phone": employee.work_phone,
            "private_phone": employee.private_phone,
        }

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            employee = self.env["hr.employee"].sudo().browse(vals.get("employee_id"))
            if employee:
                for key, value in self._employee_snapshot(employee).items():
                    vals.setdefault(key, value)
        return super().create(vals_list)

    @api.onchange("employee_id")
    def _onchange_employee(self):
        if self.employee_id:
            self.update(self._employee_snapshot(self.employee_id))

    @api.constrains("employee_id", "company_id")
    def _check_employee_company(self):
        for report in self:
            if report.employee_id.company_id != report.company_id:
                raise ValidationError(_("يجب أن يتبع الموظف الشركة المحددة."))

    def _get_employee_related_information(self):
        """Return company-scoped employee records for the printed report."""
        self.ensure_one()
        self._check_manager()
        employee_id = self.employee_id.id
        company_id = self.company_id.id
        domain = [("employee_id", "=", employee_id), ("company_id", "=", company_id)]
        return {
            "custodies": self.env["hr.custody"].sudo().search(
                domain, order="received_date desc, id desc"
            ),
            "loans": self.env["hr.loan"].sudo().search(
                domain, order="date desc, id desc"
            ),
            "assignments": self.env["hr.overtime.assignment"].sudo().search(
                domain, order="start_datetime desc, id desc"
            ),
            "sim_handovers": self.env["hr.mobile.sim.handover"].sudo().search(
                domain, order="handover_date desc, id desc"
            ),
            "vehicle_handovers": self.env["hr.vehicle.handover"].sudo().search(
                domain, order="handover_date desc, id desc"
            ),
            "warnings": self.env["hr.employee.warning"].sudo().search(
                domain, order="warning_date desc, id desc"
            ),
        }

    def action_print(self):
        self._check_manager()
        for record in self:
            record.with_context(employee_forms_workflow=True).write(
                record._employee_snapshot(record.employee_id)
            )
        return self.env.ref(
            "eljohany_employee_forms.action_report_employee_information"
        ).report_action(self)


class HrEmployeeWarning(models.Model):
    _name = "hr.employee.warning"
    _description = "نموذج إنذار موظف"
    _inherit = "hr.additional.form.mixin"
    _order = "warning_date desc, id desc"
    _sequence_code = "hr.employee.warning"
    _editable_after_approval_fields = {"employee_response", "delivery_date"}

    employee_id = fields.Many2one(
        "hr.employee",
        string="الموظف",
        required=True,
        domain="[('company_id', '=', company_id)]",
        tracking=True,
    )
    warning_date = fields.Date(
        string="تاريخ الإنذار", required=True, default=fields.Date.context_today
    )
    warning_level = fields.Selection(
        [("first", "إنذار أول"), ("second", "إنذار ثانٍ"), ("final", "إنذار نهائي")],
        string="درجة الإنذار",
        required=True,
        default="first",
        tracking=True,
    )
    identification_id = fields.Char(string="رقم الهوية / الإقامة", readonly=True)
    job_id = fields.Many2one("hr.job", string="المسمى الوظيفي", readonly=True)
    department_id = fields.Many2one("hr.department", string="الإدارة", readonly=True)
    violation_date = fields.Date(string="تاريخ المخالفة", required=True)
    subject = fields.Char(string="موضوع الإنذار", required=True, tracking=True)
    details = fields.Text(string="تفاصيل المخالفة", required=True, tracking=True)
    penalty_type = fields.Selection(
        [
            ("notice", "لفت نظر"),
            ("deduction", "حسم"),
            ("suspension", "إيقاف"),
            ("termination", "إنهاء خدمة"),
            ("other", "جزاء آخر"),
        ],
        string="نوع الجزاء",
        required=True,
        default="notice",
        tracking=True,
    )
    penalty_description = fields.Text(string="الجزاء المحدد", required=True, tracking=True)
    employee_response = fields.Text(string="رد الموظف")
    response_deadline = fields.Date(string="آخر موعد للرد")
    delivery_date = fields.Date(string="تاريخ تسليم الإنذار")

    @api.model
    def _warning_employee_values(self, employee):
        employee = employee.sudo()
        return {
            "company_id": employee.company_id.id,
            "branch_id": employee.branch_id.id,
            "identification_id": employee.identification_id,
            "job_id": employee.job_id.id,
            "department_id": employee.department_id.id,
        }

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            employee = self.env["hr.employee"].sudo().browse(vals.get("employee_id"))
            if employee:
                for key, value in self._warning_employee_values(employee).items():
                    vals.setdefault(key, value)
        return super().create(vals_list)

    @api.onchange("employee_id")
    def _onchange_employee(self):
        if self.employee_id:
            self.update(self._warning_employee_values(self.employee_id))

    @api.constrains(
        "employee_id",
        "company_id",
        "warning_date",
        "violation_date",
        "response_deadline",
        "delivery_date",
    )
    def _check_warning_values(self):
        for record in self:
            if record.employee_id.company_id != record.company_id:
                raise ValidationError(_("يجب أن يتبع الموظف الشركة المحددة."))
            if record.violation_date > record.warning_date:
                raise ValidationError(_("تاريخ المخالفة لا يمكن أن يلي تاريخ الإنذار."))
            if (
                record.response_deadline
                and record.response_deadline < record.warning_date
            ):
                raise ValidationError(_("آخر موعد للرد لا يمكن أن يسبق تاريخ الإنذار."))
            if record.delivery_date and record.delivery_date < record.warning_date:
                raise ValidationError(_("تاريخ التسليم لا يمكن أن يسبق تاريخ الإنذار."))

    def _before_approve(self):
        for record in self:
            record.with_context(employee_forms_workflow=True).write(
                record._warning_employee_values(record.employee_id)
            )
        return super()._before_approve()

    def action_print(self):
        self._ensure_printable()
        return self.env.ref(
            "eljohany_employee_forms.action_report_employee_warning"
        ).report_action(self)
