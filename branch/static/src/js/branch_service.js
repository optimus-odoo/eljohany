/** @odoo-module **/

import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";
import { session } from "@web/session";
import { UPDATE_METHODS } from "@web/core/orm_service";
import { cookie } from "@web/core/browser/cookie";

const BIDS_HASH_SEPARATOR = "-";

function parseBranchIds(bids, separator = BIDS_HASH_SEPARATOR) {
    if (typeof bids === "string") {
        return bids.split(separator).map(Number);
    } else if (typeof bids === "number") {
        return [bids];
    }
    return [];
}

function computeActiveBranchIds(bids) {
    const { user_branches } = session;
    let activeBranchIds = bids || [];
    const availableBranchesFromSession = user_branches.allowed_branches;
    const notAllowedBranches = activeBranchIds.filter(
        (id) => !(id in availableBranchesFromSession)
    );
    if (!activeBranchIds.length || notAllowedBranches.length) {
        activeBranchIds = [user_branches.current_branch];
    }
    return activeBranchIds;
}

function getBranchIdsFromBrowser(env) {
    let bids;
    const state = env.services.router.current;

    if ("bids" in state) {
        if (typeof state.bids === "string" && !state.bids.includes(BIDS_HASH_SEPARATOR)) {
            bids = parseBranchIds(state.bids, ",");
        } else {
            bids = parseBranchIds(state.bids);
        }
    } else if (cookie.get("bids")) {
        bids = parseBranchIds(cookie.get("bids"));
    }
    return bids || [];
}

export const BranchService = {
    dependencies: ["action", "orm", "user", "router", "rpc"],
    start(env, { action }) {
        const { user, router, rpc } = env.services;

        const allowedBranches = session.user_branches.allowed_branches;
        const allowedBranchesWithAncestors = {
            ...allowedBranches,
        };


        const activeBranchIds = computeActiveBranchIds(
            getBranchIdsFromBrowser(env)
        );

        cookie.set("bids", activeBranchIds.join(BIDS_HASH_SEPARATOR));
        user.updateContext({ allowed_branch_ids: activeBranchIds });

        env.bus.addEventListener("RPC:RESPONSE", (ev) => {
            const { data, error } = ev.detail;
            const { model, method } = data.params;
            if (!error && model === "res.branch" && UPDATE_METHODS.includes(method)) {
                if (!browser.localStorage.getItem("running_tour")) {
                    action.doAction("reload_context");
                }
            }
        });

        return {
            allowedBranches,
            allowedBranchesWithAncestors,

            get activeBranchIds() {
                return activeBranchIds.slice() || [1];
            },

            get currentBranch() {
                return allowedBranches[activeBranchIds[0]];
            },

            getBranch(branchId) {
                return allowedBranchesWithAncestors[branchId];
            },

            /**
             * @param {Array<>} BranchIds - List of branches to log into
             */
            async setBranches(branchIds) {
                const newBranchIds = branchIds.length ? branchIds : [activeBranchIds[0]];
                for (const branchId of branchIds) {
                    if (!newBranchIds.includes(branchId)) {
                        newBranchIds.push(branchId);
                    }
                }

                cookie.set("bids", newBranchIds.join(BIDS_HASH_SEPARATOR));
                user.updateContext({ allowed_branch_ids: newBranchIds });

                await rpc("/set_brnach", { BranchID: newBranchIds[0] });

                const controller = action.currentController;
                const state = {};
                const options = { reload: true };

                if (controller?.props.resId && controller?.props.resModel) {
                    const hasReadRights = await user.checkAccessRight(
                        controller.props.resModel,
                        "read",
                        controller.props.resId
                    );

                    if (!hasReadRights) {
                        options.replace = true;
                        state.actionStack = router.current.actionStack.slice(0, -1);
                    }
                }
                router.pushState(state, options);
            },
        };
    },
};

registry.category("services").add("Branch", BranchService);
