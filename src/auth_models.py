"""
Request models for the open-source broker alerts API.
"""
from typing import List, Optional

from pydantic import BaseModel, Field


class WebhookCreate(BaseModel):
    url: str = Field(..., max_length=500)
    name: str = Field(..., min_length=2, max_length=100)
    profile_name: str = Field("broker_alerts_v1", max_length=100)
    site_keys: Optional[List[str]] = None
    site_filter: Optional[str] = Field(None, max_length=50)
    type_filter: Optional[str] = Field(None, max_length=50)
    category_filter: Optional[str] = Field(None, max_length=50)
    confidence_filter: str = Field("verified", pattern="^(verified|likely|degraded)$")
    include_degraded: bool = False
    retry_count: int = Field(3, ge=0, le=10)
    pause_on_failure_threshold: int = Field(5, ge=0, le=50)
    timeout_seconds: int = Field(30, ge=1, le=120)
    secret: Optional[str] = Field(None, max_length=100)


class WebhookUpdate(BaseModel):
    url: Optional[str] = Field(None, max_length=500)
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    profile_name: Optional[str] = Field(None, max_length=100)
    site_keys: Optional[List[str]] = None
    site_filter: Optional[str] = Field(None, max_length=50)
    type_filter: Optional[str] = Field(None, max_length=50)
    category_filter: Optional[str] = Field(None, max_length=50)
    confidence_filter: Optional[str] = Field(None, pattern="^(verified|likely|degraded)$")
    include_degraded: Optional[bool] = None
    retry_count: Optional[int] = Field(None, ge=0, le=10)
    pause_on_failure_threshold: Optional[int] = Field(None, ge=0, le=50)
    timeout_seconds: Optional[int] = Field(None, ge=1, le=120)
    is_active: Optional[bool] = None
    secret: Optional[str] = Field(None, max_length=100)


class SourceSubscriptionUpdate(BaseModel):
    profile_name: str = Field("broker_alerts_v1", max_length=100)
    site_keys: List[str] = Field(default_factory=list)


class WebhookReplayRequest(BaseModel):
    since: Optional[str] = None
    until: Optional[str] = None
    limit: int = Field(50, ge=1, le=500)
    force: bool = False
    dry_run: bool = False
