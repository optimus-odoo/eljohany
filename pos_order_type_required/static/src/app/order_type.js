/** @odoo-module */

import { Component } from "@odoo/owl";
import { Order, Orderline } from "@point_of_sale/app/store/models";
import { PosStore } from "@point_of_sale/app/store/pos_store";
import { usePos } from "@point_of_sale/app/store/pos_hook";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import { TicketScreen } from "@point_of_sale/app/screens/ticket_screen/ticket_screen";
import { SelectionPopup } from "@point_of_sale/app/utils/input_popups/selection_popup";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";

const ORDER_TYPES = {
    dine_in: () => _t("محلي"),
    takeaway: () => _t("سفري"),
};

function getOrderTypeLabel(orderType) {
    return ORDER_TYPES[orderType]?.() || _t("نوع الطلب");
}

function getOrderTypeEnglishLabel(orderType) {
    if (orderType === "dine_in") {
        return "Dine In";
    }
    return orderType === "takeaway" ? "Take Away" : "";
}

function getOrderNumber(order) {
    if (order.trackingNumber) {
        return order.trackingNumber;
    }
    const sequenceNumber = Number(order.sequence_number);
    return Number.isFinite(sequenceNumber) ? String(sequenceNumber).padStart(3, "0") : "";
}

function getReceiptProductNames(orderline, fallbackName = "") {
    const product = orderline.get_product?.() || orderline.product;
    const arabicName = String(
        orderline.receipt_name_ar || product?.receipt_name_ar || fallbackName || ""
    ).trim();
    const englishName = String(
        orderline.receipt_name_en || product?.receipt_name_en || fallbackName || ""
    ).trim();
    return {
        receiptNameAr: arabicName,
        receiptNameEn: englishName && englishName !== arabicName ? englishName : "",
    };
}

async function askForOrderType(order, popup) {
    const { confirmed, payload } = await popup.add(SelectionPopup, {
        title: _t("اختر نوع الطلب"),
        body: _t("اختر محلي أو سفري قبل الانتقال إلى الدفع."),
        list: Object.entries(ORDER_TYPES).map(([value, label], index) => ({
            id: index,
            label: label(),
            item: value,
            isSelected: order.get_order_type() === value,
        })),
    });
    if (confirmed && payload) {
        order.set_order_type(payload);
        return true;
    }
    return false;
}

patch(Orderline.prototype, {
    init_from_JSON(json) {
        super.init_from_JSON(...arguments);
        this.receipt_name_ar =
            json.receipt_name_ar || this.product?.receipt_name_ar || false;
        this.receipt_name_en =
            json.receipt_name_en || this.product?.receipt_name_en || false;
    },

    export_as_JSON() {
        const json = super.export_as_JSON(...arguments);
        const names = getReceiptProductNames(this, this.get_full_product_name());
        json.receipt_name_ar = names.receiptNameAr || false;
        json.receipt_name_en = names.receiptNameEn || names.receiptNameAr || false;
        return json;
    },
});

patch(Order.prototype, {
    init_from_JSON(json) {
        super.init_from_JSON(...arguments);
        this.order_type = json.order_type || false;
        this.receipt_number = json.receipt_number || false;
        this.pos_config_name = json.pos_config_name || false;
        this.pos_session_name = json.pos_session_name || false;
    },

    export_as_JSON() {
        const json = super.export_as_JSON(...arguments);
        json.order_type = this.get_order_type();
        json.receipt_number = this.receipt_number || false;
        json.pos_config_name = this.pos_config_name || this.pos.config?.name || false;
        json.pos_session_name = this.pos_session_name || this.pos.pos_session?.name || false;
        return json;
    },

    export_for_printing() {
        const receipt = super.export_for_printing(...arguments);
        receipt.orderlines = receipt.orderlines.map((line, index) => ({
            ...line,
            ...getReceiptProductNames(this.orderlines[index], line.productName),
        }));
        receipt.order_type = this.get_order_type();
        receipt.order_type_label = getOrderTypeLabel(this.get_order_type());
        receipt.order_type_english_label = getOrderTypeEnglishLabel(this.get_order_type());
        receipt.receipt_number = this.receipt_number || receipt.name;
        receipt.order_number = getOrderNumber(this);
        receipt.pos_config_name = this.pos_config_name || this.pos.config?.name || "";
        receipt.pos_session_name = this.pos_session_name || this.pos.pos_session?.name || "";
        return receipt;
    },

    get_order_type() {
        return this.order_type || false;
    },

    set_order_type(orderType) {
        this.assert_editable();
        if (!(orderType in ORDER_TYPES)) {
            return;
        }
        this.order_type = orderType;
        this.save_to_db();
    },

    async pay() {
        if (this.canPay() && !this.get_order_type()) {
            const selected = await askForOrderType(this, this.env.services.popup);
            if (!selected) {
                return;
            }
        }
        return super.pay(...arguments);
    },
});

patch(PosStore.prototype, {
    _updateOrder(ordersResponseData, orders) {
        const order = super._updateOrder(...arguments);
        if (order && ordersResponseData.receipt_number) {
            order.receipt_number = ordersResponseData.receipt_number;
        }
        return order;
    },
});

patch(TicketScreen.prototype, {
    shouldHideDeleteButton(order) {
        if (order && !order.locked) {
            return true;
        }
        return super.shouldHideDeleteButton(...arguments);
    },
});

export class OrderTypeButton extends Component {
    static template = "pos_order_type_required.OrderTypeButton";

    setup() {
        this.pos = usePos();
        this.popup = useService("popup");
    }

    get label() {
        return getOrderTypeLabel(this.pos.get_order()?.get_order_type());
    }

    get isSelected() {
        return Boolean(this.pos.get_order()?.get_order_type());
    }

    async onClick() {
        const order = this.pos.get_order();
        if (order) {
            await askForOrderType(order, this.popup);
        }
    }
}

ProductScreen.addControlButton({
    component: OrderTypeButton,
});
