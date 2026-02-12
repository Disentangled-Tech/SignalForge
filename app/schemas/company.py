"""Company schemas for request/response validation."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class CompanySource(str, Enum):
    """How this company was sourced."""

    manual = "manual"
    referral = "referral"
    research = "research"


class CompanyCreate(BaseModel):
    """Schema for creating a new company."""

    company_name: str = Field(..., min_length=1, max_length=255)
    website_url: Optional[str] = Field(None, max_length=2048)
    founder_name: Optional[str] = Field(None, max_length=255)
    founder_linkedin_url: Optional[str] = Field(None, max_length=2048)
    company_linkedin_url: Optional[str] = Field(None, max_length=2048)
    notes: Optional[str] = None
    source: CompanySource = CompanySource.manual
    target_profile_match: Optional[str] = None


class CompanyUpdate(BaseModel):
    """Schema for updating a company. All fields optional."""

    company_name: Optional[str] = Field(None, min_length=1, max_length=255)
    website_url: Optional[str] = Field(None, max_length=2048)
    founder_name: Optional[str] = Field(None, max_length=255)
    founder_linkedin_url: Optional[str] = Field(None, max_length=2048)
    company_linkedin_url: Optional[str] = Field(None, max_length=2048)
    notes: Optional[str] = None
    source: Optional[CompanySource] = None
    target_profile_match: Optional[str] = None


class CompanyRead(BaseModel):
    """Schema for reading a company (response)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    company_name: str
    website_url: Optional[str] = None
    founder_name: Optional[str] = None
    founder_linkedin_url: Optional[str] = None
    company_linkedin_url: Optional[str] = None
    notes: Optional[str] = None
    source: Optional[CompanySource] = None
    target_profile_match: Optional[str] = None
    cto_need_score: Optional[int] = None
    current_stage: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    last_scan_at: Optional[datetime] = None


class CompanyList(BaseModel):
    """Paginated list of companies."""

    items: list[CompanyRead]
    total: int
    page: int = 1
    page_size: int = 20

