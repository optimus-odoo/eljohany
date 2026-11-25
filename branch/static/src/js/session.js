/** @odoo-module **/

import { Dropdown } from "@web/core/dropdown/dropdown";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";
import { registry } from "@web/core/registry";
import { session } from "@web/session";
import { Component, useChildSubEnv, useRef, useState } from "@odoo/owl";
import { symmetricalDifference } from "@web/core/utils/arrays";
import { useService } from "@web/core/utils/hooks";
import { SwitchBranchItem } from "@branch/js/switch_branch_item";

/**
 * Helper that manages the currently selected branch ids and applies them
 * through the Branch service.
 */
class BranchSelector {
    constructor(BranchService) {
        this.BranchService = BranchService;
        this.selectedBranchesIds = BranchService.activeBranchIds.slice();
    }

    get hasSelectionChanged() {
        return (
            symmetricalDifference(
                this.selectedBranchesIds,
                this.BranchService.activeBranchIds
            ).length > 0
        );
    }

    isBranchSelected(BranchId) {
        return this.selectedBranchesIds.includes(BranchId);
    }

    switchBranch(mode, BranchId) {
        if (mode === "toggle") {
            if (this.selectedBranchesIds.includes(BranchId)) {
                this._deselectBranch(BranchId);
            } else {
                this._selectBranch(BranchId);
            }
        } else if (mode === "loginto") {
            if (this._isSingleBranchMode()) {
                // keep single-root context
                this.selectedBranchesIds.splice(0, this.selectedBranchesIds.length);
            }
            this._selectBranch(BranchId, true);
            this.apply();
            // no dropdown.close() in v17 — Dropdown handles itself
        }
    }

    _selectBranch(BranchId, unshift = false) {
        if (!this.selectedBranchesIds.includes(BranchId)) {
            if (unshift) {
                this.selectedBranchesIds.unshift(BranchId);
            } else {
                this.selectedBranchesIds.push(BranchId);
            }
        } else if (unshift) {
            const index = this.selectedBranchesIds.findIndex((b) => b === BranchId);
            this.selectedBranchesIds.splice(index, 1);
            this.selectedBranchesIds.unshift(BranchId);
        }
    }

    _deselectBranch(BranchId) {
        if (this.selectedBranchesIds.includes(BranchId)) {
            this.selectedBranchesIds.splice(this.selectedBranchesIds.indexOf(BranchId), 1);
        }
    }

    apply() {
        this.BranchService.setBranches(this.selectedBranchesIds, false);
    }

    _isSingleBranchMode() {
        if (this.selectedBranchesIds.length === 1) {
            return true;
        }
        const getActiveBranch = (BranchId) => {
            const isActive = this.selectedBranchesIds.includes(BranchId);
            return isActive ? this.BranchService.getBranch(BranchId) : null;
        };
        let rootBranch;
        for (const branchId of this.selectedBranchesIds) {
            const branch = getActiveBranch(branchId);
            if (rootBranch === undefined) {
                rootBranch = branch;
            } else if (rootBranch !== branch) {
                return false;
            }
        }
        return true;
    }

    reset() {
        this.selectedBranchesIds = this.BranchService.activeBranchIds.slice();
    }

    selectAll() {
        if (this.selectedBranchesIds.length > 0) {
            this.selectedBranchesIds.splice(0, this.selectedBranchesIds.length);
        } else {
            const newIds = Object.values(this.BranchService.allowedBranches).map((b) => b.id);
            this.selectedBranchesIds.splice(0, this.selectedBranchesIds.length, ...newIds);
        }
    }
}

export class SwitchBranchMenu extends Component {
    static template = "web.SwitchBranchMenu";
    static components = { Dropdown, DropdownItem, SwitchBranchItem };
    static props = {};

    setup() {
        this.BranchService = useService("Branch");

        this.BranchSelector = useState(new BranchSelector(this.BranchService));
        useChildSubEnv({ BranchSelector: this.BranchSelector });

        this.searchInputRef = useRef("inputRef");
        this.containerRef = useRef("containerRef");

        this.state = useState({
            searchFilter: "",
            showFilter: false,
        });
        this.resetState();
    }

    // ---- getters ----
    get hasLotsOfBranches() {
        return Object.values(this.BranchService.allowedBranchesWithAncestors).length > 9;
    }

    get branchesEntries() {
        const branches = [];
        const addBranch = (branch, level = 0) => {
            if (this.matchSearch(branch.name)) {
                branches.push({ branch, level });
            }
            if (branch.child_ids) {
                for (const branchId of branch.child_ids) {
                    addBranch(this.BranchService.getBranch(branchId), level + 1);
                }
            }
        };
        Object.values(this.BranchService.allowedBranchesWithAncestors)
            .filter((b) => !b.parent_id)
            .sort((b1, b2) => b1.sequence - b2.sequence)
            .forEach((b) => addBranch(b));
        return branches;
    }

    get selectAllClass() {
        return this.BranchSelector.selectedBranchesIds.length >=
            Object.values(this.BranchService.allowedBranches).length
            ? "btn-link text-primary"
            : "btn-link text-secondary";
    }

    get selectAllIcon() {
        if (
            this.BranchSelector.selectedBranchesIds.length >=
            Object.values(this.BranchService.allowedBranches).length
        ) {
            return "fa-check-square text-primary";
        } else if (this.BranchSelector.selectedBranchesIds.length > 0) {
            return "fa-minus-square-o";
        } else {
            return "fa-square-o";
        }
    }

    get isSingleBranch() {
        return Object.values(this.BranchService.allowedBranchesWithAncestors ?? {}).length === 1;
    }

    // ---- ui helpers ----
    resetState() {
        this.state.searchFilter = "";
        this.state.showFilter = this.hasLotsOfBranches;
    }

    onSearch(ev) {
        this.state.searchFilter = ev.target.value;
        this.state.showFilter = true;
    }

    matchSearch(branchName) {
        if (!this.state.searchFilter) return true;
        const name = branchName.toLocaleLowerCase().replace(/\s/g, "");
        const filter = this.state.searchFilter.toLocaleLowerCase().replace(/\s/g, "");
        return name.includes(filter);
    }

    // If your QWeb template binds to dropdown open/close, keep these:
    onDropdownOpen() {
        if (this.searchInputRef.el) {
            this.searchInputRef.el.focus();
        }
        if (this.containerRef.el) {
            const currentWidth = this.containerRef.el.getBoundingClientRect().width;
            this.containerRef.el.style.width = currentWidth + "px";
        }
    }

    onDropdownClose() {
        this.resetState();
    }

    confirm() {
        this.BranchSelector.apply();
    }

    onBranchClick(ev) {
        ev.preventDefault();
        const branchId = parseInt(ev.currentTarget.dataset.branchId);
        this.BranchSelector.switchBranch("loginto", branchId);
        window.location.reload();
    }
}

export const systrayItem = {
    Component: SwitchBranchMenu,
    isDisplayed(env) {
        const { allowedBranches } = env.services.Branch;
        return Object.keys(allowedBranches).length > 1;
    },
};

if (session.display_switch_branch_menu) {
    registry.category("systray").add("SwitchBranchMenu", systrayItem, { sequence: 1 });
}
