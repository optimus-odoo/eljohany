/** @odoo-module */

import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";

import { AccountReportFilters } from "@account_reports/components/account_report/filters/filters";

const MAX_SAFE_EXPANSIONS = 5000;

patch(AccountReportFilters.prototype, {
    async toggleFilter(optionKey) {
        if (
            optionKey !== "unfold_all" ||
            !this.controller.options.branch_gl_safe_unfold
        ) {
            return super.toggleFilter(...arguments);
        }

        // Never persist Odoo's native unfold_all=True for this report. A later
        // refresh/export would otherwise fall back to the single unbounded RPC.
        this.controller.options.unfold_all = false;
        this.controller.saveSessionOptions(this.controller.options);

        if (this.branchSafeUnfoldRunning) {
            return;
        }

        this.branchSafeUnfoldRunning = true;
        // Keep the progress notice visible even after the operation finishes.
        // Only the user may dismiss it, so a long-running report never loses
        // the message that explains what is happening.
        this.env.services.notification.add(
            _t("يرجى الانتظار قليلًا، جارٍ تجهيز دفتر الأستاذ العام وفتحه على دفعات آمنة. لن يستغرق الأمر طويلًا، وسيظهر إشعار فور اكتمال العملية."),
            { type: "info", sticky: true }
        );

        let expansionCount = 0;
        try {
            // Expanding a hierarchy line can reveal more foldable children, so
            // keep scanning the live array until no folded line remains. Each
            // call uses Odoo's normal per-account pagination (and consequently
            // leaves a native "Load more" row for the remaining journal items).
            for (let lineIndex = 0; lineIndex < this.controller.lines.length; lineIndex++) {
                const line = this.controller.lines[lineIndex];
                if (
                    !line.unfoldable ||
                    line.unfolded ||
                    line.id.includes("|load_more~~")
                ) {
                    continue;
                }

                if (expansionCount >= MAX_SAFE_EXPANSIONS) {
                    throw new Error("General Ledger safe expansion limit reached");
                }

                await this.controller.unfoldLine(lineIndex);
                expansionCount += 1;
            }

            this.env.services.notification.add(
                _t("اكتمل تجهيز دفتر الأستاذ العام بنجاح. يمكنك الآن مراجعة الحسابات، واستخدام «تحميل المزيد» للحسابات الكبيرة."),
                { type: "success", sticky: true }
            );
        } catch (error) {
            this.env.services.notification.add(
                _t("تعذر إكمال تجهيز دفتر الأستاذ العام حاليًا. البيانات المحمّلة ما زالت متاحة، ويمكن إعادة المحاولة للمتابعة."),
                { type: "warning", sticky: true }
            );
            throw error;
        } finally {
            this.branchSafeUnfoldRunning = false;
            this.controller.options.unfold_all = false;
            this.controller.saveSessionOptions(this.controller.options);
        }
    },
});
