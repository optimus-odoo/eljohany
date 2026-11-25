EXPIRY_WARNING_DAYS = 90

EXPIRY_MODEL_FIELDS = (
    ("crm.commercial.registration", "expiration_date"),
    ("crm.municipality.license", "expiration_date"),
    ("crm.civil.defense.license", "expiration_date"),
    ("crm.lease.contract", "date_end"),
)


def get_days_remaining(expiry_date, today):
    """Return calendar days until expiry; expiry day itself is zero."""
    return (expiry_date - today).days if expiry_date else 0


def get_expiry_state(expiry_date, today):
    """Return the shared valid/soon/expired state used by every output path."""
    if not expiry_date:
        return "valid"
    days_remaining = get_days_remaining(expiry_date, today)
    if days_remaining < 0:
        return "expired"
    if days_remaining <= EXPIRY_WARNING_DAYS:
        return "soon"
    return "valid"
