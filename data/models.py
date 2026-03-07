from __future__ import annotations
from pydantic import BaseModel, Field, NonNegativeInt, field_validator, ConfigDict, computed_field, model_validator
from typing import Literal, Optional
from datetime import datetime
from utils.validators import validate_username, validate_password_strength, validate_movie_title, validate_release_year
from enum import Enum

ROLE = Literal["USER", "ADMIN"]
SORT_FIELD = Literal["rating", "title", "release_year", "created_at"]
SORT_ORDER = Literal["asc", "desc"]


class EnrichmentStatus(str, Enum):
    PENDING = "pending"       # rating is None, no error recorded yet
    SUCCESS = "success"       # rating is populated
    NOT_FOUND = "not_found"   # OMDb returned no match
    FAILED = "failed"         # timeout, HTTP error, etc.




class RefreshRequest(BaseModel):
    refresh_token: str

class TokenPairResponse(BaseModel):
    """Standard token response payload for OAuth2-style JWT authentication."""

    access_token: str = Field(..., description="Short-lived JWT access token (type=access).")
    refresh_token: str = Field(..., description="Long-lived JWT refresh token (type=refresh).")
    token_type: str = Field("bearer", description="Token type for Authorization header.")

class UserBase(BaseModel):
    """Base user model with minimal public information."""
    username: str = Field(
        min_length=2,
        max_length=16,
        description="Unique username for the user. ",
        examples=["johndoe", "alice_2024"],
    )

    @field_validator("username")
    @classmethod
    def validate_username_field(cls, v: str) -> str:
        return validate_username(v)

class UserCreate(UserBase):
    """
    Schema for user registration.
    
    All fields are required. Password must meet complexity requirements:
    - At least 8 characters
    - Contains uppercase letter
    - Contains lowercase letter  
    - Contains digit
    - Contains special character
    """
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "username": "johndoe",
                "password": "SecurePass123!"
            }
        }
    )


    password: str = Field(min_length=8, max_length=64)

    @field_validator('password')
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Validate password strength requirements."""
        return validate_password_strength(v)

class UserUpdate(BaseModel):
    """
    Schema for changing the user's password.

    """
    old_password: str = Field(min_length=8, max_length=64)
    new_password: str = Field(min_length=8, max_length=64)

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str, info) -> str:
        old = info.data.get("old_password")
        if old and v == old:
            raise ValueError("New password must be different from old password.")
        return validate_password_strength(v)
    
class UserPublic(UserBase):
    """
    Public user profile visible to all users.
    """

    id: int
    role: ROLE
    created_at: datetime

class UserRoleUpdate(BaseModel):
    """Schema for promoting/demoting users. Admin only."""
    role: ROLE

class UserInternal(BaseModel):
    """
    Internal user model for database operations.
    
    Contains all user data including password hash. Never exposed via API.
    """
    id: int
    username: str = Field(min_length=2, max_length=16)
    password_hash: str
    role: ROLE
    token_version: NonNegativeInt = 0
    created_at: datetime


class MovieBase(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    director: Optional[str] = Field(default=None, max_length=255)
    release_year: Optional[int] = Field(default=None, ge=0, le=9999)  # final check in validator


    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        return validate_movie_title(v)

    @field_validator("release_year")
    @classmethod
    def validate_year(cls, v: Optional[int]) -> Optional[int]:
        if v is None:
            return None
        return validate_release_year(v)


class MovieCreate(MovieBase):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {"title": "Inception", "director": "Christopher Nolan", "release_year": 2010}
        }
    )


class MovieUpdate(BaseModel):
    """
    Schema for updating a movie record.

    Fields omitted from the request body are left unchanged.
    Fields explicitly set to null clear the stored value (director and release_year only).
    title cannot be cleared — it is required on the movie record.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"title": "Inception", "director": None, "release_year": 2010}
        }
    )

    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    director: Optional[str] = Field(default=None, max_length=255)
    release_year: Optional[int] = Field(default=None, ge=1888, le=9999)

    @model_validator(mode="after")
    def validate_title_not_explicitly_null(self) -> "MovieUpdate":
        """Raise a clear error when the caller explicitly sends title=null."""
        if "title" in self.model_fields_set and self.title is None:
            raise ValueError("title cannot be set to null — it is a required field.")
        return self

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return validate_movie_title(v)

    @field_validator("release_year")
    @classmethod
    def validate_year(cls, v: Optional[int]) -> Optional[int]:
        if v is None:
            return None
        return validate_release_year(v)

    def fields_to_update(self) -> dict:
        """
        Return a dict of fields that were explicitly included in the request.

        None values for director/release_year mean 'clear this field'.
        title=None means 'not provided' (title cannot be cleared; validated above).
        """
        result = {}
        for field in ("director", "release_year"):
            if field in self.model_fields_set:
                result[field] = getattr(self, field)
        if self.title is not None:
            result["title"] = self.title
        return result


class MovieOut(MovieBase):
    id: int
    rating: Optional[float] = None
    rating_source: Optional[str] = None
    rating_updated_at: Optional[datetime] = None
    enrichment_error: Optional[str] = Field(default=None, exclude=True)  # kept internal
    created_at: datetime
    updated_at: datetime

    @computed_field
    @property
    def enrichment_status(self) -> EnrichmentStatus:
        if self.rating is not None:
            return EnrichmentStatus.SUCCESS
        if self.enrichment_error is None and self.rating_updated_at is None:
            return EnrichmentStatus.PENDING
        if self.enrichment_error == "Movie not found in OMDb.":
            return EnrichmentStatus.NOT_FOUND
        return EnrichmentStatus.FAILED