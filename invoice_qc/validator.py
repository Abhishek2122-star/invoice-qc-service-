from collections import Counter
from datetime import date
from typing import List, Dict, Tuple

from .models import (
    Invoice,
    InvoiceValidationResult,
    ValidationSummary,
)


def _check_completeness(invoice: Invoice) -> List[str]:
    errors: List[str] = []
    if not invoice.invoice_number:
        errors.append("missing_field: invoice_number")
    if not invoice.invoice_date:
        errors.append("missing_field: invoice_date")
    if not invoice.seller_name:
        errors.append("missing_field: seller_name")
    if not invoice.buyer_name:
        errors.append("missing_field: buyer_name")
    return errors


def _check_format_and_ranges(invoice: Invoice) -> List[str]:
    errors: List[str] = []

    # date range
    min_date = date(2000, 1, 1)
    max_date = date(2100, 1, 1)
    if not (min_date <= invoice.invoice_date <= max_date):
        errors.append("format_error: invoice_date_out_of_range")
    if invoice.due_date is not None and not (min_date <= invoice.due_date <= max_date):
        errors.append("format_error: due_date_out_of_range")

    # currency
    allowed_currencies = {"INR", "EUR", "USD", "GBP"}
    if invoice.currency.upper() not in allowed_currencies:
        errors.append("format_error: currency_invalid")

    # non-negative totals
    if invoice.net_total < 0:
        errors.append("format_error: net_total_negative")
    if invoice.tax_amount < 0:
        errors.append("format_error: tax_amount_negative")
    if invoice.gross_total < 0:
        errors.append("format_error: gross_total_negative")

    for idx, item in enumerate(invoice.line_items):
        if item.quantity < 0:
            errors.append(f"format_error: line_{idx}_quantity_negative")
        if item.unit_price < 0:
            errors.append(f"format_error: line_{idx}_unit_price_negative")
        if item.line_total < 0:
            errors.append(f"format_error: line_{idx}_line_total_negative")

    return errors


def _check_business_rules(invoice: Invoice) -> List[str]:
    errors: List[str] = []
    tolerance = 0.05

    # sum line totals ≈ net total
    if invoice.line_items:
        sum_lines = sum(li.line_total for li in invoice.line_items)
        if abs(sum_lines - invoice.net_total) > tolerance:
            errors.append("business_rule_failed: line_items_net_mismatch")

    # net_total + tax ≈ gross_total
    if abs((invoice.net_total + invoice.tax_amount) - invoice.gross_total) > tolerance:
        errors.append("business_rule_failed: totals_mismatch")

    # due_date >= invoice_date
    if invoice.due_date and invoice.due_date < invoice.invoice_date:
        errors.append("business_rule_failed: due_before_invoice_date")

    return errors


def validate_invoices(
    invoices: List[Invoice],
) -> Tuple[List[InvoiceValidationResult], ValidationSummary]:
    results: List[InvoiceValidationResult] = []
    error_counter: Counter = Counter()

    # first pass: per-invoice rules
    for inv in invoices:
        errors: List[str] = []
        errors.extend(_check_completeness(inv))
        errors.extend(_check_format_and_ranges(inv))
        errors.extend(_check_business_rules(inv))

        for e in errors:
            error_counter[e] += 1

        results.append(
            InvoiceValidationResult(
                invoice_id=inv.invoice_number,
                is_valid=len(errors) == 0,
                errors=errors,
            )
        )

    # second pass: anomaly/duplicate rule
    seen: Dict[tuple, str] = {}
    for res, inv in zip(results, invoices):
        key = (inv.seller_name.lower(), inv.invoice_number, inv.invoice_date)
        if key in seen:
            res.errors.append("anomaly: duplicate_invoice")
            res.is_valid = False
            error_counter["anomaly: duplicate_invoice"] += 1
        else:
            seen[key] = inv.invoice_number

    # summary
    total = len(results)
    invalid = sum(1 for r in results if not r.is_valid)
    valid = total - invalid

    summary = ValidationSummary(
        total_invoices=total,
        valid_invoices=valid,
        invalid_invoices=invalid,
        error_counts=dict(error_counter),
    )
    return results, summary
