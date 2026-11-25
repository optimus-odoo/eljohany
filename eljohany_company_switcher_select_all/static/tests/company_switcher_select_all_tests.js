/** @odoo-module **/

import "@eljohany_company_switcher_select_all/js/company_switcher_select_all";
import { CompanySelector } from "@web/webclient/switch_company_menu/switch_company_menu";

QUnit.module("Company Switcher Select All", () => {
    QUnit.test("select all keeps current first and applies allowed companies", (assert) => {
        const applications = [];
        const companyService = {
            activeCompanyIds: [2],
            currentCompany: { id: 2 },
            allowedCompanies: {
                1: { id: 1, sequence: 1 },
                2: { id: 2, sequence: 2 },
                3: { id: 3, sequence: 3 },
            },
            setCompanies(companyIds, includeChildCompanies) {
                applications.push({ companyIds: [...companyIds], includeChildCompanies });
            },
        };
        const selector = new CompanySelector(companyService, 0);

        selector.toggleAllCompanies();

        assert.deepEqual(selector.selectedCompaniesIds, [2, 1, 3]);
        assert.deepEqual(applications, [
            { companyIds: [2, 1, 3], includeChildCompanies: false },
        ]);
        assert.true(selector.allCompaniesSelected);
    });

    QUnit.test("clear all keeps the current company active", (assert) => {
        const applications = [];
        const companyService = {
            activeCompanyIds: [2, 1, 3],
            currentCompany: { id: 2 },
            allowedCompanies: {
                1: { id: 1, sequence: 1 },
                2: { id: 2, sequence: 2 },
                3: { id: 3, sequence: 3 },
            },
            setCompanies(companyIds, includeChildCompanies) {
                applications.push({ companyIds: [...companyIds], includeChildCompanies });
            },
        };
        const selector = new CompanySelector(companyService, 0);

        selector.toggleAllCompanies();

        assert.deepEqual(selector.selectedCompaniesIds, [2]);
        assert.deepEqual(applications, [
            { companyIds: [2], includeChildCompanies: false },
        ]);
        assert.false(selector.allCompaniesSelected);
    });
});
