"""Pydantic schemas for request/response validation."""

from app.schemas.analysis import (
    AnalysisRecordList,
    AnalysisRecordRead,
    PainSignalItem,
    PainSignals,
)
from app.schemas.auth import LoginRequest, TokenResponse, UserRead
from app.schemas.briefing import BriefingItemRead, BriefingResponse
from app.schemas.company import (
    CompanyCreate,
    CompanyList,
    CompanyRead,
    CompanySource,
    CompanyUpdate,
)
from app.schemas.settings import (
    OperatorProfileRead,
    OperatorProfileUpdate,
    SettingsRead,
    SettingsUpdate,
)
from app.schemas.signal import RawEvent, SignalRecordList, SignalRecordRead

__all__ = [
    # Company
    "CompanyCreate",
    "CompanyUpdate",
    "CompanyRead",
    "CompanyList",
    "CompanySource",
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
    # Auth
    "LoginRequest",
    "TokenResponse",
    "UserRead",
    # Settings
    "SettingsUpdate",
    "SettingsRead",
    "OperatorProfileUpdate",
    "OperatorProfileRead",
]
