"""Database models."""
from app.models.base import Base, TimestampMixin
from app.models.story import Story
from app.models.source import Source
from app.models.user import User, UserRole
from app.models.disaster import (
    DisasterIncident,
    DisasterAlert,
    HazardType,
    AlertType,
    DisasterSeverity,
    BIPAD_HAZARD_MAP,
)
from app.models.river import RiverStation, RiverReading, RiverStatus, RiverTrend
from app.models.weather import WeatherForecast
from app.models.announcement import GovtAnnouncement, GOVT_SOURCES
from app.models.procurement import GovtContract
from app.models.procurement_company_link import ProcurementCompanyLink
from app.models.company import (
    CompanyRegistration,
    CompanyDirector,
    IRDEnrichment,
    AnalystPhoneClusterGroup,
)
from app.models.market_data import MarketData, MarketDataType, MARKET_SOURCES
from app.models.election import (
    Election,
    Constituency,
    Candidate,
    UserConstituencyWatchlist,
    ElectionType,
    ElectionStatus,
    ConstituencyStatus,
    AlertLevel,
)

# Political entity models
from app.models.political_entity import (
    PoliticalEntity,
    EntityType,
    EntityTrend,
)
from app.models.curfew_alert import CurfewAlert
from app.models.tweet import Tweet, TwitterAccount, TwitterQuery
from app.models.tweet_cluster import TweetCluster

# Parliament models (MP Performance Index)
from app.models.parliament import (
    MPPerformance,
    ParliamentBill,
    BillSponsor,
    ParliamentCommittee,
    CommitteeMembership,
    ParliamentQuestion,
    SessionAttendance,
    Chamber,
    ElectionTypeMP,
    BillType,
    BillStatus,
    CommitteeType,
    CommitteeRole,
    QuestionType,
    PerformanceTier,
)

# Ministerial position models (Executive branch tracking)
from app.models.ministerial_position import (
    MinisterialPosition,
    PositionType,
)

from app.models.notification import UserNotification, NotificationType
from app.models.election_sync_run import ElectionSyncRun

# Situation briefs
from app.models.situation_brief import (
    SituationBrief,
    ProvinceSitrep,
    FakeNewsFlag,
)

# Province Anomaly Agent
from app.models.province_anomaly import (
    ProvinceAnomalyRun,
    ProvinceAnomaly,
)

# Email OTP (signup verification)
from app.models.email_otp import EmailOTP

# Live election results (ECN result.election.gov.np)
from app.models.election_result import ElectionCandidate, ElectionPartySummary, ElectionScrapeLog

# Promise tracker
from app.models.promise import Promise

from app.models.aviation import AircraftPosition

__all__ = [
    "Base",
    "TimestampMixin",
    "Story",
    "Source",
    "User",
    "UserRole",
    # Disaster models
    "DisasterIncident",
    "DisasterAlert",
    "HazardType",
    "AlertType",
    "DisasterSeverity",
    "BIPAD_HAZARD_MAP",
    # River models
    "RiverStation",
    "RiverReading",
    "RiverStatus",
    "RiverTrend",
    # Weather models
    "WeatherForecast",
    # Government announcement models
    "GovtAnnouncement",
    "GOVT_SOURCES",
    # Government procurement models
    "GovtContract",
    "ProcurementCompanyLink",
    # Company registration models
    "CompanyRegistration",
    "CompanyDirector",
    "IRDEnrichment",
    "AnalystPhoneClusterGroup",
    # Market data models
    "MarketData",
    "MarketDataType",
    "MARKET_SOURCES",
    # Election models
    "Election",
    "Constituency",
    "Candidate",
    "UserConstituencyWatchlist",
    "ElectionType",
    "ElectionStatus",
    "ConstituencyStatus",
    "AlertLevel",
    # Political entity models
    "PoliticalEntity",
    "EntityType",
    "EntityTrend",
    "CurfewAlert",
    "Tweet",
    "TwitterAccount",
    "TwitterQuery",
    "TweetCluster",
    # Parliament models (MP Performance Index)
    "MPPerformance",
    "ParliamentBill",
    "BillSponsor",
    "ParliamentCommittee",
    "CommitteeMembership",
    "ParliamentQuestion",
    "SessionAttendance",
    "Chamber",
    "ElectionTypeMP",
    "BillType",
    "BillStatus",
    "CommitteeType",
    "CommitteeRole",
    "QuestionType",
    "PerformanceTier",
    # Ministerial position models (Executive branch tracking)
    "MinisterialPosition",
    "PositionType",
    "UserNotification",
    "NotificationType",
    "ElectionSyncRun",
    # Situation briefs
    "SituationBrief",
    "ProvinceSitrep",
    "FakeNewsFlag",
    # Province Anomaly Agent
    "ProvinceAnomalyRun",
    "ProvinceAnomaly",
    # Email OTP
    "EmailOTP",
    # Live election results
    "ElectionCandidate",
    "ElectionPartySummary",
    "ElectionScrapeLog",
    # Aviation
    "AircraftPosition",
]
