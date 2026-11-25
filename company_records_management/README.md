# Company Records Management — Odoo 17

Version: `17.0.3.2.0`. Technical module name: `company_records_management`.

## One workspace

The app opens directly to **ملف الشركة** (Company File). Users select a
company and optionally a branch, then work in tabs on the same screen:

- Overview with expiry counts and clickable document summaries.
- Branches and company partners.
- Commercial registrations, municipality and civil defense licenses.
- National addresses, electricity meters, bank accounts, and leases.

Add and edit forms open as dialogs. Saving or cancelling returns to the
same tab. New records receive the selected company and branch as defaults.
Branch-specific records require a branch selection before creation.
Lists support search and pagination. Company data, attachments, Excel
export, and the company PDF report are accessible from the workspace.

Excel and dashboard counts follow the company/branch selection. The company
PDF report includes all company branches. Partners always belong to the
whole company. Audit access remains restricted to Manager/Auditor groups.

The old submenu entries are deactivated on upgrade, preserving their
external IDs and the existing records. No business records are migrated or
deleted. See [the Arabic user guide](USER_GUIDE_AR.md).

## Installation and upgrade

1. Place `company_records_management` in an Odoo 17 custom addons directory.
   Include its parent directory in `addons_path`.
2. Ensure `xlsxwriter` is installed in the Python environment running Odoo.
   Standard addon dependencies are `base`, `mail`, and `web`.
3. Restart Odoo and update the Apps list in developer mode.
4. Install **Company Records Management Enterprise**, or **upgrade** the
   module if the previous version is already installed. Reload the browser
   after upgrading to load the new interface.
5. Assign Records User or Records Manager to the relevant internal users.

PDF printing requires an Odoo-compatible `wkhtmltopdf` installation.
Exclude `.venv`, `.idea`, and `__pycache__` when deploying the module.

## Validation

The validation environment uses Python 3.10.12, PostgreSQL 14.24, and
Odoo 17 Community at commit `dd7a1b58744f95898b7305a6dedfc1b29a6d4949`.
The previous version was installed into a fresh database; the workspace
version is validated by upgrading that database.

On 2026-09-19, the upgrade and all eight server integration tests passed.
The separate Chrome workflow test also passed, covering the live workspace
as an ordinary Records User (nine passing tests in total).

Integration coverage includes view loading, the single app entry point,
record workflows and audit creation, filtered dashboard data, recurring
expiry activities, scoped Excel export including leases, and report HTML.
The Chrome test exercises company switching, record tabs, branch defaults,
creation, editing, and returning to the same tab.

Enterprise-specific addons and PDF binary generation are outside this
validation environment; report HTML is covered.

Run tests on a disposable database using your Odoo runtime:

```sh
/path/to/odoo/python /path/to/odoo/odoo-bin \
  -c /path/to/odoo.conf -d records_install_test \
  -i company_records_management --without-demo=all \
  --test-enable --test-tags=/company_records_management \
  --stop-after-init --http-interface=127.0.0.1 --max-cron-threads=0
```

Use `-u company_records_management` for upgrade tests. The browser test
requires Chrome and the Python package `websocket-client` in the test
runtime. They are not module installation dependencies.
