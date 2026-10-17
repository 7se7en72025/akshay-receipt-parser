from decimal import Decimal

from .models import Invoice

TOLERANCE = Decimal("0.02")


def validate_invoice(invoice: Invoice, duplicate_ids=None):
    issues = []

    def issue(level, field, message, row=None):
        issues.append({"level": level, "field": field, "message": message, "row": row})

    for field, label in [
        ("supplier_name", "Supplier name"),
        ("bill_number", "Bill number"),
        ("bill_date", "Bill date"),
        ("taxable_total", "Taxable total"),
        ("grand_total", "Grand total"),
    ]:
        value = getattr(invoice, field)
        if value is None or (isinstance(value, str) and not value.strip()):
            issue("error", field, f"{label} is required before approval.")
    if not invoice.items:
        issue("error", "items", "Add at least one product row before approval.")
    for index, item in enumerate(invoice.items):
        for field, label in [
            ("description", "Product description"),
            ("quantity", "Quantity"),
            ("unit", "Unit"),
            ("unit_price", "Rate"),
            ("taxable_amount", "Taxable amount"),
        ]:
            value = getattr(item, field)
            if value is None or (isinstance(value, str) and not value.strip()):
                issue("error", field, f"{label} is missing on item {index + 1}.", index)
        if item.quantity == 0:
            issue("warning", "quantity", f"Item {index + 1} has zero quantity.", index)
        for field in ("cgst_rate", "sgst_rate", "igst_rate"):
            value = getattr(item, field)
            if value is not None and value > 100:
                issue("error", field, f"Tax rate exceeds 100% on item {index + 1}.", index)
        for prefix in ("cgst", "sgst", "igst"):
            rate = getattr(item, prefix + "_rate")
            amount = getattr(item, prefix + "_amount")
            if rate is not None and amount is not None and item.taxable_amount is not None:
                expected = item.taxable_amount * rate / 100
                if abs(expected - amount) > TOLERANCE:
                    issue(
                        "warning",
                        prefix + "_amount",
                        f"Item {index + 1} {prefix.upper()} amount differs from taxable value × rate. Check the printed bill.",
                        index,
                    )
        if item.discount_1 is not None or item.discount_2 is not None:
            issue("warning", "discount_1", f"Confirm discount meaning on item {index + 1}.", index)
    fields = [
        ("taxable_amount", "taxable_total", "Taxable"),
        ("sgst_amount", "sgst_total", "SGST"),
        ("cgst_amount", "cgst_total", "CGST"),
        ("igst_amount", "igst_total", "IGST"),
        ("cess_amount", "cess_total", "Cess"),
    ]
    for item_field, total_field, label in fields:
        entries = [getattr(item, item_field) for item in invoice.items]
        printed = getattr(invoice, total_field)
        if printed is None:
            issue("warning", total_field, f"{label} total is not recorded.")
        elif entries and all(value is not None for value in entries):
            calculated = sum(entries, Decimal(0))
            if abs(calculated - printed) > TOLERANCE:
                issue(
                    "error",
                    total_field,
                    f"{label} rows total {calculated:.2f}; recorded total is {printed:.2f}.",
                )
        elif any(value is None for value in entries):
            issue("warning", total_field, f"Some item-level {label} values are missing.")
    tax_values = [
        invoice.taxable_total,
        invoice.sgst_total,
        invoice.cgst_total,
        invoice.igst_total,
        invoice.cess_total,
    ]
    if invoice.grand_total is not None and all(value is not None for value in tax_values):
        calculated = sum(tax_values, Decimal(0)) + (invoice.round_off or Decimal(0))
        if abs(calculated - invoice.grand_total) > TOLERANCE:
            issue(
                "error",
                "grand_total",
                f"Totals plus round-off give {calculated:.2f}; grand total is {invoice.grand_total:.2f}.",
            )
    else:
        issue("warning", "grand_total", "Complete all tax totals to reconcile the grand total.")
    if duplicate_ids:
        issue(
            "warning",
            "bill_number",
            "Another saved bill has this supplier and bill number. Check for duplicates.",
        )
    errors = sum(item["level"] == "error" for item in issues)
    warnings = len(issues) - errors
    return {"issues": issues, "errors": errors, "warnings": warnings, "can_approve": errors == 0}
