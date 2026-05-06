from __future__ import annotations
from datetime import date, time, datetime
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, EmailStr, Field, field_validator
from app.models import (
    UserRole, Gender, AppointmentStatus, ConsultationType, SlotStatus
)


# ─────────────────────────────────────────────
#  Auth
# ─────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    phone: Optional[str] = None
    full_name: str = Field(..., min_length=2, max_length=255)
    password: str = Field(..., min_length=8)
    role: UserRole = UserRole.PATIENT


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshTokenRequest(BaseModel):
    refresh_token: str


# ─────────────────────────────────────────────
#  User
# ─────────────────────────────────────────────

class UserOut(BaseModel):
    id: int
    email: str
    phone: Optional[str]
    full_name: str
    role: UserRole
    is_active: bool
    is_verified: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────
#  Specialization
# ─────────────────────────────────────────────

class SpecializationCreate(BaseModel):
    name: str
    description: Optional[str] = None
    icon_url: Optional[str] = None


class SpecializationOut(BaseModel):
    id: int
    name: str
    description: Optional[str]
    icon_url: Optional[str]

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────
#  Doctor Profile
# ─────────────────────────────────────────────

class DoctorProfileCreate(BaseModel):
    specialization_id: int
    registration_number: str
    gender: Optional[Gender] = None
    date_of_birth: Optional[date] = None
    bio: Optional[str] = None
    languages: List[str] = []
    experience_years: int = 0
    qualifications: List[Dict[str, Any]] = []
    consultation_fee: float = Field(..., gt=0)
    video_fee: Optional[float] = None
    follow_up_fee: Optional[float] = None
    clinic_name: Optional[str] = None
    clinic_address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    available_for_video: bool = False
    available_for_home: bool = False


class DoctorProfileUpdate(BaseModel):
    bio: Optional[str] = None
    languages: Optional[List[str]] = None
    experience_years: Optional[int] = None
    qualifications: Optional[List[Dict[str, Any]]] = None
    consultation_fee: Optional[float] = None
    video_fee: Optional[float] = None
    follow_up_fee: Optional[float] = None
    clinic_name: Optional[str] = None
    clinic_address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    available_for_video: Optional[bool] = None
    available_for_home: Optional[bool] = None
    accepting_new_patients: Optional[bool] = None


class DoctorSummary(BaseModel):
    id: int
    user_id: int
    full_name: str
    specialization: str
    experience_years: int
    consultation_fee: float
    avg_rating: float
    total_reviews: int
    city: Optional[str]
    clinic_name: Optional[str]
    avatar_url: Optional[str]
    is_verified: bool
    available_for_video: bool
    accepting_new_patients: bool

    model_config = {"from_attributes": True}


class DoctorDetail(DoctorSummary):
    registration_number: str
    gender: Optional[Gender]
    bio: Optional[str]
    languages: List[str]
    qualifications: List[Dict[str, Any]]
    awards: List[Any]
    video_fee: Optional[float]
    follow_up_fee: Optional[float]
    clinic_address: Optional[str]
    state: Optional[str]
    pincode: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    available_for_home: bool
    total_patients: int


# ─────────────────────────────────────────────
#  Availability
# ─────────────────────────────────────────────

class AvailabilityCreate(BaseModel):
    day_of_week: int = Field(..., ge=0, le=6)
    start_time: time
    end_time: time
    slot_duration_minutes: int = Field(30, ge=10, le=120)
    consultation_type: ConsultationType = ConsultationType.IN_PERSON
    max_patients_per_slot: int = Field(1, ge=1)

    @field_validator("end_time")
    @classmethod
    def end_after_start(cls, v, info):
        if "start_time" in info.data and v <= info.data["start_time"]:
            raise ValueError("end_time must be after start_time")
        return v


class AvailabilityOut(BaseModel):
    id: int
    day_of_week: int
    start_time: time
    end_time: time
    slot_duration_minutes: int
    consultation_type: ConsultationType
    max_patients_per_slot: int
    is_active: bool

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────
#  Time Slots
# ─────────────────────────────────────────────

class TimeSlotOut(BaseModel):
    id: int
    slot_date: date
    start_time: time
    end_time: time
    status: SlotStatus
    consultation_type: ConsultationType

    model_config = {"from_attributes": True}


class GenerateSlotsRequest(BaseModel):
    from_date: date
    to_date: date

    @field_validator("to_date")
    @classmethod
    def to_after_from(cls, v, info):
        if "from_date" in info.data and v < info.data["from_date"]:
            raise ValueError("to_date must be >= from_date")
        return v


# ─────────────────────────────────────────────
#  Appointment
# ─────────────────────────────────────────────

class AppointmentCreate(BaseModel):
    doctor_id: int
    time_slot_id: int
    consultation_type: ConsultationType = ConsultationType.IN_PERSON
    symptoms: Optional[str] = None
    notes: Optional[str] = None


class AppointmentUpdate(BaseModel):
    prescription: Optional[str] = None
    diagnosis: Optional[str] = None
    follow_up_date: Optional[date] = None
    status: Optional[AppointmentStatus] = None


class CancelAppointmentRequest(BaseModel):
    reason: Optional[str] = None


class AppointmentOut(BaseModel):
    id: int
    patient_id: int
    doctor_id: int
    status: AppointmentStatus
    consultation_type: ConsultationType
    symptoms: Optional[str]
    notes: Optional[str]
    prescription: Optional[str]
    diagnosis: Optional[str]
    follow_up_date: Optional[date]
    video_call_link: Optional[str]
    fee_paid: Optional[float]
    payment_status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class AppointmentDetail(AppointmentOut):
    time_slot: TimeSlotOut
    patient: UserOut
    doctor_name: Optional[str] = None
    doctor_specialization: Optional[str] = None

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────
#  Review
# ─────────────────────────────────────────────

class ReviewCreate(BaseModel):
    appointment_id: Optional[int] = None
    rating: float = Field(..., ge=1.0, le=5.0)
    comment: Optional[str] = None
    is_anonymous: bool = False


class ReviewOut(BaseModel):
    id: int
    patient_id: int
    doctor_id: int
    rating: float
    comment: Optional[str]
    is_anonymous: bool
    created_at: datetime
    patient_name: Optional[str] = None

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────
#  Search
# ─────────────────────────────────────────────

class DoctorSearchParams(BaseModel):
    q: Optional[str] = Field(None, description="Full-text search: name, specialization, clinic")
    specialization_id: Optional[int] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    radius_km: float = 10.0
    min_fee: Optional[float] = None
    max_fee: Optional[float] = None
    min_rating: Optional[float] = None
    min_experience: Optional[int] = None
    gender: Optional[Gender] = None
    available_for_video: Optional[bool] = None
    available_for_home: Optional[bool] = None
    accepting_new_patients: Optional[bool] = None
    available_on: Optional[date] = None
    language: Optional[str] = None
    is_verified: Optional[bool] = None
    sort_by: str = Field("relevance", pattern="^(relevance|rating|fee_asc|fee_desc|experience|distance)$")
    page: int = Field(1, ge=1)
    page_size: int = Field(10, ge=1, le=50)


class SearchResponse(BaseModel):
    total: int
    page: int
    page_size: int
    total_pages: int
    results: List[DoctorSummary]


# ─────────────────────────────────────────────
#  Notification
# ─────────────────────────────────────────────

class NotificationOut(BaseModel):
    id: int
    title: str
    message: str
    notif_type: Optional[str]
    is_read: bool
    data: Dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────
#  Generic
# ─────────────────────────────────────────────

class MessageResponse(BaseModel):
    message: str
    detail: Optional[Any] = None


class PaginatedResponse(BaseModel):
    total: int
    page: int
    page_size: int
    total_pages: int
    results: List[Any]
