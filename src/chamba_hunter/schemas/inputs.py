from typing import Any

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator

from chamba_hunter.domain.enums import SourceType


class CompanySeedInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    name: str = Field(min_length=1)

    website_url: AnyHttpUrl | None = None
    country: str | None = None

    source_type: SourceType = SourceType.MANUAL
    external_id: str | None = None
    source_url: AnyHttpUrl | None = None

    notes: str | None = None

    @field_validator(
        "country",
        "external_id",
        "notes",
        mode="before",
    )
    @classmethod
    def blank_strings_to_none(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            return None
        return value


class SearchProfileInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    name: str = Field(min_length=1)
    description: str | None = None

    rules: dict[str, Any]

    is_active: bool = True