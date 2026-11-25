# HR Management Attendance API

Standalone Odoo 17 REST API for branch-based GPS attendance.

## Features

- Separate employee API credentials using PBKDF2-SHA256 password hashes.
- Non-interactive Odoo administrator authentication with API-key support. Users
  protected by two-factor authentication must use an Odoo API key.
- Opaque bearer tokens stored only as SHA-256 digests.
- Token expiry, revocation, login lockout, and scheduled cleanup.
- Company-scoped branch, employee, and attendance administration.
- GPS radius and accuracy validation with optional attendance windows.
- Row-level employee locking and optional idempotency keys.
- Immutable accepted-event evidence linked to normal `hr.attendance` records.
- Soft deletion of branches and employees.
- Paginated list endpoints and stable JSON error codes.
- Configurable exact-origin browser CORS allowlist.
- Configurable pull connector for the external Laravel HR API.
- Manual date-range pulls, 15-minute scheduled pulls, reference mapping, and synchronization logs.

## API routes

| Method | Route | Role |
| --- | --- | --- |
| POST | `/api/login` | Public |
| GET | `/api/me` | Any token |
| POST | `/api/logout` | Any token |
| POST | `/api/attendance/check-in` | Employee |
| POST | `/api/attendance/check-out` | Employee |
| GET/POST | `/api/admin/branches` | API administrator |
| GET/PUT/DELETE | `/api/admin/branches/{id}` | API administrator |
| GET/POST | `/api/admin/employees` | API administrator |
| GET/PUT/DELETE | `/api/admin/employees/{id}` | API administrator |
| GET | `/api/admin/attendances` | API administrator |
| GET | `/api/admin/attendances/{id}` | API administrator |

All protected routes use `Authorization: Bearer <token>`. Clients should send a
unique `Idempotency-Key` header for attendance writes.

`morning` and `evening` are treated as the submitted check-in/check-out periods.
The module intentionally permits one completed `hr.attendance` record per employee
per local calendar day so it remains compatible with the existing payroll
attendance constraint. A second independent shift on the same day is rejected.

## Installation

1. Install or upgrade the repository's `branch` and standard `hr_attendance` addons.
2. Install `hr_management_attend_api`.
3. Grant **Attendance API Administrator** only to designated administrators.
4. Configure token lifetimes, page limits, and browser origins in Settings.
5. Configure GPS and attendance fields on each branch.
6. Create employees through the API or configure their Attendance API tab.

Deleting a branch or employee through the API deactivates it so historical
attendance remains auditable.

## External attendance pull

Only an Odoo system administrator can configure the upstream connector under
**Settings > Attendance API > External HR Attendance Pull**.

Configuration includes:

- External API base URL, administrator email/password or bearer token.
- Target Odoo company, upstream timezone, TLS verification, timeout, and page size.
- Branch and employee matching, optional creation of missing reference records,
  and optional updates to already matched records.
- Scheduled synchronization every 15 minutes with a configurable 1-31 day
  lookback window.
- Configurable 5-1440 minute schedule with unlimited executions, automatic
  repair/reactivation when settings are saved, and a safe migration for older
  one-shot scheduled actions.
- Bounded retries for temporary network and HTTP failures, per-day isolation,
  and an advisory lock that prevents overlapping manual and scheduled pulls.
- Operational health fields for the last attempt, last successful pull, and
  consecutive failures.
- Cross-company pull-log visibility for system administrators, while dedicated
  Attendance API administrators remain limited to their active companies.
- A responsive pull-log form with metric cards and a full-width, mixed-direction
  details panel for readable Arabic and English diagnostics.
- A manual **Pull Attendance Now** action for a selected date range, with
  optional branch, employee, and morning/evening shift filters.

Branches are linked using immutable external IDs. Employees are matched for
external attendance pulls exclusively by **API Employee Number**; external
employee IDs, work email, the configured company, and branch mapping are not
used for employee selection. A missing branch mapping does not block an
attendance import. Attendance records are upserted by external attendance ID,
so repeated pulls do not create duplicates. Each run is recorded under
**Attendances > Attendance API > Attendance Pull Logs**.

Automatic creation of missing branches and employees is disabled by default.
The external password and bearer token are stored in access-restricted Odoo
system parameters and are write-only in the Settings UI; prefer a dedicated
least-privilege upstream administrator.
