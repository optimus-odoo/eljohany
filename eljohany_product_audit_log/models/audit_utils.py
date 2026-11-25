import uuid

from odoo import _, fields


EXCLUDED_FIELDS = {
    "__last_update",
    "change_log_ids",
    "create_date",
    "create_uid",
    "variant_change_log_ids",
    "write_date",
    "write_uid",
}
MAX_VALUE_LENGTH = 4000


def auditable_field_names(record, vals, skip_template_related=False):
    names = []
    for field_name in vals:
        field = record._fields.get(field_name)
        if not field or field_name in EXCLUDED_FIELDS:
            continue
        if skip_template_related and field.related and field.related[0] == "product_tmpl_id":
            continue
        names.append(field_name)
    return names


def display_value(record, field_name):
    record = record.sudo()
    field = record._fields[field_name]
    value = record[field_name]

    if field.type == "boolean":
        result = _("Yes") if value else _("No")
    elif field.type == "many2one":
        result = value.display_name if value else ""
    elif field.type in ("many2many", "one2many"):
        result = ", ".join(value.sorted("id").mapped("display_name"))
    elif field.type == "selection":
        selection = dict(field._description_selection(record.env))
        result = selection.get(value, value or "")
    elif field.type == "binary":
        result = _("File set") if value else _("No file")
    elif field.type == "date":
        result = fields.Date.to_string(value) if value else ""
    elif field.type == "datetime":
        result = fields.Datetime.to_string(value) if value else ""
    elif value is False or value is None:
        result = ""
    else:
        result = str(value)

    result = str(result)
    if len(result) > MAX_VALUE_LENGTH:
        return "%s..." % result[: MAX_VALUE_LENGTH - 3]
    return result


def prepare_values(records, vals, skip_template_related=False):
    field_names = auditable_field_names(
        records, vals, skip_template_related=skip_template_related
    )
    return {
        record.id: {
            field_name: display_value(record, field_name)
            for field_name in field_names
        }
        for record in records
    }


def create_log_entries(records, before_values, target_model):
    if not before_values:
        return

    changed_on = fields.Datetime.now()
    operation_id = uuid.uuid4().hex
    entries = []
    for record in records:
        sudo_record = record.sudo()
        for field_name, old_value in before_values.get(record.id, {}).items():
            new_value = display_value(sudo_record, field_name)
            if old_value == new_value:
                continue
            field = record._fields[field_name]
            template = (
                sudo_record
                if target_model == "product.template"
                else sudo_record.product_tmpl_id
            )
            company = template.company_id
            entries.append(
                {
                    "product_tmpl_id": template.id,
                    "product_id": record.id if target_model == "product.product" else False,
                    "target_model": target_model,
                    "target_name": sudo_record.display_name,
                    "target_res_id": record.id,
                    "field_name": field_name,
                    "field_label": field.string or field_name,
                    "old_value": old_value,
                    "new_value": new_value,
                    "changed_by_id": records.env.user.id,
                    "changed_on": changed_on,
                    "operation_id": operation_id,
                    "company_id": company.id if company else False,
                }
            )

    if entries:
        records.env["eljohany.product.audit.log"].sudo().with_context(
            _product_audit_internal_create=True
        ).create(entries)
