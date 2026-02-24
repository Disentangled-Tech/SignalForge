"""Company schemas for request/response validation."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class CompanySource(str, Enum):
    """How this company was sourced."""

    manual = "manual"
    referral = "referral"
    research = "research"


class CompanyCreate(BaseModel):
    """Schema for creating a new company."""

    company_name: str = Field(..., min_length=1, max_length=255)
    website_url: str | None = Field(None, max_length=2048)
    founder_name: str | None = Field(None, max_length=255)
    founder_linkedin_url: str | None = Field(None, max_length=2048)
    company_linkedin_url: str | None = Field(None, max_length=2048)
    notes: str | None = None
    source: CompanySource = CompanySource.manual
    target_profile_match: str | None = None


class CompanyUpdate(BaseModel):
    """Schema for updating a company. All fields optional (issue #50)."""

    company_name: str | None = Field(None, min_length=1, max_length=255)
    website_url: str | None = Field(None, max_length=2048)
    founder_name: str | None = Field(None, max_length=255)
    founder_linkedin_url: str | None = Field(None, max_length=2048)
    company_linkedin_url: str | None = Field(None, max_length=2048)
    notes: str | None = None
    source: CompanySource | None = None
    target_profile_match: str | None = None
    current_stage: str | None = Field(None, max_length=64)


class CompanyRead(BaseModel):
    """Schema for reading a company (response)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    company_name: str
    domain: str | None = None
    website_url: str | None = None
    founder_name: str | None = None
    founder_linkedin_url: str | None = None
    company_linkedin_url: str | None = None
    notes: str | None = None
    source: CompanySource | None = None
    target_profile_match: str | None = None
    cto_need_score: int | None = None
    current_stage: str | None = None
    created_at: datetime
    updated_at: datetime | None = None
    last_scan_at: datetime | None = None


class CompanyList(BaseModel):
    """Paginated list of companies."""

    items: list[CompanyRead]
    total: int
    page: int = 1
    page_size: int = 20


class BulkImportRow(BaseModel):
    """Result for a single row in a bulk import."""

    row: int
    company_name: str
    status: str  # "created", "duplicate", "error"
    detail: str | None = None


class BulkImportResponse(BaseModel):
    """Summary response for a bulk import operation."""

    total: int
    created: int
    duplicates: int
    errors: int
    rows: list[BulkImportRow]

