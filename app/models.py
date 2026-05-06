import enum
from datetime import datetime, time
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, Date, Time,
    Text, ForeignKey, Enum, JSON, Index, UniqueConstraint, func
)
from sqlalchemy.orm import relationship
from app.database import Base


# ─────────────────────────────────────────────
#  Enums
# ─────────────────────────────────────────────

class UserRole(str, enum.Enum):
    PATIENT = "patient"
    DOCTOR  = "doctor"
    ADMIN   = "admin"


class Gender(str, enum.Enum):
    MALE    = "male"
    FEMALE  = "female"
    OTHER   = "other"


class AppointmentStatus(str, enum.Enum):
    PENDING   = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    NO_SHOW   = "no_show"


class ConsultationType(str, enum.Enum):
    IN_PERSON = "in_person"
    VIDEO     = "video"
    PHONE     = "phone"


class SlotStatus(str, enum.Enum):
    AVAILABLE = "available"
    BOOKED    = "booked"
    BLOCKED   = "blocked"


# ─────────────────────────────────────────────
#  User
# ─────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id             = Column(Integer, primary_key=True, index=True)
    email          = Column(String(255), unique=True, index=True, nullable=False)
    phone          = Column(String(20), unique=True, index=True, nullable=True)
    hashed_password = Column(String(255), nullable=False)
    full_name      = Column(String(255), nullable=False)
    role           = Column(Enum(UserRole), default=UserRole.PATIENT, nullable=False)
    is_active      = Column(Boolean, default=True)
    is_verified    = Column(Boolean, default=False)
    created_at     = Column(DateTime, default=datetime.utcnow)
    updated_at     = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    patient_profile  = relationship("PatientProfile", back_populates="user", uselist=False)
    doctor_profile   = relationship("DoctorProfile",  back_populates="user", uselist=False)
    appointments     = relationship("Appointment", foreign_keys="Appointment.patient_id", back_populates="patient")
    reviews_given    = relationship("Review", foreign_keys="Review.patient_id", back_populates="patient")
    notifications    = relationship("Notification", back_populates="user")


# ─────────────────────────────────────────────
#  Patient Profile
# ─────────────────────────────────────────────

class PatientProfile(Base):
    __tablename__ = "patient_profiles"

    id          = Column(Integer, primary_key=True, index=True)
    user_id     = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    date_of_birth = Column(Date, nullable=True)
    gender      = Column(Enum(Gender), nullable=True)
    blood_group = Column(String(5), nullable=True)
    address     = Column(Text, nullable=True)
    city        = Column(String(100), nullable=True)
    state       = Column(String(100), nullable=True)
    pincode     = Column(String(10), nullable=True)
    medical_history = Column(JSON, default=list)   # list of past conditions
    allergies   = Column(JSON, default=list)
    avatar_url  = Column(String(500), nullable=True)

    user = relationship("User", back_populates="patient_profile")


# ─────────────────────────────────────────────
#  Specialization (lookup table)
# ─────────────────────────────────────────────

class Specialization(Base):
    __tablename__ = "specializations"

    id          = Column(Integer, primary_key=True, index=True)
    name        = Column(String(200), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    icon_url    = Column(String(500), nullable=True)

    doctors = relationship("DoctorProfile", back_populates="specialization")


# ─────────────────────────────────────────────
#  Doctor Profile
# ─────────────────────────────────────────────

class DoctorProfile(Base):
    __tablename__ = "doctor_profiles"

    id               = Column(Integer, primary_key=True, index=True)
    user_id          = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    specialization_id = Column(Integer, ForeignKey("specializations.id"), nullable=False)

    # Identity
    registration_number = Column(String(100), unique=True, nullable=False)
    gender           = Column(Enum(Gender), nullable=True)
    date_of_birth    = Column(Date, nullable=True)
    avatar_url       = Column(String(500), nullable=True)
    bio              = Column(Text, nullable=True)
    languages        = Column(JSON, default=list)   # ["Hindi", "English"]

    # Professional
    experience_years = Column(Integer, default=0)
    qualifications   = Column(JSON, default=list)   # [{"degree":"MBBS","college":"AIIMS","year":2015}]
    awards           = Column(JSON, default=list)
    publications     = Column(JSON, default=list)

    # Fees
    consultation_fee = Column(Float, nullable=False, default=500.0)
    video_fee        = Column(Float, nullable=True)
    follow_up_fee    = Column(Float, nullable=True)

    # Location
    clinic_name      = Column(String(255), nullable=True)
    clinic_address   = Column(Text, nullable=True)
    city             = Column(String(100), index=True, nullable=True)
    state            = Column(String(100), nullable=True)
    pincode          = Column(String(10), nullable=True)
    latitude         = Column(Float, nullable=True)
    longitude        = Column(Float, nullable=True)

    # Availability flags
    available_for_video   = Column(Boolean, default=False)
    available_for_home    = Column(Boolean, default=False)
    accepting_new_patients = Column(Boolean, default=True)

    # Ratings (denormalised for fast reads)
    avg_rating       = Column(Float, default=0.0)
    total_reviews    = Column(Integer, default=0)
    total_patients   = Column(Integer, default=0)

    is_verified      = Column(Boolean, default=False)
    is_featured      = Column(Boolean, default=False)
    created_at       = Column(DateTime, default=datetime.utcnow)
    updated_at       = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Full-text search vector stored as a generated column in PG
    # We maintain it manually via trigger or update call

    # Relationships
    user             = relationship("User", back_populates="doctor_profile")
    specialization   = relationship("Specialization", back_populates="doctors")
    availability     = relationship("DoctorAvailability", back_populates="doctor", cascade="all, delete-orphan")
    time_slots       = relationship("TimeSlot", back_populates="doctor", cascade="all, delete-orphan")
    appointments     = relationship("Appointment", back_populates="doctor")
    reviews          = relationship("Review", back_populates="doctor")

    __table_args__ = (
        Index("ix_doctor_city_spec", "city", "specialization_id"),
        Index("ix_doctor_rating",    "avg_rating"),
        Index("ix_doctor_fee",       "consultation_fee"),
    )


# ─────────────────────────────────────────────
#  Doctor Weekly Availability
# ─────────────────────────────────────────────

class DoctorAvailability(Base):
    __tablename__ = "doctor_availability"

    id          = Column(Integer, primary_key=True, index=True)
    doctor_id   = Column(Integer, ForeignKey("doctor_profiles.id", ondelete="CASCADE"))
    day_of_week = Column(Integer, nullable=False)   # 0=Mon … 6=Sun
    start_time  = Column(Time, nullable=False)
    end_time    = Column(Time, nullable=False)
    slot_duration_minutes = Column(Integer, default=30)
    consultation_type     = Column(Enum(ConsultationType), default=ConsultationType.IN_PERSON)
    max_patients_per_slot = Column(Integer, default=1)
    is_active   = Column(Boolean, default=True)

    doctor = relationship("DoctorProfile", back_populates="availability")

    __table_args__ = (
        UniqueConstraint("doctor_id", "day_of_week", "start_time", "consultation_type",
                         name="uq_doctor_day_time_type"),
    )


# ─────────────────────────────────────────────
#  Time Slot (concrete slots per date)
# ─────────────────────────────────────────────

class TimeSlot(Base):
    __tablename__ = "time_slots"

    id          = Column(Integer, primary_key=True, index=True)
    doctor_id   = Column(Integer, ForeignKey("doctor_profiles.id", ondelete="CASCADE"))
    slot_date   = Column(Date, nullable=False, index=True)
    start_time  = Column(Time, nullable=False)
    end_time    = Column(Time, nullable=False)
    status      = Column(Enum(SlotStatus), default=SlotStatus.AVAILABLE)
    consultation_type = Column(Enum(ConsultationType), default=ConsultationType.IN_PERSON)
    created_at  = Column(DateTime, default=datetime.utcnow)

    doctor      = relationship("DoctorProfile", back_populates="time_slots")
    appointment = relationship("Appointment", back_populates="time_slot", uselist=False)

    __table_args__ = (
        Index("ix_slot_doctor_date", "doctor_id", "slot_date"),
        UniqueConstraint("doctor_id", "slot_date", "start_time", "consultation_type",
                         name="uq_slot_doctor_date_time_type"),
    )


# ─────────────────────────────────────────────
#  Appointment
# ─────────────────────────────────────────────

class Appointment(Base):
    __tablename__ = "appointments"

    id              = Column(Integer, primary_key=True, index=True)
    patient_id      = Column(Integer, ForeignKey("users.id"), nullable=False)
    doctor_id       = Column(Integer, ForeignKey("doctor_profiles.id"), nullable=False)
    time_slot_id    = Column(Integer, ForeignKey("time_slots.id"), nullable=False, unique=True)

    status          = Column(Enum(AppointmentStatus), default=AppointmentStatus.PENDING)
    consultation_type = Column(Enum(ConsultationType), default=ConsultationType.IN_PERSON)

    # Patient-filled details
    symptoms        = Column(Text, nullable=True)
    notes           = Column(Text, nullable=True)

    # Doctor-filled details
    prescription    = Column(Text, nullable=True)
    diagnosis       = Column(Text, nullable=True)
    follow_up_date  = Column(Date, nullable=True)

    # Video call
    video_call_link = Column(String(500), nullable=True)

    # Fees
    fee_paid        = Column(Float, nullable=True)
    payment_status  = Column(String(50), default="pending")   # pending / paid / refunded
    payment_id      = Column(String(200), nullable=True)

    # Cancellation
    cancelled_by    = Column(String(50), nullable=True)        # patient / doctor
    cancellation_reason = Column(Text, nullable=True)
    cancelled_at    = Column(DateTime, nullable=True)

    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    patient    = relationship("User",          foreign_keys=[patient_id], back_populates="appointments")
    doctor     = relationship("DoctorProfile", back_populates="appointments")
    time_slot  = relationship("TimeSlot",      back_populates="appointment")
    review     = relationship("Review",        back_populates="appointment", uselist=False)

    __table_args__ = (
        Index("ix_appt_patient", "patient_id"),
        Index("ix_appt_doctor",  "doctor_id"),
    )


# ─────────────────────────────────────────────
#  Review
# ─────────────────────────────────────────────

class Review(Base):
    __tablename__ = "reviews"

    id             = Column(Integer, primary_key=True, index=True)
    patient_id     = Column(Integer, ForeignKey("users.id"), nullable=False)
    doctor_id      = Column(Integer, ForeignKey("doctor_profiles.id"), nullable=False)
    appointment_id = Column(Integer, ForeignKey("appointments.id"), nullable=True, unique=True)
    rating         = Column(Float, nullable=False)          # 1-5
    comment        = Column(Text, nullable=True)
    is_anonymous   = Column(Boolean, default=False)
    is_approved    = Column(Boolean, default=True)
    created_at     = Column(DateTime, default=datetime.utcnow)

    patient     = relationship("User",          foreign_keys=[patient_id], back_populates="reviews_given")
    doctor      = relationship("DoctorProfile", back_populates="reviews")
    appointment = relationship("Appointment",   back_populates="review")

    __table_args__ = (
        UniqueConstraint("patient_id", "doctor_id", "appointment_id", name="uq_review_patient_doctor_appt"),
    )


# ─────────────────────────────────────────────
#  Notification
# ─────────────────────────────────────────────

class Notification(Base):
    __tablename__ = "notifications"

    id          = Column(Integer, primary_key=True, index=True)
    user_id     = Column(Integer, ForeignKey("users.id"), nullable=False)
    title       = Column(String(255), nullable=False)
    message     = Column(Text, nullable=False)
    notif_type  = Column(String(50), nullable=True)   # appointment_reminder, cancellation …
    is_read     = Column(Boolean, default=False)
    data        = Column(JSON, default=dict)           # extra context
    created_at  = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="notifications")

    __table_args__ = (
        Index("ix_notif_user_read", "user_id", "is_read"),
    )
