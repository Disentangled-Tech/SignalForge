"""Pydantic schemas for request/response validation."""

from app.schemas.analysis import (
    AnalysisRecordList,
    AnalysisRecordRead,
    PainSignalItem,
    PainSignals,
)
from app.schemas.auth import LoginRequest, TokenResponse, UserRead
from app.schemas.briefing import (
    BriefingItemRead,
    BriefingResponse,
    EmergingCompanyBriefing,
)
from app.schemas.company import (
    CompanyCreate,
    CompanyList,
    CompanyRead,
    CompanySource,
    CompanyUpdate,
)
from app.schemas.ranked_companies import (
    RankedCompaniesResponse,
    RankedCompanyTop,
)
from app.schemas.settings import (
    OperatorProfileRead,
    OperatorProfileUpdate,
    SettingsRead,
    SettingsUpdate,
)
from app.schemas.evidence import EvidenceBundleRecord
from app.schemas.scout import (
    EvidenceBundle,
    EvidenceItem,
    ScoutRunInput,
    ScoutRunMetadata,
    ScoutRunResult,
)
from app.schemas.signal import RawEvent, SignalRecordList, SignalRecordRead
from app.schemas.watchlist import (
    WatchlistAddRequest,
    WatchlistItemResponse,
    WatchlistListResponse,
)

__all__ = [
    # Company
    "CompanyCreate",
    "CompanyUpdate",
    "CompanyRead",
    "CompanyList",
    "CompanySource",
    # Ranked companies
    "RankedCompanyTop",
    "RankedCompaniesResponse",
    # Evidence store
    "EvidenceBundleRecord",
    # Scout
    "EvidenceBundle",
    "EvidenceItem",
    "ScoutRunInput",
    "ScoutRunMetadata",
    "ScoutRunResult",
    # Signal
    "RawEvent",
    "SignalRecordRead",
    "SignalRecordList",
    # Analysis
    "PainSignalItem",
    "PainSignals",
    "AnalysisRecordRead",
    "AnalysisRecordList",
    # Briefing
    "BriefingItemRead",
    "BriefingResponse",
    "EmergingCompanyBriefing",
    # Auth
    "LoginRequest",
    "TokenResponse",
    "UserRead",
    # Settings
    "SettingsUpdate",
    "SettingsRead",
    "OperatorProfileUpdate",
    "OperatorProfileRead",
    # Watchlist
    "WatchlistAddRequest",
    "WatchlistItemResponse",
    "WatchlistListResponse",
]
