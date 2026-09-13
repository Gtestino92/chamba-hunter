from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from chamba_hunter.db.connection import PROJECT_ROOT
from chamba_hunter.domain.enums import SourceType
from chamba_hunter.schemas.inputs import CompanySeedInput


DEFAULT_REGISTRY_PATH = (
    PROJECT_ROOT
    / "data"
    / "latam_enterprise_companies.json"
)


@dataclass(frozen=True, slots=True)
class LatamEnterpriseRegistryEntry:
    seed: CompanySeedInput
    sector: str | None = None


@dataclass(frozen=True, slots=True)
class LatamEnterpriseRegistry:
    schema_version: int
    entries: tuple[
        LatamEnterpriseRegistryEntry,
        ...,
    ]


REQUIRED_ENTRY_FIELDS = frozenset(
    {
        "name",
        "country",
        "website_url",
        "careers_url",
        "external_id",
        "source_url",
    }
)

OPTIONAL_ENTRY_FIELDS = frozenset(
    {
        "sector",
    }
)

ALLOWED_ENTRY_FIELDS = (
    REQUIRED_ENTRY_FIELDS
    | OPTIONAL_ENTRY_FIELDS
)


def load_latam_enterprise_registry(
    path: Path | str = DEFAULT_REGISTRY_PATH,
) -> LatamEnterpriseRegistry:
    registry_path = Path(path)

    try:
        raw = json.loads(
            registry_path.read_text(
                encoding="utf-8"
            )
        )
    except json.JSONDecodeError as exc:
        raise ValueError(
            "LATAM enterprise registry is "
            f"not valid JSON: {registry_path}"
        ) from exc

    if not isinstance(raw, dict):
        raise ValueError(
            "LATAM enterprise registry must "
            "be a JSON object."
        )

    schema_version = raw.get(
        "schema_version"
    )

    if schema_version != 1:
        raise ValueError(
            "LATAM enterprise registry "
            "schema_version must be 1."
        )

    raw_entries = raw.get("entries")

    if not isinstance(raw_entries, list):
        raise ValueError(
            "LATAM enterprise registry "
            "entries must be a list."
        )

    entries: list[
        LatamEnterpriseRegistryEntry
    ] = []

    seen_external_ids: set[str] = set()
    seen_name_country: set[
        tuple[str, str]
    ] = set()

    for index, raw_entry in enumerate(
        raw_entries,
        start=1,
    ):
        entry = _parse_entry(
            raw_entry,
            index=index,
        )

        external_id = (
            entry.seed.external_id
        )

        if external_id is None:
            raise ValueError(
                "LATAM enterprise registry "
                f"entry {index} has no "
                "external_id."
            )

        if external_id in seen_external_ids:
            raise ValueError(
                "LATAM enterprise registry "
                "has duplicate external_id: "
                f"{external_id}"
            )

        seen_external_ids.add(
            external_id
        )

        country = (
            entry.seed.country
            or ""
        ).casefold()

        name_country = (
            entry.seed.name.casefold(),
            country,
        )

        if name_country in seen_name_country:
            raise ValueError(
                "LATAM enterprise registry "
                "has duplicate name/country: "
                f"{entry.seed.name} / "
                f"{entry.seed.country}"
            )

        seen_name_country.add(
            name_country
        )

        entries.append(
            entry
        )

    return LatamEnterpriseRegistry(
        schema_version=schema_version,
        entries=tuple(entries),
    )


def _parse_entry(
    raw_entry: Any,
    *,
    index: int,
) -> LatamEnterpriseRegistryEntry:
    if not isinstance(raw_entry, dict):
        raise ValueError(
            "LATAM enterprise registry "
            f"entry {index} must be an object."
        )

    fields = set(
        raw_entry
    )

    missing = (
        REQUIRED_ENTRY_FIELDS
        - fields
    )

    if missing:
        raise ValueError(
            "LATAM enterprise registry "
            f"entry {index} is missing "
            f"fields: {', '.join(sorted(missing))}"
        )

    unknown = fields - ALLOWED_ENTRY_FIELDS

    if unknown:
        raise ValueError(
            "LATAM enterprise registry "
            f"entry {index} has unknown "
            f"fields: {', '.join(sorted(unknown))}"
        )

    sector = raw_entry.get(
        "sector"
    )

    if (
        sector is not None
        and not isinstance(sector, str)
    ):
        raise ValueError(
            "LATAM enterprise registry "
            f"entry {index} sector must "
            "be a string or null."
        )

    try:
        seed = CompanySeedInput(
            name=raw_entry["name"],
            country=raw_entry["country"],
            website_url=(
                raw_entry["website_url"]
            ),
            careers_url=(
                raw_entry["careers_url"]
            ),
            source_type=(
                SourceType
                .LATAM_ENTERPRISE
            ),
            external_id=(
                raw_entry["external_id"]
            ),
            source_url=(
                raw_entry["source_url"]
            ),
        )
    except ValidationError as exc:
        raise ValueError(
            "LATAM enterprise registry "
            f"entry {index} is invalid: "
            f"{exc}"
        ) from exc

    return LatamEnterpriseRegistryEntry(
        seed=seed,
        sector=sector,
    )
