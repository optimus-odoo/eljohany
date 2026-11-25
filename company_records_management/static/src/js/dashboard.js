/** @odoo-module **/
import { registry } from "@web/core/registry";
import { Component, onWillStart, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { FormViewDialog } from "@web/views/view_dialogs/form_view_dialog";

const SECTIONS = [
    {id: "branches", label: "الفروع", model: "crm.company.branch", owner: "company_id", columns: [["name", "الفرع"], ["code", "الكود"], ["city", "المدينة"], ["manager", "المسؤول"]]},
    {id: "partners", label: "الشركاء", model: "crm.company.partner", owner: "company_id", columns: [["name", "الاسم"], ["ownership_percent", "نسبة الملكية %"], ["mobile", "الجوال"], ["email", "البريد الإلكتروني"]]},
    {id: "registrations", label: "السجلات التجارية", model: "crm.commercial.registration", owner: "company_id", columns: [["name", "رقم السجل"], ["expiration_date", "تاريخ الانتهاء"], ["status", "الحالة"], ["days_remaining", "الأيام المتبقية"]]},
    {id: "municipality", label: "الرخص البلدية", model: "crm.municipality.license", owner: "branch_id.company_id", branch: true, columns: [["name", "رقم الرخصة"], ["branch_id", "الفرع"], ["expiration_date", "تاريخ الانتهاء"], ["status", "الحالة"], ["days_remaining", "الأيام المتبقية"]]},
    {id: "civil", label: "الدفاع المدني", model: "crm.civil.defense.license", owner: "branch_id.company_id", branch: true, columns: [["name", "رقم الرخصة"], ["branch_id", "الفرع"], ["expiration_date", "تاريخ الانتهاء"], ["status", "الحالة"], ["days_remaining", "الأيام المتبقية"]]},
    {id: "addresses", label: "العناوين الوطنية", model: "crm.national.address", owner: "branch_id.company_id", branch: true, columns: [["name", "الاسم"], ["branch_id", "الفرع"], ["short_address", "العنوان المختصر"], ["city", "المدينة"]]},
    {id: "electricity", label: "الكهرباء", model: "crm.electricity.meter", owner: "branch_id.company_id", branch: true, columns: [["name", "رقم الحساب"], ["branch_id", "الفرع"], ["monthly_payment_day", "يوم السداد"], ["state", "الحالة"]]},
    {id: "banks", label: "الحسابات البنكية", model: "crm.branch.bank.account", owner: "branch_id.company_id", branch: true, columns: [["name", "اسم الحساب"], ["branch_id", "الفرع"], ["bank_name", "البنك"], ["iban", "IBAN"]]},
    {id: "leases", label: "عقود الإيجار", model: "crm.lease.contract", owner: "company_id", branch: true, columns: [["name", "رقم العقد"], ["branch_id", "الفرع"], ["date_end", "تاريخ الانتهاء"], ["state", "الحالة"], ["days_remaining", "الأيام المتبقية"]]},
];
const STATUS_LABELS = {valid: "ساري", active: "ساري", soon: "قريب الانتهاء", expired: "منتهي", draft: "مسودة", suspended: "معلق", cancelled: "ملغى", inactive: "غير نشط", closed: "مغلق"};
const PAGE_SIZE = 40;

export class RecordsDashboard extends Component {
    setup() {
        this.orm = useService("orm");
        this.dialog = useService("dialog");
        this.action = useService("action");
        this.notification = useService("notification");
        this.user = useService("user");
        this.sections = SECTIONS;
        this.requestId = 0;
        this.state = useState({
            companies: [], branches: [], companyId: false, branchId: false,
            tab: "overview", rows: [], summary: [], alerts: [], loading: true, error: false,
            search: "", offset: 0, hasMore: false, canAudit: false, canManage: false,
            testingNotification: false, sendingCurrentNotifications: false,
        });
        onWillStart(async () => {
            this.state.canAudit = await this.user.hasGroup("company_records_management.group_records_manager") ||
                await this.user.hasGroup("company_records_management.group_records_auditor");
            this.state.canManage = await this.user.hasGroup("company_records_management.group_records_manager");
            await this.refreshCompanies();
        });
    }

    get section() { return SECTIONS.find((item) => item.id === this.state.tab); }
    get needsBranch() { return this.section?.branch && !this.state.branchId; }
    get companyName() { return this.state.companies.find((c) => c.id === this.state.companyId)?.name || ""; }

    async refreshCompanies(preferredId) {
        try {
            this.state.companies = await this.orm.searchRead("crm.company.record", [], ["name"], {order: "name"});
            const wanted = preferredId || this.state.companyId;
            this.state.companyId = this.state.companies.some((c) => c.id === wanted) ? wanted : this.state.companies[0]?.id || false;
            await this.refreshBranches();
        } catch (error) { this.showError(error); }
    }

    async refreshBranches() {
        this.state.branches = this.state.companyId ? await this.orm.searchRead("crm.company.branch", [["company_id", "=", this.state.companyId]], ["name"], {order: "name"}) : [];
        if (!this.state.branches.some((b) => b.id === this.state.branchId)) this.state.branchId = false;
        await this.loadContent();
    }

    async changeCompany(event) {
        this.state.companyId = Number(event.target.value) || false;
        this.state.branchId = false;
        this.state.offset = 0;
        this.state.search = "";
        this.state.loading = true;
        try { await this.refreshBranches(); } catch (error) { this.showError(error); }
    }

    async changeBranch(event) {
        this.state.branchId = Number(event.target.value) || false;
        this.state.offset = 0;
        await this.loadContent();
    }

    async selectTab(id) {
        this.state.tab = id;
        this.state.offset = 0;
        this.state.search = "";
        await this.loadContent();
    }

    domain() {
        const section = this.section;
        const domain = [[section.owner, "=", this.state.companyId]];
        if (this.state.branchId) {
            if (section.branch) domain.push(["branch_id", "=", this.state.branchId]);
            if (section.id === "registrations") domain.push(["branch_ids", "in", [this.state.branchId]]);
            if (section.id === "branches") domain.push(["id", "=", this.state.branchId]);
        }
        if (this.state.search.trim()) domain.push(["name", "ilike", this.state.search.trim()]);
        return domain;
    }

    async loadContent() {
        const requestId = ++this.requestId;
        this.state.loading = true;
        this.state.error = false;
        this.state.rows = [];
        try {
            if (!this.state.companyId) { this.state.summary = []; return; }
            if (this.state.tab === "overview") {
                const [summary, alerts] = await Promise.all([
                    this.orm.call("crm.dashboard", "get_data", [], {company_id: this.state.companyId, branch_id: this.state.branchId}),
                    this.orm.call("crm.dashboard", "get_expiry_alerts", [], {company_id: this.state.companyId, branch_id: this.state.branchId}),
                ]);
                if (requestId === this.requestId) {
                    this.state.summary = summary;
                    this.state.alerts = alerts;
                }
            } else {
                const rows = await this.orm.searchRead(this.section.model, this.domain(), this.section.columns.map(([name]) => name), {offset: this.state.offset, limit: PAGE_SIZE + 1, order: "id desc"});
                if (requestId === this.requestId) {
                    this.state.hasMore = rows.length > PAGE_SIZE;
                    this.state.rows = rows.slice(0, PAGE_SIZE);
                }
            }
        } catch (error) {
            if (requestId === this.requestId) this.showError(error);
        } finally {
            if (requestId === this.requestId) this.state.loading = false;
        }
    }

    showError(error) {
        this.state.loading = false;
        this.state.error = true;
        this.notification.add("تعذر تحميل البيانات. حاول التحديث مرة أخرى.", {type: "danger"});
        console.error(error);
    }

    async search(event) { event.preventDefault(); this.state.offset = 0; await this.loadContent(); }
    async page(direction) { this.state.offset = Math.max(0, this.state.offset + direction * PAGE_SIZE); await this.loadContent(); }

    cell(row, field) {
        const value = row[field];
        if (Array.isArray(value)) return value[1];
        if (field === "status" || field === "state") return STATUS_LABELS[value] || value || "—";
        return value === false || value === null || value === "" ? "—" : value;
    }

    openForm(model, resId = false, title = "", context = {}) {
        this.dialog.add(FormViewDialog, {
            resModel: model, resId, title, context,
            onRecordSaved: async (record) => {
                if (model === "crm.company.record") await this.refreshCompanies(record.resId);
                else if (model === "crm.company.branch") await this.refreshBranches();
                else await this.loadContent();
            },
        }, {onClose: () => this.refreshCompanies()});
    }

    addCompany() { this.openForm("crm.company.record", false, "إضافة شركة"); }
    editCompany() { this.openForm("crm.company.record", this.state.companyId, "بيانات الشركة والشركاء"); }
    addBranch() { this.openForm("crm.company.branch", false, "إضافة فرع", {default_company_id: this.state.companyId}); }
    editBranch() { this.openForm("crm.company.branch", this.state.branchId, "بيانات الفرع"); }
    openRecord(row) { this.openForm(this.section.model, row.id, this.section.label); }
    openAlert(alert) { this.openForm(alert.model, alert.record_id, alert.record_type); }
    alertStatus(alert) {
        if (alert.days_remaining < 0) return `منتهي منذ ${Math.abs(alert.days_remaining)} يوم`;
        if (alert.days_remaining === 0) return "ينتهي اليوم";
        return `متبقي ${alert.days_remaining} يوم`;
    }
    addRecord() {
        if (!this.state.companyId || this.needsBranch) return;
        const context = {default_company_id: this.state.companyId};
        if (this.state.branchId) {
            context.default_branch_id = this.state.branchId;
            if (this.section.id === "registrations") context.default_branch_ids = [[6, 0, [this.state.branchId]]];
        }
        this.openForm(this.section.model, false, `إضافة — ${this.section.label}`, context);
    }

    async exportExcel() {
        const action = await this.orm.call("crm.records.xlsx.wizard", "action_export", [[]], {
            context: {records_company_id: this.state.companyId, records_branch_id: this.state.branchId},
        });
        await this.action.doAction(action);
    }
    async printCompany() {
        await this.action.doAction("company_records_management.action_records_pdf", {
            additionalContext: {active_ids: [this.state.companyId], active_id: this.state.companyId, active_model: "crm.company.record"},
        });
    }
    async testNotification() {
        if (!this.state.companyId || this.state.testingNotification) return;
        this.state.testingNotification = true;
        try {
            const result = await this.orm.call("crm.expiry.service", "action_send_test_notification", [], {
                company_id: this.state.companyId,
                branch_id: this.state.branchId,
            });
            this.notification.add(result.message, {
                title: result.success ? "تم اختبار الإشعار" : "تعذر اختبار الإشعار",
                type: result.success ? "success" : "warning",
                sticky: true,
            });
        } catch (error) {
            this.notification.add("تعذر إرسال الإشعار الاختباري. راجع صلاحيات المستخدم ثم حاول مرة أخرى.", {
                title: "تعذر اختبار الإشعار",
                type: "danger",
                sticky: true,
            });
            console.error(error);
        } finally {
            this.state.testingNotification = false;
        }
    }
    async sendCurrentNotifications() {
        if (!this.state.companyId || this.state.sendingCurrentNotifications) return;
        this.state.sendingCurrentNotifications = true;
        try {
            const result = await this.orm.call("crm.expiry.service", "action_send_current_expiry_notifications", [], {
                company_id: this.state.companyId,
                branch_id: this.state.branchId,
            });
            const recipients = result.recipients.length ? ` المستلمون: ${result.recipients.join("، ")}.` : "";
            this.notification.add(result.message + recipients, {
                title: "تنبيهات السجلات الحالية",
                type: "success",
                sticky: true,
            });
        } catch (error) {
            this.notification.add("تعذر إرسال تنبيهات السجلات الحالية.", {
                title: "خطأ في إرسال التنبيهات",
                type: "danger",
                sticky: true,
            });
            console.error(error);
        } finally {
            this.state.sendingCurrentNotifications = false;
        }
    }
    async openAudit() {
        await this.action.doAction({type: "ir.actions.act_window", name: "سجل التدقيق", res_model: "crm.audit.log", views: [[false, "list"]], target: "new"});
    }
}
RecordsDashboard.template = "company_records_management.RecordsDashboard";
registry.category("actions").add("crm_records_dashboard", RecordsDashboard);
