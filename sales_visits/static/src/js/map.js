/** @odoo-module **/

import { onWillStart } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { jsonrpc } from "@web/core/network/rpc_service";
import { session } from "@web/session";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";
import { registry } from "@web/core/registry";
import { useDebounced } from "@web/core/utils/timing";
import { ActivityMenu } from "@hr_attendance/components/attendance_menu/attendance_menu";

import { MapRenderer } from "@web_map/map_view/map_renderer";
//rom "@hr_attendance/components/attendance_menu/attendance_menu";


patch(MapRenderer.prototype, {
    setup() {
        super.setup();
        this.action = useService("action");
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.dialogService = useService("dialog");
        console.log("Model Name:", this.props.model.metaData.resModel);
    },

    async _getActiveVisit(contactId) {
        return this.orm.searchRead("visit.visit", [
            ["partner_id", "=", contactId],
            ["end_date", "=", false],
        ], ["id"]);
    },

    async _checkIn(markerInfo) {
        const partner = markerInfo.record.partner;
        const now = new Date().toISOString().slice(0, 19).replace('T', ' '); // "YYYY-MM-DD HH:MM:SS"

        // Get current user's geolocation
        navigator.geolocation.getCurrentPosition(async (position) => {
            const userLatitude = position.coords.latitude;
            const userLongitude = position.coords.longitude;
            var loc = "http://www.google.com/maps/place/" + userLatitude + "," + userLongitude;

            // Create the visit record with user's location
            await this.orm.create("visit.visit", [{
                partner_id: markerInfo.record.id,
                start_date: now,
                in_latitude: userLatitude,
                in_longitude: userLongitude,
                in_url: loc,
                state: "open",
                salesperson_id: session.user_id[0],
            }]);

            this.notification.add(_t("Checked in successfully."), { type: "success" });
            }, (error) => {
                console.error("Geolocation error:", error);
                this.notification.add(_t("Unable to retrieve location. Please enable location services."), { type: "warning" });
        });
    },

    async _checkOut(visitId,markerInfo) {
        const now = new Date().toISOString().slice(0, 19).replace('T', ' '); // "YYYY-MM-DD HH:MM:SS"
        // Get current user's geolocation
        navigator.geolocation.getCurrentPosition(async (position) => {
            const userLatitude = position.coords.latitude;
            const userLongitude = position.coords.longitude;
            var loc = "http://www.google.com/maps/place/" + userLatitude + "," + userLongitude;

            // Create the visit record with user's location
            await this.orm.write("visit.visit",[visitId], {
                end_date: now,
                out_latitude: userLatitude,
                out_longitude: userLongitude,
                out_url: loc,
                state: "close",
            });
            console.log('checked out');

            this.notification.add(_t("Checked out successfully."), { type: "success" });
            }, (error) => {
                console.error("Geolocation error:", error);
                this.notification.add(_t("Unable to retrieve location. Please enable location services."), { type: "warning" });
        });
    },

    showErrorPopup() {
        const title = "Error"; // Title of the popup
        const message = "Can't open 2 visits for the same client at the same time!"; // Error message
        this.dialogService.add(WarningDialog, {
                    title: _t("Warning"),
                    message: _t("Can't open 2 visits for the same client at the same time!"),
        });

    },


    createMarkerPopup(markerInfo, latLongOffset = 0) {
        const popup = super.createMarkerPopup(markerInfo, latLongOffset);
        const popupElement = popup.getElement();

        if (this.props.model.metaData.resModel == 'res.partner' ) {
            let checInBtn = popupElement.querySelector("button.o-map-renderer--popup-buttons-checkin-out");
            if (!checInBtn) {
                checInBtn = document.createElement("button");
                checInBtn.classList.add("btn", "btn-primary", "o-map-renderer--popup-buttons-checkin-out");
                checInBtn.innerText = _t("Check In/Out");
                popupElement.appendChild(checInBtn);
            }



        // Attach the async event handler correctly
            checInBtn.onclick = async () => {
                const visit = await this._getActiveVisit(markerInfo.record.id);
                if (visit.length === 0) {
                    // Perform Check-In
                    await this._checkIn(markerInfo);
                }
                else if(visit.length > 1){
                    this.showErrorPopup();
                }
                else {
                    // Perform Check-Out
                    await this._checkOut(visit[0].id, markerInfo);
                    console.log('THIS',this);
                    setTimeout(this.action.doAction({
                        type: 'ir.actions.act_window',
                        name: _t('Visits'),
                        target: 'current',
                        res_id: visit[0].id,
                        res_model: 'visit.visit',
                        views: [[false, 'form']],
                    }), 4000);



                }
            };
        }
        else if (this.props.model.metaData.resModel == 'visit.visit' && markerInfo.record.state == 'open') {
            var x = $(popupElement).find('.o-map-renderer--popup-buttons-checkin-out');
            console.log('mmm',x);
            $(popupElement).find('.o-map-renderer--popup-buttons-checkin-out')[0].innerText = 'Check Out';
            let checInBtn = popupElement.querySelector("button.o-map-renderer--popup-buttons-checkin-out");
            if (!checInBtn) {
                checInBtn = document.createElement("button");
                checInBtn.classList.add("btn", "btn-primary", "o-map-renderer--popup-buttons-checkin-out");
                checInBtn.innerText = _t("Check Out");
                popupElement.appendChild(checInBtn);
            }



        // Attach the async event handler correctly
            checInBtn.onclick = async () => {
                const visit = markerInfo.record;
                console.log('VISIT',visit);
                    // Perform Check-Out
                await this._checkOut(visit.id, markerInfo);
                console.log('THIS',this);
//                setTimeout(this.action.doAction({
//                    type: 'ir.actions.act_window',
//                    name: _t('Visits'),
//                    target: 'current',
//                    res_id: visit.id,
//                    res_model: 'visit.visit',
//                    views: [[false, 'form']],
//                }), 5000);




            };
        }
        else{
            $(popupElement).find('.o-map-renderer--popup-buttons-checkin-out').addClass('d-none');

        }
        return popup;
    },

});
