/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onWillStart, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class CreditDashboard extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");

        this.openPartner = this.openPartner.bind(this);
        this.openExceeded = this.openExceeded.bind(this);
        this.openOverdue = this.openOverdue.bind(this);
        this.reload = this.reload.bind(this);
        this.cleanupLegacy = this.cleanupLegacy.bind(this);

        this.state = useState({
            loading: true,
            currency: { name: "", symbol: "" },
            kpis: { total_customers: 0, overdue: 0, exceeded: 0, both: 0 },
            buckets: {},
            top: [],
        });

        onWillStart(async () => {
            await this.load();
        });
    }

    get bucketList() {
        const b = this.state.buckets || {};
        const order = ["0-49", "50-79", "80-99", "100+", "No Limit"];
        return order.map((k) => ({ label: k, value: b[k] || 0 }));
    }

    fmtMoney(v) {
        const sym = this.state.currency?.symbol || "";
        return `${sym} ${Number(v || 0).toLocaleString()}`;
    }

    async load() {
        this.state.loading = true;
        const data = await this.orm.call("res.partner", "get_credit_dashboard_data", []);
        this.state.currency = data.currency;
        this.state.kpis = data.kpis;
        this.state.buckets = data.buckets;
        this.state.top = data.top;
        this.state.loading = false;
    }

    async reload() {
        await this.load();
    }

    openPartner(partnerId) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "res.partner",
            res_id: partnerId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    async openExceeded() {
        const act = await this.orm.call("res.partner", "action_open_exceeded_customers", []);
        this.action.doAction(act);
    }

    async openOverdue() {
        const act = await this.orm.call("res.partner", "action_open_overdue_customers", []);
        this.action.doAction(act);
    }


    async cleanupLegacy() {
        await this.orm.call("res.partner", "cleanup_legacy_credit_filters", []);
        this.notification.add("تم تنظيف الفلاتر/الإجراءات القديمة بنجاح.", { type: "success" });
    }

}

CreditDashboard.template = "customer_credit_control.CreditDashboard";

registry.category("actions").add("customer_credit_dashboard", CreditDashboard);
