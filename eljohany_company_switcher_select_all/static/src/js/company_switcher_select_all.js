/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import {
    CompanySelector,
    SwitchCompanyMenu,
} from "@web/webclient/switch_company_menu/switch_company_menu";

patch(CompanySelector.prototype, {
    get selectableCompanyIds() {
        return Object.values(this.companyService.allowedCompanies)
            .sort((companyA, companyB) => {
                const sequenceDifference = companyA.sequence - companyB.sequence;
                return sequenceDifference || companyA.id - companyB.id;
            })
            .map((company) => company.id);
    },

    get allCompaniesSelected() {
        const selectableCompanyIds = this.selectableCompanyIds;
        return (
            selectableCompanyIds.length > 0 &&
            selectableCompanyIds.every((companyId) =>
                this.selectedCompaniesIds.includes(companyId)
            )
        );
    },

    toggleAllCompanies() {
        const selectableCompanyIds = this.selectableCompanyIds;
        if (!selectableCompanyIds.length) {
            return;
        }

        const currentCompanyId = this.companyService.currentCompany.id;
        const fallbackCompanyId = selectableCompanyIds[0];
        const companyToKeep = selectableCompanyIds.includes(currentCompanyId)
            ? currentCompanyId
            : fallbackCompanyId;
        const nextCompanyIds = this.allCompaniesSelected
            ? [companyToKeep]
            : [
                  companyToKeep,
                  ...selectableCompanyIds.filter(
                      (companyId) => companyId !== companyToKeep
                  ),
              ];

        this.selectedCompaniesIds.splice(
            0,
            this.selectedCompaniesIds.length,
            ...nextCompanyIds
        );
        this._apply();
    },
});

patch(SwitchCompanyMenu.prototype, {
    get allCompaniesSelected() {
        return this.companySelector.allCompaniesSelected;
    },

    get selectableCompanyCount() {
        return this.companySelector.selectableCompanyIds.length;
    },

    get toggleAllCompaniesLabel() {
        return this.allCompaniesSelected ? _t("Clear All") : _t("Select All");
    },

    toggleAllCompanies() {
        this.companySelector.toggleAllCompanies();
    },
});
