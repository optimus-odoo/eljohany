/* @odoo-module */
import { registry } from '@web/core/registry';
import { useService } from "@web/core/utils/hooks";
const { Component, onMounted, onWillStart, useRef, useState } = owl;
import { renderToString } from "@web/core/utils/render";
import { cookie } from "@web/core/browser/cookie";
import { renderToElement } from "@web/core/utils/render";
import { _t } from "@web/core/l10n/translation";
import { session } from "@web/session";

class ConstructionDashboard extends Component {
    setup() {
        this.action = useService("action");
        this.orm = useService("orm");
        this.rpc = useService("rpc");
        this.current_user_id = session.user_id
        this.ConstructManagementDashboard = {}
        super.setup();
        onWillStart(this.onWillStart);
        onMounted(this.onMounted.bind(this));
    }

    async onWillStart() {
        await this.fetch_data();
    }
    
    async fetch_data() {
        await this.loadGoogleCharts();
    }

    onMounted() {
        this.drawCharts();  // Load and draw charts
    }

    async loadGoogleCharts() {
        return new Promise((resolve) => {
            google.charts.load('current', { 'packages': ['corechart', 'bar'] });
            google.charts.setOnLoadCallback(() => resolve());
        });
    }

    async drawCharts() {
        try {
            // Load data and Google Charts
            const dashboardData = await this.rpc("/construct/dashboard", {});
            this.ConstructManagementDashboard = dashboardData;
            this.drawGraphs(dashboardData);  // Draw the charts with the fetched data
            this.render_dashboards(dashboardData);  // Only render after data is fetched
        } catch (e) {
            console.error("Error loading charts or data", e);
        }
    }

    drawGraphs(result) {
        try {
            // Project Pie chart
            const project_data = google.visualization.arrayToDataTable(result['project_state_data']);
            const project_options = {
                backgroundColor: 'transparent',
                pieHole: 0.4,
            };
            const project_chart = new google.visualization.PieChart(document.getElementById('project_state_chart'));
            project_chart.draw(project_data, project_options);

            // Task Pie chart
            const task_data = google.visualization.arrayToDataTable(result['task_stage_data']);
            const task_options = {
                backgroundColor: 'transparent',
                is3D: true,
            };
            const task_chart = new google.visualization.PieChart(document.getElementById('task_stage_chart'));
            task_chart.draw(task_data, task_options);

            // Yearly Invoices Line Chart
            const invoice_data = google.visualization.arrayToDataTable(result['project_invoice_yearly']);
            const invoice_options = {
                backgroundColor: 'transparent',
                hAxis: { title: 'Month' },
                vAxis: { title: 'Total Invoices' },
                legend: 'none',
                bar: { groupWidth: "75%" }
            };
            const invoice_chart = new google.visualization.ColumnChart(document.getElementById('project_invoice_yearly'));
            invoice_chart.draw(invoice_data, invoice_options);

            // Cost Type Wise Estimated Amount Column chart
            const column_data = google.visualization.arrayToDataTable(result['cost_type_estimated_amount_yearly']);
            const column_options = {
                backgroundColor: 'transparent',
                legend: 'none',
                bar: { groupWidth: "40%" },
            };
            const column_chart = new google.visualization.ColumnChart(document.getElementById('cost_type_estimated_amount_yearly'));
            column_chart.draw(column_data, column_options);

        } catch (e) {
            console.error("Error drawing charts", e);
        }
    }
    
    view_job_costing(self) {
        var action = {
            name: _t('All Cost Sheets'),
            type: 'ir.actions.act_window',
            res_model: 'job.costing',
            domain: [['user_id', '=', self.current_user_id]],
            views: [[false, 'list'], [false, 'form']],
            target: 'current'
        };
        self.action.doAction(action);
    }

    view_projects(self) {
        var action = {
            name: _t('All Projects'),
            type: 'ir.actions.act_window',
            res_model: 'project.project',
            domain: [['user_id', '=', self.current_user_id]],
            views: [[false, 'list'], [false, 'form']],
            target: 'current'
        };
        self.action.doAction(action);
    }
        
    view_tasks(self) {
        var action = {
            name: _t('All Tasks'),
            type: 'ir.actions.act_window',
            res_model: 'project.task',
            domain: [['project_id', '!=', false],['user_ids', 'in', self.current_user_id]],
            views: [[false, 'list'], [false, 'form']],
            target: 'current'
        };
        self.action.doAction(action);
    } 

    view_contractors(self) {
        var action = {
            name: _t('All Contractors'),
            type: 'ir.actions.act_window',
            res_model: 'res.partner',
            views: [[false, 'list'], [false, 'form']],
            target: 'current'
        };
        self.action.doAction(action);
    }
   
    view_bills(self) {
        var action = {
            name: _t('All Bills'),
            type: 'ir.actions.act_window',
            res_model: 'account.move',
            domain: ['|', '|', ['project_id', '!=', false], ['task_id', '!=', false], ['job_cost_id', '!=', false]],
            views: [[false, 'list'], [false, 'form']],
            target: 'current'
        };
        self.action.doAction(action);
    }

    view_picking(self) {
        var action = {
            name: _t('All Pickings'),
            type: 'ir.actions.act_window',
            res_model: 'stock.picking',
            domain: ['|', '|', ['project_id', '!=', false], ['task_id', '!=', false], ['job_cost_id', '!=', false]],
            views: [[false, 'list'], [false, 'form']],
            target: 'current'
        };
        self.action.doAction(action);
    }

    view_inspection(self) {
        var action = {
            name: _t('All Inspections'),
            type: 'ir.actions.act_window',
            res_model: 'construct.inspector',
            domain: [['inspector_id', '=', self.current_user_id]],
            views: [[false, 'list'], [false, 'form']],
            target: 'current'
        };
        self.action.doAction(action);
    }

    view_compliance(self) {
        var action = {
            name: _t('All Compliance'),
            type: 'ir.actions.act_window',
            res_model: 'construct.compliance',
            views: [[false, 'list'], [false, 'form']],
            target: 'current'
        };
        self.action.doAction(action);
    }

    view_material(self) {
        var action = {
            name: _t('All Materials'),
            type: 'ir.actions.act_window',
            res_model: 'product.product',
            views: [[false, 'list'], [false, 'form']],
            target: 'current'
        };
        self.action.doAction(action);
    }

    view_purchase_requisition(self) {
        var action = {
            name: _t('All Purchase'),
            type: 'ir.actions.act_window',
            res_model: 'material.purchase.requisition',
            domain: [['requisition_type', '=', 'purchase'], ['task_user_ids', 'in', self.current_user_id]],
            views: [[false, 'list'], [false, 'form']],
            target: 'current'
        };
        self.action.doAction(action);
    }

    view_internal_requisition(self) {
        var action = {
            name: _t('All Purchase'),
            type: 'ir.actions.act_window',
            res_model: 'material.purchase.requisition',
            domain: [['requisition_type', '=', 'internal'], ['task_user_ids', 'in', self.current_user_id]],
            views: [[false, 'list'], [false, 'form']],
            target: 'current'
        };
        self.action.doAction(action);
    }

    view_scrap_requisition(self) {
        var action = {
            name: _t('All Purchase'),
            type: 'ir.actions.act_window',
            res_model: 'material.purchase.requisition',
            domain: [['requisition_type', '=', 'scrap'], ['task_user_ids', 'in', self.current_user_id]],
            views: [[false, 'list'], [false, 'form']],
            target: 'current'
        };
        self.action.doAction(action);
    }

    render_dashboards(result) {
        // Count
        $('#job_costing_count').text(result['job_costing_count']);
        $('#projects_count').text(result['projects_count']);
        $('#tasks_count').text(result['tasks_count']);
        $('#contractors_count').text(result['contractors_count']);
        $('#bills_count').text(result['bills_count']);
        $('#picking_count').text(result['picking_count']);
        $('#inspection_count').text(result['inspection_count']);
        $('#compliance_count').text(result['compliance_count']);
        $('#materials_count').text(result['materials_count']);
        $('#purchase_count').text(result['purchase_count']);
        $('#in_picking_count').text(result['in_picking_count']);
        $('#scraps_count').text(result['scraps_count']);
        // Button
        $('.job_costing').click(() => {this.view_job_costing(this);});
        $('.projects').click(() => {this.view_projects(this);});
        $('.tasks').click(() => {this.view_tasks(this);});
        $('.contractors').click(() => {this.view_contractors(this);});
        $('.bills').click(() => {this.view_bills(this);});
        $('.picking').click(() => {this.view_picking(this);});
        $('.inspection').click(() => {this.view_inspection(this);});
        $('.compliance').click(() => {this.view_compliance(this);});
        $('.material').click(() => {this.view_material(this);});
        $('.purchase_requisition').click(() => {this.view_purchase_requisition(this);});
        $('.internal_requisition').click(() => {this.view_internal_requisition(this);});
        $('.scrap_requisition').click(() => {this.view_scrap_requisition(this);});
    }
}

ConstructionDashboard.template = "ConstructionDashboard";
registry.category("actions").add("construct_dashboard", ConstructionDashboard);
