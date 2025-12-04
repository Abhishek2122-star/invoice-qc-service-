from typing import List

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .models import Invoice, ValidationResponse
from .validator import validate_invoices

app = FastAPI(
    title="Invoice QC Service",
    version="0.1.0",
    description="Invoice extraction & validation API",
)

# Allow local dev frontends, etc.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/validate-json", response_model=ValidationResponse)
def validate_json(invoices: List[Invoice]):
    results, summary = validate_invoices(invoices)
    return ValidationResponse(summary=summary, results=results)
