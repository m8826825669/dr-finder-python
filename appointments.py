from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import (
    User, DoctorProfile, Appointment, TimeSlot,
    AppointmentStatus, SlotStatus, UserRole, Review
)
from app.schemas import (
    AppointmentCreate, AppointmentUpdate, AppointmentOut,
    CancelAppointmentRequest, MessageResponse, ReviewCreate, ReviewOut,
)
from app.auth import get_current_user, get_current_doctor
from app.cache import cache_delete, cache_delete_pattern, make_slots_key

router = APIRouter(prefix="/appointments", tags=["Appointments"])


# ─────────────────────────────────────────────
#  Book Appointment
# ─────────────────────────────────────────────

@router.post("", response_model=AppointmentOut, status_code=201)
async def book_appointment(
    payload: AppointmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Book an appointment for a time slot."""
    # Fetch and lock the slot
    slot_result = await db.execute(
        select(TimeSlot).where(
            TimeSlot.id == payload.time_slot_id,
            TimeSlot.doctor_id == payload.doctor_id,
        ).with_for_update()   # row-level lock to prevent double booking
    )
    slot: TimeSlot = slot_result.scalar_one_or_none()
    if not slot:
        raise HTTPException(status_code=404, detail="Time slot not found")
    if slot.status != SlotStatus.AVAILABLE:
        raise HTTPException(status_code=409, detail="Time slot is no longer available")

    # Check doctor is accepting
    doctor = await db.get(DoctorProfile, payload.doctor_id)
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")
    if not doctor.accepting_new_patients:
        raise HTTPException(status_code=400, detail="Doctor is not accepting new patients")

    # Check patient has no conflicting appointment on same slot
    conflict = await db.execute(
        select(Appointment).where(
            Appointment.patient_id == current_user.id,
            Appointment.time_slot_id == payload.time_slot_id,
            Appointment.status.notin_([AppointmentStatus.CANCELLED]),
        )
    )
    if conflict.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="You already have an appointment in this slot")

    # Mark slot as booked
    slot.status = SlotStatus.BOOKED

    appointment = Appointment(
        patient_id=current_user.id,
        doctor_id=payload.doctor_id,
        time_slot_id=payload.time_slot_id,
        consultation_type=payload.consultation_type,
        symptoms=payload.symptoms,
        notes=payload.notes,
        fee_paid=doctor.video_fee if payload.consultation_type.value == "video" else doctor.consultation_fee,
    )
    db.add(appointment)
    await db.flush()
    await db.refresh(appointment)

    # Update total_patients on doctor
    doctor.total_patients = (doctor.total_patients or 0) + 1

    # Invalidate slots cache
    await cache_delete(make_slots_key(payload.doctor_id, str(slot.slot_date)))
    await cache_delete_pattern(f"search:*")

    # TODO: Send notification (push/email) to doctor and patient
    return appointment


# ─────────────────────────────────────────────
#  Get My Appointments (Patient)
# ─────────────────────────────────────────────

@router.get("/my", response_model=List[dict])
async def get_my_appointments(
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all appointments for the current patient."""
    stmt = (
        select(Appointment)
        .options(
            selectinload(Appointment.time_slot),
            selectinload(Appointment.doctor).selectinload(DoctorProfile.user),
            selectinload(Appointment.doctor).selectinload(DoctorProfile.specialization),
        )
        .where(Appointment.patient_id == current_user.id)
        .order_by(Appointment.created_at.desc())
    )
    if status:
        stmt = stmt.where(Appointment.status == status)

    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    appointments = result.scalars().all()

    return [
        {
            "id": a.id,
            "status": a.status,
            "consultation_type": a.consultation_type,
            "doctor_name": a.doctor.user.full_name if a.doctor and a.doctor.user else None,
            "specialization": a.doctor.specialization.name if a.doctor and a.doctor.specialization else None,
            "slot_date": str(a.time_slot.slot_date) if a.time_slot else None,
            "start_time": str(a.time_slot.start_time) if a.time_slot else None,
            "fee_paid": a.fee_paid,
            "payment_status": a.payment_status,
            "created_at": a.created_at,
        }
        for a in appointments
    ]


# ─────────────────────────────────────────────
#  Get Doctor's Appointments
# ─────────────────────────────────────────────

@router.get("/doctor", response_model=List[dict])
async def get_doctor_appointments(
    status: Optional[str] = Query(None),
    date_filter: Optional[str] = Query(None, description="YYYY-MM-DD"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_doctor),
):
    """Get appointments for the currently logged-in doctor."""
    # Get doctor profile
    doc_result = await db.execute(
        select(DoctorProfile).where(DoctorProfile.user_id == current_user.id)
    )
    doctor = doc_result.scalar_one_or_none()
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor profile not found")

    stmt = (
        select(Appointment)
        .options(
            selectinload(Appointment.time_slot),
            selectinload(Appointment.patient),
        )
        .where(Appointment.doctor_id == doctor.id)
        .order_by(Appointment.created_at.desc())
    )
    if status:
        stmt = stmt.where(Appointment.status == status)
    if date_filter:
        from datetime import date
        d = date.fromisoformat(date_filter)
        stmt = stmt.join(TimeSlot).where(TimeSlot.slot_date == d)

    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    appointments = result.scalars().all()

    return [
        {
            "id": a.id,
            "patient_name": a.patient.full_name if a.patient else None,
            "patient_email": a.patient.email if a.patient else None,
            "status": a.status,
            "consultation_type": a.consultation_type,
            "symptoms": a.symptoms,
            "slot_date": str(a.time_slot.slot_date) if a.time_slot else None,
            "start_time": str(a.time_slot.start_time) if a.time_slot else None,
            "created_at": a.created_at,
        }
        for a in appointments
    ]


# ─────────────────────────────────────────────
#  Get Single Appointment
# ─────────────────────────────────────────────

@router.get("/{appointment_id}", response_model=dict)
async def get_appointment(
    appointment_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Appointment)
        .options(
            selectinload(Appointment.time_slot),
            selectinload(Appointment.patient),
            selectinload(Appointment.doctor).selectinload(DoctorProfile.user),
            selectinload(Appointment.doctor).selectinload(DoctorProfile.specialization),
        )
        .where(Appointment.id == appointment_id)
    )
    appt: Appointment = result.scalar_one_or_none()
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")

    # Authorization: only patient, doctor, or admin
    is_patient = appt.patient_id == current_user.id
    is_doctor  = appt.doctor.user_id == current_user.id if appt.doctor else False
    if not is_patient and not is_doctor and current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Access denied")

    return {
        "id": appt.id,
        "status": appt.status,
        "consultation_type": appt.consultation_type,
        "symptoms": appt.symptoms,
        "notes": appt.notes,
        "prescription": appt.prescription,
        "diagnosis": appt.diagnosis,
        "follow_up_date": str(appt.follow_up_date) if appt.follow_up_date else None,
        "video_call_link": appt.video_call_link,
        "fee_paid": appt.fee_paid,
        "payment_status": appt.payment_status,
        "patient_name": appt.patient.full_name if appt.patient else None,
        "doctor_name": appt.doctor.user.full_name if appt.doctor and appt.doctor.user else None,
        "specialization": appt.doctor.specialization.name if appt.doctor and appt.doctor.specialization else None,
        "slot_date": str(appt.time_slot.slot_date) if appt.time_slot else None,
        "start_time": str(appt.time_slot.start_time) if appt.time_slot else None,
        "created_at": appt.created_at,
    }


# ─────────────────────────────────────────────
#  Update Appointment (Doctor fills diagnosis / prescription)
# ─────────────────────────────────────────────

@router.patch("/{appointment_id}", response_model=AppointmentOut)
async def update_appointment(
    appointment_id: int,
    payload: AppointmentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Appointment)
        .options(selectinload(Appointment.doctor))
        .where(Appointment.id == appointment_id)
    )
    appt: Appointment = result.scalar_one_or_none()
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")

    is_doctor = appt.doctor.user_id == current_user.id if appt.doctor else False
    is_admin  = current_user.role == UserRole.ADMIN
    if not is_doctor and not is_admin:
        raise HTTPException(status_code=403, detail="Only the treating doctor can update")

    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(appt, field, value)

    await db.flush()
    await db.refresh(appt)
    return appt


# ─────────────────────────────────────────────
#  Confirm Appointment (Doctor)
# ─────────────────────────────────────────────

@router.post("/{appointment_id}/confirm", response_model=MessageResponse)
async def confirm_appointment(
    appointment_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_doctor),
):
    result = await db.execute(
        select(Appointment)
        .options(selectinload(Appointment.doctor))
        .where(Appointment.id == appointment_id)
    )
    appt: Appointment = result.scalar_one_or_none()
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if appt.doctor.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your appointment")
    if appt.status != AppointmentStatus.PENDING:
        raise HTTPException(status_code=400, detail=f"Cannot confirm an appointment with status: {appt.status}")

    appt.status = AppointmentStatus.CONFIRMED
    return {"message": "Appointment confirmed"}


# ─────────────────────────────────────────────
#  Cancel Appointment
# ─────────────────────────────────────────────

@router.post("/{appointment_id}/cancel", response_model=MessageResponse)
async def cancel_appointment(
    appointment_id: int,
    payload: CancelAppointmentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Appointment)
        .options(
            selectinload(Appointment.time_slot),
            selectinload(Appointment.doctor),
        )
        .where(Appointment.id == appointment_id)
    )
    appt: Appointment = result.scalar_one_or_none()
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")

    is_patient = appt.patient_id == current_user.id
    is_doctor  = appt.doctor.user_id == current_user.id if appt.doctor else False
    is_admin   = current_user.role == UserRole.ADMIN

    if not is_patient and not is_doctor and not is_admin:
        raise HTTPException(status_code=403, detail="Not authorized to cancel")
    if appt.status in [AppointmentStatus.CANCELLED, AppointmentStatus.COMPLETED]:
        raise HTTPException(status_code=400, detail=f"Appointment already {appt.status}")

    appt.status = AppointmentStatus.CANCELLED
    appt.cancelled_by = "patient" if is_patient else "doctor"
    appt.cancellation_reason = payload.reason
    appt.cancelled_at = datetime.utcnow()

    # Free up the slot
    if appt.time_slot:
        appt.time_slot.status = SlotStatus.AVAILABLE
        await cache_delete(make_slots_key(appt.doctor_id, str(appt.time_slot.slot_date)))

    return {"message": "Appointment cancelled successfully"}


# ─────────────────────────────────────────────
#  Complete Appointment
# ─────────────────────────────────────────────

@router.post("/{appointment_id}/complete", response_model=MessageResponse)
async def complete_appointment(
    appointment_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_doctor),
):
    result = await db.execute(
        select(Appointment)
        .options(selectinload(Appointment.doctor))
        .where(Appointment.id == appointment_id)
    )
    appt: Appointment = result.scalar_one_or_none()
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if appt.doctor.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your appointment")
    if appt.status != AppointmentStatus.CONFIRMED:
        raise HTTPException(status_code=400, detail="Only confirmed appointments can be completed")

    appt.status = AppointmentStatus.COMPLETED
    return {"message": "Appointment marked as completed"}


# ─────────────────────────────────────────────
#  Review
# ─────────────────────────────────────────────

@router.post("/{appointment_id}/review", response_model=ReviewOut, status_code=201)
async def submit_review(
    appointment_id: int,
    payload: ReviewCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Submit a review after a completed appointment."""
    result = await db.execute(
        select(Appointment)
        .options(selectinload(Appointment.doctor))
        .where(Appointment.id == appointment_id, Appointment.patient_id == current_user.id)
    )
    appt: Appointment = result.scalar_one_or_none()
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if appt.status != AppointmentStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Can only review completed appointments")

    # Check duplicate
    existing = await db.execute(
        select(Review).where(Review.appointment_id == appointment_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Review already submitted for this appointment")

    review = Review(
        patient_id=current_user.id,
        doctor_id=appt.doctor_id,
        appointment_id=appointment_id,
        rating=payload.rating,
        comment=payload.comment,
        is_anonymous=payload.is_anonymous,
    )
    db.add(review)
    await db.flush()

    # Update doctor's avg_rating and total_reviews
    doc = appt.doctor
    new_total  = doc.total_reviews + 1
    new_avg    = ((doc.avg_rating * doc.total_reviews) + payload.rating) / new_total
    doc.total_reviews = new_total
    doc.avg_rating    = round(new_avg, 2)

    await db.refresh(review)
    await cache_delete(f"doctor:{doc.id}")
    await cache_delete_pattern("search:*")
    return review
