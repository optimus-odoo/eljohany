/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

export class ExecutiveIntelligenceCenter extends Component {
    static template = "eljohany_executive_intelligence_core.Center";

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.defaultTitle = _t("Executive Intelligence Center");
        this.labels = {
            brand: _t("Executive Intelligence"),
            center: _t("Executive Intelligence Center"),
            loadingCenter: _t("Loading intelligence center…"),
            lastUpdate: _t("Last update:"),
            from: _t("From"),
            to: _t("To"),
            companies: _t("Companies"),
            warehouses: _t("Warehouses"),
            apply: _t("Apply"),
            selected: _t("Selected"),
            selectAll: _t("Select all"),
            clear: _t("Clear"),
            noDashboards: _t(
                "No dashboards are assigned to this user. Contact the intelligence center administrator."
            ),
            loadingData: _t("Loading verified data…"),
            completeErrorDetails: _t("Complete error details"),
            technicalTraceback: _t("Technical traceback"),
            retry: _t("Retry"),
            copyError: _t("Copy error"),
            copied: _t("Copied"),
            dashboard: _t("Dashboard:"),
            occurredAt: _t("Occurred at:"),
            errorHelp: _t(
                "The complete error details are displayed below and will remain visible until retry."
            ),
            searchTable: _t("Search in table…"),
            noMatchingRows: _t("No matching rows."),
            rows: _t("rows"),
            chartTypes: {
                line: _t("Line chart"),
                area: _t("Area chart"),
                bar: _t("Bar chart"),
                column: _t("Column chart"),
                gauge: _t("Gauge"),
                progress: _t("Progress"),
                heatmap: _t("Heatmap"),
                geo: _t("Geographic map"),
            },
        };
        this.state = useState({
            loading: true,
            loadingData: false,
            bootstrap: null,
            activeDashboard: null,
            data: null,
            dateFrom: "",
            dateTo: "",
            selectedCompanyIds: [],
            selectedWarehouseIds: [],
            tableQueries: {},
            tableSorts: {},
            error: null,
        });
        onWillStart(() => this.loadBootstrap());
    }

    async loadBootstrap() {
        this.state.loading = true;
        this.state.error = null;
        try {
            const bootstrap = await this.orm.call(
                "executive.intelligence.service",
                "get_bootstrap",
                []
            );
            this.state.bootstrap = bootstrap;
            this.state.dateTo = bootstrap.today;
            const [year, month, day] = bootstrap.today.split("-").map(Number);
            const start = new Date(Date.UTC(year, month - 1, day));
            start.setUTCDate(start.getUTCDate() - 29);
            this.state.dateFrom = start.toISOString().slice(0, 10);
            this.state.selectedCompanyIds = bootstrap.companies.map((company) => company.id);
            this.state.selectedWarehouseIds = (bootstrap.warehouses || []).map(
                (warehouse) => warehouse.id
            );
            if (bootstrap.dashboards.length) {
                await this.selectDashboard(bootstrap.dashboards[0]);
            }
        } catch (error) {
            this.showError(
                error,
                _t("Intelligence center loading error"),
                _t("Unable to load the intelligence center."),
                "bootstrap"
            );
        } finally {
            this.state.loading = false;
        }
    }

    async selectDashboard(dashboard) {
        this.state.activeDashboard = dashboard;
        await this.loadDashboardData();
    }

    async loadDashboardData() {
        if (!this.state.activeDashboard || !this.state.selectedCompanyIds.length) {
            return;
        }
        this.state.loadingData = true;
        this.state.error = null;
        try {
            this.state.data = await this.orm.call(
                "executive.intelligence.service",
                "get_dashboard_data",
                [
                    this.state.activeDashboard.code,
                    {
                        date_from: this.state.dateFrom,
                        date_to: this.state.dateTo,
                        company_ids: this.state.selectedCompanyIds,
                        warehouse_ids: this.state.selectedWarehouseIds,
                    },
                ]
            );
            this.state.tableQueries = {};
            this.state.tableSorts = {};
        } catch (error) {
            this.state.data = null;
            this.showError(
                error,
                _t("Dashboard loading error"),
                _t("Unable to load dashboard data."),
                "dashboard"
            );
        } finally {
            this.state.loadingData = false;
        }
    }

    showError(error, title, fallbackMessage, scope) {
        const data = error?.data || error?.cause?.data || {};
        const causeData = error?.cause?.data || {};
        const message = data.message || causeData.message || error?.message || fallbackMessage;
        const details = [];
        for (const value of [data.debug, causeData.debug, error?.stack, error?.cause?.stack]) {
            if (value && !details.includes(String(value))) {
                details.push(String(value));
            }
        }
        const metadata = {
            name: data.name || causeData.name || error?.name,
            type: data.type || causeData.type || error?.type,
            subType: data.subType || causeData.subType || error?.subType,
            code: error?.code,
            arguments: data.arguments || causeData.arguments,
        };
        const availableMetadata = Object.fromEntries(
            Object.entries(metadata).filter(([, value]) => value !== undefined && value !== null)
        );
        if (Object.keys(availableMetadata).length) {
            try {
                details.push(JSON.stringify(availableMetadata, null, 2));
            } catch {
                // The server traceback above remains the authoritative error detail.
            }
        }
        const dashboardName =
            scope === "dashboard" && this.state.activeDashboard
                ? `${this.state.activeDashboard.name} (${this.state.activeDashboard.code})`
                : "";
        const occurredAt = new Date().toLocaleString();
        const technicalDetails = details.length ? details.join("\n\n") : String(message);
        this.state.error = {
            title,
            message: String(message),
            technicalDetails,
            dashboardName,
            occurredAt,
            scope,
            copied: false,
        };
        this.notification.add(_t("The complete error details are displayed on the dashboard."), {
            title,
            type: "danger",
            sticky: true,
        });
    }

    errorText() {
        const error = this.state.error;
        if (!error) {
            return "";
        }
        return [
            error.title,
            error.dashboardName ? `${this.labels.dashboard} ${error.dashboardName}` : "",
            `${this.labels.occurredAt} ${error.occurredAt}`,
            error.message,
            error.technicalDetails,
        ]
            .filter(Boolean)
            .join("\n\n");
    }

    async copyErrorDetails() {
        const text = this.errorText();
        if (!text) {
            return;
        }
        try {
            if (navigator.clipboard?.writeText) {
                await navigator.clipboard.writeText(text);
            } else {
                const textarea = document.createElement("textarea");
                textarea.value = text;
                textarea.setAttribute("readonly", "");
                textarea.style.position = "fixed";
                textarea.style.opacity = "0";
                document.body.appendChild(textarea);
                textarea.select();
                const copied = document.execCommand("copy");
                textarea.remove();
                if (!copied) {
                    throw new Error("Copy command failed");
                }
            }
            if (this.state.error) {
                this.state.error.copied = true;
            }
        } catch {
            this.notification.add(_t("Unable to copy the error details."), {
                type: "danger",
                sticky: true,
            });
        }
    }

    async retryLastError() {
        const scope = this.state.error?.scope;
        if (scope === "bootstrap") {
            await this.loadBootstrap();
        } else {
            await this.loadDashboardData();
        }
    }

    onCompanyToggle(companyId, ev) {
        const selected = new Set(this.state.selectedCompanyIds);
        if (ev.target.checked) {
            selected.add(companyId);
        } else {
            selected.delete(companyId);
        }
        this.state.selectedCompanyIds = Array.from(selected);
        const selectedWarehouses = new Set(this.state.selectedWarehouseIds);
        for (const warehouse of this.state.bootstrap.warehouses || []) {
            if (!selected.has(warehouse.company_id)) {
                selectedWarehouses.delete(warehouse.id);
            } else if (ev.target.checked && warehouse.company_id === companyId) {
                selectedWarehouses.add(warehouse.id);
            }
        }
        this.state.selectedWarehouseIds = Array.from(selectedWarehouses);
    }

    onWarehouseToggle(warehouseId, ev) {
        const selected = new Set(this.state.selectedWarehouseIds);
        if (ev.target.checked) {
            selected.add(warehouseId);
        } else {
            selected.delete(warehouseId);
        }
        this.state.selectedWarehouseIds = Array.from(selected);
    }

    selectAllCompanies() {
        this.state.selectedCompanyIds = this.state.bootstrap.companies.map(
            (company) => company.id
        );
        this.state.selectedWarehouseIds = (this.state.bootstrap.warehouses || []).map(
            (warehouse) => warehouse.id
        );
    }

    clearCompanies() {
        this.state.selectedCompanyIds = [];
        this.state.selectedWarehouseIds = [];
    }

    selectAllWarehouses() {
        const selectedCompanies = new Set(this.state.selectedCompanyIds);
        this.state.selectedWarehouseIds = (this.state.bootstrap.warehouses || [])
            .filter((warehouse) => selectedCompanies.has(warehouse.company_id))
            .map((warehouse) => warehouse.id);
    }

    clearWarehouses() {
        this.state.selectedWarehouseIds = [];
    }

    toNumber(value) {
        const number = Number(value);
        return Number.isFinite(number) ? number : 0;
    }

    chartValues(chart) {
        return (chart.items || []).map((item) => this.toNumber(item.value));
    }

    chartRange(chart) {
        const values = this.chartValues(chart);
        const minimum = Math.min(0, ...values);
        const maximum = Math.max(0, ...values);
        return { minimum, maximum, span: Math.max(maximum - minimum, 1) };
    }

    chartPointX(chart, index) {
        const count = (chart.items || []).length;
        return count <= 1 ? 50 : 4 + (index * 92) / (count - 1);
    }

    chartPointY(chart, item) {
        const range = this.chartRange(chart);
        return 92 - ((this.toNumber(item.value) - range.minimum) / range.span) * 82;
    }

    linePoints(chart) {
        return (chart.items || [])
            .map((item, index) => `${this.chartPointX(chart, index)},${this.chartPointY(chart, item)}`)
            .join(" ");
    }

    areaPoints(chart) {
        const items = chart.items || [];
        if (!items.length) {
            return "";
        }
        return `4,94 ${this.linePoints(chart)} 96,94`;
    }

    axisLabel(chart, item, index) {
        const count = (chart.items || []).length;
        const interval = Math.max(Math.ceil(count / 8), 1);
        return index === count - 1 || index % interval === 0 ? item.label : "";
    }

    chartMaximum(chart) {
        return Math.max(...this.chartValues(chart).map((value) => Math.abs(value)), 1);
    }

    chartPercent(chart, item) {
        if (item.percent !== undefined && item.percent !== null) {
            return Math.max(0, Math.min(this.toNumber(item.percent), 100));
        }
        const target = this.toNumber(item.target || chart.target);
        if (target > 0) {
            return Math.max(0, Math.min((this.toNumber(item.value) / target) * 100, 100));
        }
        return Math.max(
            0,
            Math.min((Math.abs(this.toNumber(item.value)) / this.chartMaximum(chart)) * 100, 100)
        );
    }

    barStyle(chart, item) {
        return `width: ${Math.max(this.chartPercent(chart, item), item.value ? 2 : 0)}%;`;
    }

    columnStyle(chart, item) {
        return `height: ${Math.max(this.chartPercent(chart, item), item.value ? 4 : 0)}%;`;
    }

    progressStyle(chart, item) {
        const color = item.color || chart.color || "#1b8a7a";
        return `width: ${this.chartPercent(chart, item)}%; background: ${color};`;
    }

    gaugeStyle(chart, item) {
        const percent = this.chartPercent(chart, item);
        const color = item.color || chart.color || "#3562f3";
        return `background: conic-gradient(${color} 0deg ${percent * 3.6}deg, #e7edf2 ${percent * 3.6}deg 360deg);`;
    }

    roundedChartPercent(chart, item) {
        return Math.round(this.chartPercent(chart, item));
    }

    chartTypeLabel(chart) {
        return this.labels.chartTypes[chart.type] || chart.type;
    }

    heatStyle(chart, item) {
        const intensity = Math.max(this.chartPercent(chart, item) / 100, 0.08);
        const color = item.color || chart.color || "27, 138, 122";
        return `--ei-heat-opacity: ${intensity}; --ei-heat-color: ${color};`;
    }

    geoBounds(chart) {
        const items = chart.items || [];
        const latitudes = items.map((item) => this.toNumber(item.latitude));
        const longitudes = items.map((item) => this.toNumber(item.longitude));
        return {
            minLat: Math.min(...latitudes),
            maxLat: Math.max(...latitudes),
            minLon: Math.min(...longitudes),
            maxLon: Math.max(...longitudes),
        };
    }

    geoX(chart, item) {
        const bounds = this.geoBounds(chart);
        const span = bounds.maxLon - bounds.minLon;
        return span ? 8 + ((this.toNumber(item.longitude) - bounds.minLon) / span) * 84 : 50;
    }

    geoY(chart, item) {
        const bounds = this.geoBounds(chart);
        const span = bounds.maxLat - bounds.minLat;
        return span ? 90 - ((this.toNumber(item.latitude) - bounds.minLat) / span) * 80 : 50;
    }

    geoRadius(chart, item) {
        return 3 + Math.sqrt(Math.abs(this.toNumber(item.value)) / this.chartMaximum(chart)) * 7;
    }

    onTableSearch(tableKey, ev) {
        this.state.tableQueries[tableKey] = ev.target.value;
    }

    toggleTableSort(tableKey, columnKey) {
        const current = this.state.tableSorts[tableKey];
        this.state.tableSorts[tableKey] = {
            column: columnKey,
            direction:
                current && current.column === columnKey && current.direction === "asc"
                    ? "desc"
                    : "asc",
        };
    }

    sortIcon(tableKey, columnKey) {
        const current = this.state.tableSorts[tableKey];
        if (!current || current.column !== columnKey) {
            return "fa fa-sort";
        }
        return current.direction === "asc" ? "fa fa-sort-up" : "fa fa-sort-down";
    }

    sortableValue(value) {
        if (typeof value === "number") {
            return value;
        }
        const normalized = String(value ?? "").replace(/[^0-9.-]/g, "");
        const number = Number(normalized);
        return normalized && Number.isFinite(number) ? number : String(value ?? "").toLocaleLowerCase();
    }

    tableRows(table) {
        const query = String(this.state.tableQueries[table.key] || "").trim().toLocaleLowerCase();
        let rows = [...(table.rows || [])];
        if (query) {
            rows = rows.filter((row) =>
                (table.columns || []).some((column) =>
                    String(row[column.key] ?? "").toLocaleLowerCase().includes(query)
                )
            );
        }
        const sort = this.state.tableSorts[table.key];
        if (sort) {
            const direction = sort.direction === "asc" ? 1 : -1;
            rows.sort((left, right) => {
                const leftValue = this.sortableValue(left[sort.column]);
                const rightValue = this.sortableValue(right[sort.column]);
                if (typeof leftValue === "number" && typeof rightValue === "number") {
                    return (leftValue - rightValue) * direction;
                }
                return String(leftValue).localeCompare(String(rightValue)) * direction;
            });
        }
        return rows;
    }

}

registry.category("actions").add(
    "eljohany_executive_intelligence.center",
    ExecutiveIntelligenceCenter
);

