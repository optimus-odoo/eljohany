/** @odoo-module */

import { ClosePosPopup } from "@point_of_sale/app/navbar/closing_popup/closing_popup";
import { ErrorPopup } from "@point_of_sale/app/errors/popups/error_popup";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";

const SHIFT_REPORT_ACTION =
    "pos_shift_summary_report.action_pos_session_shift_summary_report_pdf";

patch(ClosePosPopup.prototype, {
    async downloadShiftReport() {
        if (this.shiftReportDownloading) {
            return;
        }
        this.shiftReportDownloading = true;
        try {
            await this.report.doAction(SHIFT_REPORT_ACTION, [this.pos.pos_session.id]);
        } catch (error) {
            await this.popup.add(ErrorPopup, {
                title: _t("Shift report download failed"),
                body: _t(
                    "The shift report could not be downloaded. The POS session was not changed."
                ),
            });
        } finally {
            this.shiftReportDownloading = false;
        }
    },
});
