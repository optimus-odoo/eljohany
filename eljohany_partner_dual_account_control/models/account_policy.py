RECEIVABLE_ACCOUNT_TYPE = "asset_receivable"
PAYABLE_ACCOUNT_TYPE = "liability_payable"


def get_direction_account(partner, company, direction, fiscal_position=None):
    """Return the commercial partner's company-specific settlement account."""
    if not partner or not company:
        return (partner or company).env["account.account"] if (partner or company) else None

    commercial_partner = partner.commercial_partner_id.with_company(company)
    if direction == "customer":
        account = commercial_partner.property_account_receivable_id
    elif direction == "supplier":
        account = commercial_partner.property_account_payable_id
    else:
        return partner.env["account.account"]

    if account and fiscal_position:
        account = fiscal_position.with_company(company).map_account(account)
    return account


def get_account_issues(account, company, expected_type):
    """Return stable issue codes so models and the audit wizard share one policy."""
    issues = []
    if not account:
        return ["missing"]
    if account.account_type != expected_type:
        issues.append("wrong_type")
    if account.deprecated:
        issues.append("deprecated")
    if not account.reconcile:
        issues.append("not_reconcilable")
    company_domain = account._check_company_domain(company)
    if not account.filtered_domain(company_domain):
        issues.append("wrong_company")
    return issues
