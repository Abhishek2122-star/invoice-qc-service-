from datetime import date
from typing import List, Optional, Dict

from pydantic import BaseModel, Field, validator


class LineItem(BaseModel):
    description: str = Field(..., description="Line item description")
    quantity: float = Field(..., ge=0, description="Quantity of items")
    unit_price: float = Field(..., ge=0, description="Price per unit")
    line_total: float = Field(..., ge=0, description="Total for this line")

    @validator("line_total", always=True)
    def validate_line_total(cls, v, values):
        # Allow some tolerance due to rounding
        qty = values.get("quantity")
        price = values.get("unit_price")
        if qty is not None and price is not None:
            expected = qty * price
            if v is None:
                return expected
            if abs(expected - v) > 0.05:
                # We don't raise, validator will catch consistency separately.
                return v
        return v


class Invoice(BaseModel):
    invoice_number: str
    invoice_date: date
    due_date: Optional[date] = None

    seller_name: str
    seller_address: Optional[str] = None
    seller_tax_id: Optional[str] = None

    buyer_name: str
    buyer_address: Optional[str] = None
    buyer_tax_id: Optional[str] = None

    currency: str = "INR"
    net_total: float
    tax_amount: float
    gross_total: float

    payment_terms: Optional[str] = None

    line_items: List[LineItem] = Field(default_factory=list)

    @validator("currency")
    def validate_currency(cls, v: str) -> str:
        allowed = {"INR", "EUR", "USD", "GBP"}
        v = v.upper().strip()
        if v not in allowed:
            # Let validation core handle as rule; we just normalize.
            return v
        return v


class InvoiceValidationResult(BaseModel):
    invoice_id: str
    is_valid: bool
    errors: List[str]


class ValidationSummary(BaseModel):
    total_invoices: int
    valid_invoices: int
    invalid_invoices: int
    error_counts: Dict[str, int]


class ValidationResponse(BaseModel):
    summary: ValidationSummary
    results: List[InvoiceValidationResult]
