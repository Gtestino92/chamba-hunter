import csv
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from chamba_hunter.schemas.inputs import CompanySeedInput
from chamba_hunter.services.company_import_service import (
    CompanyImportService,
)


CSV_FIELDS = {
    "name",
    "website_url",
    "country",
    "source_type",
    "external_id",
    "source_url",
    "notes",
}


@dataclass(frozen=True, slots=True)
class CsvImportError:
    row_number: int
    message: str


@dataclass(slots=True)
class CsvImportSummary:
    total: int = 0
    created: int = 0
    existing: int = 0
    invalid: int = 0

    errors: list[CsvImportError] = field(default_factory=list)


def import_companies_csv(
    path: Path,
    service: CompanyImportService,
) -> CsvImportSummary:
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")

    summary = CsvImportSummary()

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        reader = csv.DictReader(file)

        if reader.fieldnames is None:
            raise ValueError("CSV does not contain a header.")

        fieldnames = {
            name.strip()
            for name in reader.fieldnames
            if name is not None
        }

        if "name" not in fieldnames:
            raise ValueError(
                "CSV must contain a 'name' column."
            )

        unknown_fields = fieldnames - CSV_FIELDS

        if unknown_fields:
            raise ValueError(
                "Unknown CSV columns: "
                + ", ".join(sorted(unknown_fields))
            )

        for row_number, row in enumerate(reader, start=2):
            summary.total += 1

            payload = {
                key: value
                for key, value in row.items()
                if key is not None
                and value is not None
                and value.strip()
            }

            try:
                seed = CompanySeedInput.model_validate(payload)

                result = service.import_seed(seed)

                if result.created:
                    summary.created += 1
                else:
                    summary.existing += 1

            except (ValidationError, ValueError) as exc:
                summary.invalid += 1

                summary.errors.append(
                    CsvImportError(
                        row_number=row_number,
                        message=str(exc),
                    )
                )

    return summary