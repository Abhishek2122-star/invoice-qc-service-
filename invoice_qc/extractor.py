import json
import os
from datetime import date
from typing import List, Dict, Any, Optional

import pdfplumber

from .models import Invoice, LineItem
from .utils import (
    clean_text,
    find_first_match,
    parse_date,
    parse_float_safe,
)


def extract_text_from_pdf(path: str) -> str:
    with pdfplumber.open(path) as pdf:
        pages_text = []
        for page in pdf.pages:
            pages_text.append(page.extract_text() or "")
    return clean_text("\n".join(pages_text))


def extract_invoice_number(text: str) -> Optional[str]:
    patterns = [
        r"(invoice\s*(no\.?|number|#)\s*[:\-]?\s*)(\S+)",
    ]
    match = find_first_match(patterns, text, flags=re.IGNORECASE)
    if match:
        return match.group(3).strip()
    return None


def extract_dates(text: str) -> (Optional[date], Optional[date]):
    import re

    invoice_date = None
    due_date = None

    # Invoice date
    inv_patterns = [
        r"(invoice\s*date\s*[:\-]?\s*)([0-9./\-\sA-Za-z]+)",
        r"(date\s*[:\-]?\s*)([0-9./\-\sA-Za-z]+)",
    ]
    match = find_first_match(inv_patterns, text, flags=re.IGNORECASE)
    if match:
        dt = parse_date(match.group(2))
        if dt:
            invoice_date = dt.date()

    # Due date
    due_patterns = [
        r"(due\s*date\s*[:\-]?\s*)([0-9./\-\sA-Za-z]+)",
    ]
    match = find_first_match(due_patterns, text, flags=re.IGNORECASE)
    if match:
        dt = parse_date(match.group(2))
        if dt:
            due_date = dt.date()

    return invoice_date, due_date


def extract_currency(text: str) -> str:
    import re

    match = re.search(r"\b(INR|EUR|USD|GBP)\b", text, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    # default
    return "INR"


def extract_parties(text: str) -> (Optional[str], Optional[str], Optional[str], Optional[str], Optional[str], Optional[str]):
    """
    Very simple heuristics:
    - Find 'Seller'/'Supplier' block.
    - Find 'Buyer'/'Customer' block.
    """
    import re

    seller_name = buyer_name = None
    seller_address = buyer_address = None
    seller_tax_id = buyer_tax_id = None

    lines = text.splitlines()

    def grab_block(start_idx: int) -> str:
        block = []
        for i in range(start_idx, min(start_idx + 4, len(lines))):
            if lines[i].strip():
                block.append(lines[i].strip())
        return " ".join(block)

    # seller
    for i, line in enumerate(lines):
        if re.search(r"\b(seller|supplier)\b", line, re.IGNORECASE):
            block = grab_block(i + 1)
            if block:
                seller_name = block.split(",")[0]
                seller_address = block
            break

    # buyer
    for i, line in enumerate(lines):
        if re.search(r"\b(buyer|customer|bill to|ship to)\b", line, re.IGNORECASE):
            block = grab_block(i + 1)
            if block:
                buyer_name = block.split(",")[0]
                buyer_address = block
            break

    # tax ids
    tax_patterns = [
        r"(GSTIN|VAT\s*ID|Tax\s*ID)\s*[:\-]?\s*(\S+)",
    ]
    for line in lines:
        m = re.search(tax_patterns[0], line, re.IGNORECASE)
        if m:
            # naive: first occurrence -> seller, second -> buyer
            if not seller_tax_id:
                seller_tax_id = m.group(2)
            elif not buyer_tax_id:
                buyer_tax_id = m.group(2)
                break

    return (
        seller_name,
        seller_address,
        seller_tax_id,
        buyer_name,
        buyer_address,
        buyer_tax_id,
    )


def extract_totals(text: str) -> (Optional[float], Optional[float], Optional[float]):
    import re

    net_total = tax_amount = gross_total = None

    lines = text.splitlines()
    for line in lines:
        l = line.lower()

        if "net total" in l or "subtotal" in l:
            m = re.search(r"([0-9.,]+)", line)
            if m:
                net_total = parse_float_safe(m.group(1))

        if "tax" in l or "vat" in l:
            m = re.search(r"([0-9.,]+)", line)
            if m:
                tax_amount = parse_float_safe(m.group(1))

        if "total" in l and ("grand" in l or "amount payable" in l or "invoice total" in l or "total" == l.strip()):
            m = re.search(r"([0-9.,]+)", line)
            if m:
                gross_total = parse_float_safe(m.group(1))

    return net_total, tax_amount, gross_total


def extract_payment_terms(text: str) -> Optional[str]:
    import re

    patterns = [
        r"(payment\s*terms\s*[:\-]?\s*)(.+)",
        r"(terms\s*[:\-]?\s*)(.+)",
    ]
    match = find_first_match(patterns, text, flags=re.IGNORECASE)
    if match:
        return match.group(2).strip()
    return None


def extract_line_items(text: str) -> List[LineItem]:
    """
    Very simple heuristic: look for a header line containing 'description' and 'qty' etc.
    Then parse subsequent lines until a line containing 'total' or 'subtotal'.
    """
    import re

    lines = text.splitlines()
    header_index = None

    for i, line in enumerate(lines):
        l = line.lower()
        if "description" in l and ("qty" in l or "quantity" in l):
            header_index = i
            break

    if header_index is None:
        return []

    items: List[LineItem] = []

    for line in lines[header_index + 1 :]:
        l = line.lower()
        if "subtotal" in l or "net total" in l or "total" in l:
            break

        # Split by multiple spaces
        parts = re.split(r"\s{2,}", line.strip())
        if len(parts) < 3:
            continue

        # Heuristic: description = first, qty = second, unit_price = third, total = last
        description = parts[0]
        qty = parse_float_safe(parts[1]) or 0.0
        unit = parse_float_safe(parts[2]) or 0.0
        total = parse_float_safe(parts[-1]) or (qty * unit)

        if description:
            items.append(
                LineItem(
                    description=description,
                    quantity=qty,
                    unit_price=unit,
                    line_total=total,
                )
            )

    return items


def extract_invoice_from_pdf(path: str) -> Invoice:
    text = extract_text_from_pdf(path)
    currency = extract_currency(text)
    inv_date, due_date = extract_dates(text)
    (
        seller_name,
        seller_address,
        seller_tax_id,
        buyer_name,
        buyer_address,
        buyer_tax_id,
    ) = extract_parties(text)
    net_total, tax_amount, gross_total = extract_totals(text)
    payment_terms = extract_payment_terms(text)
    line_items = extract_line_items(text)
    invoice_number = extract_invoice_number(text) or os.path.basename(path)

    # Fallbacks / defaults
    if inv_date is None:
        inv_date = date.today()
    if net_total is None:
        # approximate from items
        net_total = sum(li.line_total for li in line_items) if line_items else 0.0
    if tax_amount is None:
        tax_amount = 0.0
    if gross_total is None:
        gross_total = (net_total or 0.0) + (tax_amount or 0.0)

    return Invoice(
        invoice_number=invoice_number,
        invoice_date=inv_date,
        due_date=due_date,
        seller_name=seller_name or "UNKNOWN_SELLER",
        seller_address=seller_address,
        seller_tax_id=seller_tax_id,
        buyer_name=buyer_name or "UNKNOWN_BUYER",
        buyer_address=buyer_address,
        buyer_tax_id=buyer_tax_id,
        currency=currency,
        net_total=net_total,
        tax_amount=tax_amount,
        gross_total=gross_total,
        payment_terms=payment_terms,
        line_items=line_items,
    )


def extract_from_dir(pdf_dir: str) -> List[Dict[str, Any]]:
    invoices: List[Dict[str, Any]] = []
    for fname in os.listdir(pdf_dir):
        if not fname.lower().endswith(".pdf"):
            continue
        path = os.path.join(pdf_dir, fname)
        invoice = extract_invoice_from_pdf(path)
        invoices.append(invoice.dict())
    return invoices


def write_invoices_to_json(invoices: List[Dict[str, Any]], output_path: str) -> None:
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(invoices, f, indent=2, default=str)
