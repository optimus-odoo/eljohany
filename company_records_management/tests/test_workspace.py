from odoo.tests import HttpCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestWorkspace(HttpCase):
    def test_workspace_browser(self):
        user = new_test_user(
            self.env, login='workspace_user',
            groups='base.group_user,company_records_management.group_records_user',
        )
        company = self.env['crm.company.record'].create({'name': 'Workspace Company A'})
        other_company = self.env['crm.company.record'].create({'name': 'Workspace Company B'})
        branch = self.env['crm.company.branch'].create({'name': 'Workspace Branch A', 'company_id': company.id})
        self.env['crm.company.branch'].create({'name': 'Workspace Branch B', 'company_id': other_company.id})
        action = self.env.ref('company_records_management.action_dashboard')
        code = """
        (async () => {
            const wait = async (fn, message) => {
                for (let i = 0; i < 300; i++) {
                    if (fn()) return;
                    await new Promise(resolve => setTimeout(resolve, 100));
                }
                throw new Error(message);
            };
            const find = (selector) => document.querySelector(selector);
            const loaded = () => find('#crm_workspace_panel')?.getAttribute('aria-busy') === 'false';
            const click = async (selector) => {
                await wait(() => find(selector), `Missing ${selector}`);
                find(selector).click();
                await new Promise(resolve => setTimeout(resolve, 100));
                await wait(loaded, 'Workspace did not finish loading');
            };
            const choose = async (selector, value) => {
                find(selector).value = String(value);
                find(selector).dispatchEvent(new Event('change', {bubbles: true}));
                await new Promise(resolve => setTimeout(resolve, 100));
                await wait(loaded, 'Selection did not finish loading');
            };
            await wait(loaded, 'Workspace did not open');
            await choose('#crm_workspace_company', COMPANY_ID);
            if (document.querySelectorAll('.o_crm_summary_card').length !== 4) throw new Error('Missing summary cards');
            await click('#crm_tab_branches');
            if (!find('.o_crm_records_table').textContent.includes('Workspace Branch A')) throw new Error('Missing company branch');
            if (find('.o_crm_records_table').textContent.includes('Workspace Branch B')) throw new Error('Leaked another company branch');
            await choose('#crm_workspace_company', OTHER_COMPANY_ID);
            if (!find('.o_crm_records_table').textContent.includes('Workspace Branch B')) throw new Error('Company selection did not refresh records');
            await choose('#crm_workspace_company', COMPANY_ID);
            await click('#crm_tab_municipality');
            if (!find('.o_crm_add_record').disabled) throw new Error('Missing branch guard');
            await choose('#crm_workspace_branch', BRANCH_ID);
            await click('.o_crm_add_record');
            await wait(() => find('.modal .o_field_widget[name="name"] input'), 'Record dialog did not open');
            const branchField = find('.modal .o_field_widget[name="branch_id"] input');
            if (!branchField?.value.includes('Workspace Branch A')) throw new Error('Branch was not prefilled');
            const input = find('.modal .o_field_widget[name="name"] input');
            input.value = 'WORKSPACE-LICENSE';
            input.dispatchEvent(new Event('input', {bubbles: true}));
            input.dispatchEvent(new Event('change', {bubbles: true}));
            const date = find('.modal .o_field_widget[name="expiration_date"] input');
            date.value = '12/31/2030';
            date.dispatchEvent(new Event('input', {bubbles: true}));
            date.dispatchEvent(new Event('change', {bubbles: true}));
            date.blur();
            find('.modal .o_form_button_save').click();
            await wait(() => !find('.modal') && loaded(), 'Save did not return to the workspace');
            if (!find('.o_crm_records_table')?.textContent.includes('WORKSPACE-LICENSE')) throw new Error('Saved record missing');
            if (find('#crm_tab_municipality').getAttribute('aria-selected') !== 'true') throw new Error('Current tab was lost');
            await click('.o_crm_open_record');
            await wait(() => find('.modal .o_field_widget[name="name"] input')?.value === 'WORKSPACE-LICENSE', 'Edit did not open the saved record');
            find('.modal .o_form_button_cancel').click();
            await wait(() => !find('.modal') && loaded(), 'Cancel did not return to the workspace');
            for (const tab of ['partners', 'registrations', 'civil', 'addresses', 'electricity', 'banks', 'leases', 'overview']) {
                await click('#crm_tab_' + tab);
            }
            if (find('.o_crm_workspace .alert-danger')) throw new Error('Workspace reported an error');
            console.log('test successful');
        })().catch(error => console.error(error));
        """.replace('OTHER_COMPANY_ID', str(other_company.id)).replace('COMPANY_ID', str(company.id)).replace('BRANCH_ID', str(branch.id))
        self.browser_js(f'/web#action={action.id}', code, login=user.login, timeout=120)
