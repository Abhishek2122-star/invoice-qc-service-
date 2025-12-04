import json
import sys
from pathlib import Path
from typing import Optional, List

import typer

from .extractor import extract_from_dir, write_invoices_to_json
from .models import Invoice
from .validator import validate_invoices

app = typer.Typer(help="Invoice QC Service CLI")


@app.command()
def extract(
    pdf_dir: str = typer.Option(..., help="Directory containing invoice PDFs"),
    output: str = typer.Option(
        "extracted_invoices.json", help="Path to write extracted invoices JSON"
    ),
):
    """Extract invoices from PDFs to JSON."""
    invoices = extract_from_dir(pdf_dir)
    write_invoices_to_json(invoices, output)
    typer.echo(f"Extracted {len(invoices)} invoices to {output}")


@app.command()
def validate(
    input: str = typer.Option(..., help="Path to input invoices JSON"),
    report: str = typer.Option(
        "validation_report.json", help="Path to write validation report JSON"
    ),
    fail_on_invalid: bool = typer.Option(
        False, help="Exit with non-zero code if invalid invoices exist"
    ),
):
    """Validate invoices from JSON."""
    input_path = Path(input)
    if not input_path.exists():
        typer.echo(f"Input file not found: {input}", err=True)
        raise typer.Exit(code=1)

    with open(input_path, "r", encoding="utf-8") as f:
        raw_invoices = json.load(f)

    invoices: List[Invoice] = [Invoice.parse_obj(obj) for obj in raw_invoices]

    results, summary = validate_invoices(invoices)

    # write full report
    full_report = {
        "summary": json.loads(summary.json()),
        "results": [json.loads(r.json()) for r in results],
    }
    with open(report, "w", encoding="utf-8") as f:
        json.dump(full_report, f, indent=2, default=str)

    # print human summary
    typer.echo(f"Processed {summary.total_invoices} invoices.")
    typer.echo(f"Valid:   {summary.valid_invoices}")
    typer.echo(f"Invalid: {summary.invalid_invoices}")
    typer.echo("Top errors:")
    for err, count in summary.error_counts.items():
        typer.echo(f"  {err:40s} {count}")

    if fail_on_invalid and summary.invalid_invoices > 0:
        raise typer.Exit(code=1)


@app.command("full-run")
def full_run(
    pdf_dir: str = typer.Option(..., help="Directory containing invoice PDFs"),
    report: str = typer.Option(
        "validation_report.json", help="Path to write validation report JSON"
    ),
    temp_output: Optional[str] = typer.Option(
        None, help="Optional temp JSON file for extracted invoices"
    ),
    fail_on_invalid: bool = typer.Option(
        False, help="Exit with non-zero code if invalid invoices exist"
    ),
):
    """Extract from PDFs and then validate (end-to-end)."""
    # Extract
    invoices = extract_from_dir(pdf_dir)
    if temp_output:
        write_invoices_to_json(invoices, temp_output)
        typer.echo(f"Extracted {len(invoices)} invoices to {temp_output}")

    # Validate
    parsed_invoices: List[Invoice] = [Invoice.parse_obj(obj) for obj in invoices]
    results, summary = validate_invoices(parsed_invoices)

    full_report = {
        "summary": json.loads(summary.json()),
        "results": [json.loads(r.json()) for r in results],
    }
    with open(report, "w", encoding="utf-8") as f:
        json.dump(full_report, f, indent=2, default=str)

    typer.echo(f"[FULL RUN] Processed {summary.total_invoices} invoices.")
    typer.echo(f"Valid:   {summary.valid_invoices}")
    typer.echo(f"Invalid: {summary.invalid_invoices}")

    if fail_on_invalid and summary.invalid_invoices > 0:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
