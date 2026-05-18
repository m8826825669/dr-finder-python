from datetime import date, timedelta, datetime, time
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import (
    User, DoctorProfile, Specialization, DoctorAvailability,
    TimeSlot, SlotStatus, ConsultationType, UserRole
)
from app.schemas import (
    DoctorProfileCreate, DoctorProfileUpdate, DoctorDetail, DoctorSummary,
    AvailabilityCreate, AvailabilityOut, TimeSlotOut,
    GenerateSlotsRequest, DoctorSearchParams, SearchResponse, MessageResponse,
    SpecializationCreate, SpecializationOut,
)
from app.auth import get_current_user, get_current_doctor, get_current_admin
from app.cache import cache_get, cache_set, cache_delete, cache_delete_pattern, make_doctor_key, make_slots_key, make_search_key
from app.elasticsearch_service import search_doctors, index_doctor, delete_doctor_from_index
from app.config import settings

router = APIRouter(prefix="/doctors", tags=["Doctors"])


# ─────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────

def _doctor_to_summary(doctor: DoctorProfile) -> dict:
    return {
        "id": doctor.id,
        "user_id": doctor.user_id,
        "full_name": doctor.user.full_name if doctor.user else "",
        "specialization": doctor.specialization.name if doctor.specialization else "",
        "experience_years": doctor.experience_years,
        "consultation_fee": doctor.consultation_fee,
        "avg_rating": doctor.avg_rating,
        "total_reviews": doctor.total_reviews,
        "city": doctor.city,
        "clinic_name": doctor.clinic_name,
        "avatar_url": doctor.avatar_url,
        "is_verified": doctor.is_verified,
        "available_for_video": doctor.available_for_video,
        "accepting_new_patients": doctor.accepting_new_patients,
    }


def _doctor_to_detail(doctor: DoctorProfile) -> dict:
    """Build a complete DoctorDetail-compatible dict from an ORM object."""
    return {
        **_doctor_to_summary(doctor),
        "registration_number": doctor.registration_number,
        "gender":              doctor.gender,
        "bio":                 doctor.bio,
        "languages":           doctor.languages or [],
        "qualifications":      doctor.qualifications or [],
        "awards":              doctor.awards or [],
        "video_fee":           doctor.video_fee,
        "follow_up_fee":       doctor.follow_up_fee,
        "clinic_address":      doctor.clinic_address,
        "state":               doctor.state,
        "pincode":             doctor.pincode,
        "latitude":            doctor.latitude,
        "longitude":           doctor.longitude,
        "available_for_home":  doctor.available_for_home,
        "total_patients":      doctor.total_patients,
    }


async def _get_doctor_or_404(doctor_id: int, db: AsyncSession) -> DoctorProfile:
    result = await db.execute(
        select(DoctorProfile)
        .options(selectinload(DoctorProfile.user), selectinload(DoctorProfile.specialization))
        .where(DoctorProfile.id == doctor_id)
    )
    doctor = result.scalar_one_or_none()
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")
    return doctor


# ─────────────────────────────────────────────
#  Specializations (lookup)
# ─────────────────────────────────────────────

@router.get("/specializations", response_model=List[SpecializationOut], tags=["Specializations"])
async def list_specializations(db: AsyncSession = Depends(get_db)):
    """Get all medical specializations."""
    cached = await cache_get("specializations:all")
    if cached:
        return cached
    result = await db.execute(select(Specialization).order_by(Specialization.name))
    specs = result.scalars().all()
    data = [{"id": s.id, "name": s.name, "description": s.description, "icon_url": s.icon_url} for s in specs]
    await cache_set("specializations:all", data, ttl=3600)
    return data


@router.post("/specializations", response_model=SpecializationOut, status_code=201, tags=["Specializations"])
async def create_specialization(
    payload: SpecializationCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    spec = Specialization(**payload.model_dump())
    db.add(spec)
    await db.flush()
    await db.refresh(spec)
    await cache_delete("specializations:all")
    return spec


# ─────────────────────────────────────────────
#  Search  (primary — ES backed with PG fallback)
# ─────────────────────────────────────────────

@router.get("/search", response_model=SearchResponse)
async def search(
    q: Optional[str]         = Query(None, description="Name, specialization, clinic keyword"),
    specialization_id: Optional[int] = Query(None),
    city: Optional[str]      = Query(None),
    state: Optional[str]     = Query(None),
    pincode: Optional[str]   = Query(None),
    lat: Optional[float]     = Query(None),
    lng: Optional[float]     = Query(None),
    radius_km: float         = Query(10.0),
    min_fee: Optional[float] = Query(None),
    max_fee: Optional[float] = Query(None),
    min_rating: Optional[float] = Query(None),
    min_experience: Optional[int] = Query(None),
    gender: Optional[str]    = Query(None),
    available_for_video: Optional[bool] = Query(None),
    available_for_home: Optional[bool]  = Query(None),
    accepting_new_patients: Optional[bool] = Query(None),
    available_on: Optional[date] = Query(None),
    language: Optional[str]  = Query(None),
    is_verified: Optional[bool] = Query(None),
    sort_by: str             = Query("relevance"),
    page: int                = Query(1, ge=1),
    page_size: int           = Query(10, ge=1, le=50),
    db: AsyncSession         = Depends(get_db),
):
    """
    Search doctors with full-text, filters, geo-distance.
    Uses Elasticsearch for speed; falls back to PostgreSQL.
    Results are cached in Redis.
    """
    params = {k: v for k, v in locals().items()
              if k not in ("db",) and v is not None and k != "self"}
    cache_key = make_search_key(params)

    cached = await cache_get(cache_key)
    if cached:
        return cached

    # ── Try Elasticsearch first ────────────────────────────────
    es_result = await search_doctors(params)

    if es_result is not None:
        total      = es_result["total"]
        total_pages = (total + page_size - 1) // page_size
        response   = {
            "total": total, "page": page, "page_size": page_size,
            "total_pages": total_pages,
            "results": es_result["hits"],
        }
        await cache_set(cache_key, response, ttl=settings.SEARCH_CACHE_TTL)
        return response

    # ── Fallback: PostgreSQL ───────────────────────────────────
    stmt = (
        select(DoctorProfile)
        .join(DoctorProfile.user)
        .join(DoctorProfile.specialization)
        .options(selectinload(DoctorProfile.user), selectinload(DoctorProfile.specialization))
    )

    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(
                User.full_name.ilike(like),
                Specialization.name.ilike(like),
                DoctorProfile.clinic_name.ilike(like),
                DoctorProfile.city.ilike(like),
            )
        )
    if specialization_id:
        stmt = stmt.where(DoctorProfile.specialization_id == specialization_id)
    if city:
        stmt = stmt.where(DoctorProfile.city.ilike(f"%{city}%"))
    if state:
        stmt = stmt.where(DoctorProfile.state.ilike(f"%{state}%"))
    if pincode:
        stmt = stmt.where(DoctorProfile.pincode == pincode)
    if min_fee is not None:
        stmt = stmt.where(DoctorProfile.consultation_fee >= min_fee)
    if max_fee is not None:
        stmt = stmt.where(DoctorProfile.consultation_fee <= max_fee)
    if min_rating is not None:
        stmt = stmt.where(DoctorProfile.avg_rating >= min_rating)
    if min_experience is not None:
        stmt = stmt.where(DoctorProfile.experience_years >= min_experience)
    if gender:
        stmt = stmt.where(DoctorProfile.gender == gender)
    if available_for_video is not None:
        stmt = stmt.where(DoctorProfile.available_for_video == available_for_video)
    if available_for_home is not None:
        stmt = stmt.where(DoctorProfile.available_for_home == available_for_home)
    if accepting_new_patients is not None:
        stmt = stmt.where(DoctorProfile.accepting_new_patients == accepting_new_patients)
    if is_verified is not None:
        stmt = stmt.where(DoctorProfile.is_verified == is_verified)
    if language:
        stmt = stmt.where(DoctorProfile.languages.contains([language]))
    if available_on:
        sub = select(TimeSlot.doctor_id).where(
            TimeSlot.slot_date == available_on,
            TimeSlot.status == SlotStatus.AVAILABLE,
        ).distinct()
        stmt = stmt.where(DoctorProfile.id.in_(sub))

    # Sort
    sort_map = {
        "rating":     DoctorProfile.avg_rating.desc(),
        "fee_asc":    DoctorProfile.consultation_fee.asc(),
        "fee_desc":   DoctorProfile.consultation_fee.desc(),
        "experience": DoctorProfile.experience_years.desc(),
    }
    stmt = stmt.order_by(sort_map.get(sort_by, DoctorProfile.avg_rating.desc()))

    # Count
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    # Paginate
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    doctors = result.scalars().all()

    total_pages = (total + page_size - 1) // page_size
    response = {
        "total": total, "page": page, "page_size": page_size,
        "total_pages": total_pages,
        "results": [_doctor_to_summary(d) for d in doctors],
    }
    await cache_set(cache_key, response, ttl=settings.SEARCH_CACHE_TTL)
    return response


# ─────────────────────────────────────────────
#  Doctor Profile CRUD
# ─────────────────────────────────────────────

@router.post("/profile", response_model=DoctorDetail, status_code=201)
async def create_doctor_profile(
    payload: DoctorProfileCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_doctor),
):
    """Create doctor profile (only for users with doctor role)."""
    existing = await db.execute(
        select(DoctorProfile).where(DoctorProfile.user_id == current_user.id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Doctor profile already exists")

    spec = await db.get(Specialization, payload.specialization_id)
    if not spec:
        raise HTTPException(status_code=404, detail="Specialization not found")

    doctor = DoctorProfile(user_id=current_user.id, **payload.model_dump())
    db.add(doctor)
    await db.flush()

    # Reload with relationships so _doctor_to_detail works
    result = await db.execute(
        select(DoctorProfile)
        .options(selectinload(DoctorProfile.user), selectinload(DoctorProfile.specialization))
        .where(DoctorProfile.id == doctor.id)
    )
    doctor = result.scalar_one()

    detail = _doctor_to_detail(doctor)
    await index_doctor({**detail, "specialization_id": doctor.specialization_id,
                        "is_featured": doctor.is_featured})
    return detail


@router.get("/profile/me", response_model=Optional[DoctorDetail])
async def get_my_doctor_profile(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_doctor),
):
    """Return the authenticated doctor's own profile, or null if not yet created."""
    result = await db.execute(
        select(DoctorProfile)
        .options(selectinload(DoctorProfile.user), selectinload(DoctorProfile.specialization))
        .where(DoctorProfile.user_id == current_user.id)
    )
    doctor = result.scalar_one_or_none()
    if not doctor:
        return None
    return _doctor_to_detail(doctor)


@router.get("/{doctor_id}", response_model=DoctorDetail)
async def get_doctor(doctor_id: int, db: AsyncSession = Depends(get_db)):
    """Get doctor profile by ID."""
    cache_key = make_doctor_key(doctor_id)
    cached = await cache_get(cache_key)
    if cached:
        return cached

    doctor = await _get_doctor_or_404(doctor_id, db)
    data = _doctor_to_detail(doctor)
    await cache_set(cache_key, data, ttl=settings.CACHE_TTL)
    return data


@router.put("/profile", response_model=DoctorDetail)
async def update_doctor_profile(
    payload: DoctorProfileUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_doctor),
):
    """Update own doctor profile."""
    result = await db.execute(
        select(DoctorProfile)
        .options(selectinload(DoctorProfile.user), selectinload(DoctorProfile.specialization))
        .where(DoctorProfile.user_id == current_user.id)
    )
    doctor = result.scalar_one_or_none()
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor profile not found")

    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(doctor, field, value)

    await db.flush()
    await cache_delete(make_doctor_key(doctor.id))
    await cache_delete_pattern("search:*")
    detail = _doctor_to_detail(doctor)
    await index_doctor({**detail, "id": doctor.id})
    return detail


# ─────────────────────────────────────────────
#  Availability Management
# ─────────────────────────────────────────────

@router.post("/{doctor_id}/availability", response_model=AvailabilityOut, status_code=201)
async def add_availability(
    doctor_id: int,
    payload: AvailabilityCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_doctor),
):
    """Set a weekly recurring availability slot."""
    doctor = await _get_doctor_or_404(doctor_id, db)
    if doctor.user_id != current_user.id and current_user.role.value != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    avail = DoctorAvailability(doctor_id=doctor_id, **payload.model_dump())
    db.add(avail)
    await db.flush()
    await db.refresh(avail)
    return avail


@router.get("/{doctor_id}/availability", response_model=List[AvailabilityOut])
async def get_availability(doctor_id: int, db: AsyncSession = Depends(get_db)):
    """Get weekly availability schedule for a doctor."""
    result = await db.execute(
        select(DoctorAvailability)
        .where(DoctorAvailability.doctor_id == doctor_id, DoctorAvailability.is_active == True)
        .order_by(DoctorAvailability.day_of_week, DoctorAvailability.start_time)
    )
    return result.scalars().all()


@router.delete("/{doctor_id}/availability/{avail_id}", response_model=MessageResponse)
async def delete_availability(
    doctor_id: int,
    avail_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_doctor),
):
    result = await db.execute(
        select(DoctorAvailability).where(
            DoctorAvailability.id == avail_id,
            DoctorAvailability.doctor_id == doctor_id,
        )
    )
    avail = result.scalar_one_or_none()
    if not avail:
        raise HTTPException(status_code=404, detail="Availability not found")
    await db.delete(avail)
    return {"message": "Availability deleted"}


# ─────────────────────────────────────────────
#  Time Slot Generation & Query
# ─────────────────────────────────────────────

@router.post("/{doctor_id}/slots/generate", response_model=MessageResponse)
async def generate_slots(
    doctor_id: int,
    payload: GenerateSlotsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_doctor),
):
    """
    Auto-generate concrete time slots from weekly availability
    for a date range.
    """
    doctor = await _get_doctor_or_404(doctor_id, db)
    if doctor.user_id != current_user.id and current_user.role.value != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    # Fetch availability
    avail_result = await db.execute(
        select(DoctorAvailability).where(
            DoctorAvailability.doctor_id == doctor_id,
            DoctorAvailability.is_active == True,
        )
    )
    availabilities = avail_result.scalars().all()
    if not availabilities:
        raise HTTPException(status_code=400, detail="No availability configured")

    created_count = 0
    current_date  = payload.from_date
    while current_date <= payload.to_date:
        dow = current_date.weekday()  # 0=Mon
        day_avails = [a for a in availabilities if a.day_of_week == dow]
        for avail in day_avails:
            start = datetime.combine(current_date, avail.start_time)
            end   = datetime.combine(current_date, avail.end_time)
            duration = timedelta(minutes=avail.slot_duration_minutes)
            slot_start = start
            while slot_start + duration <= end:
                slot_end = slot_start + duration
                # Skip if already exists
                existing = await db.execute(
                    select(TimeSlot).where(
                        TimeSlot.doctor_id == doctor_id,
                        TimeSlot.slot_date == current_date,
                        TimeSlot.start_time == slot_start.time(),
                        TimeSlot.consultation_type == avail.consultation_type,
                    )
                )
                if not existing.scalar_one_or_none():
                    slot = TimeSlot(
                        doctor_id=doctor_id,
                        slot_date=current_date,
                        start_time=slot_start.time(),
                        end_time=slot_end.time(),
                        consultation_type=avail.consultation_type,
                    )
                    db.add(slot)
                    created_count += 1
                slot_start += duration
        current_date += timedelta(days=1)

    await db.flush()
    # Invalidate slots cache
    await cache_delete_pattern(f"slots:{doctor_id}:*")
    return {"message": f"Generated {created_count} slots"}


@router.get("/{doctor_id}/slots", response_model=List[TimeSlotOut])
async def get_slots(
    doctor_id: int,
    slot_date: date = Query(..., description="Date to fetch slots for (YYYY-MM-DD)"),
    consultation_type: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Get available time slots for a doctor on a given date."""
    cache_key = make_slots_key(doctor_id, str(slot_date))
    cached = await cache_get(cache_key)
    if cached:
        return cached

    stmt = select(TimeSlot).where(
        TimeSlot.doctor_id == doctor_id,
        TimeSlot.slot_date == slot_date,
        TimeSlot.status == SlotStatus.AVAILABLE,
    )
    if consultation_type:
        stmt = stmt.where(TimeSlot.consultation_type == consultation_type)
    stmt = stmt.order_by(TimeSlot.start_time)

    result = await db.execute(stmt)
    slots = result.scalars().all()
    data = [
        {"id": s.id, "slot_date": str(s.slot_date), "start_time": str(s.start_time),
         "end_time": str(s.end_time), "status": s.status, "consultation_type": s.consultation_type}
        for s in slots
    ]
    await cache_set(cache_key, data, ttl=60)
    return slots


@router.get("/{doctor_id}/slots/range", response_model=List[TimeSlotOut])
async def get_slots_range(
    doctor_id: int,
    from_date: date = Query(...),
    to_date: date   = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Get available time slots for a doctor over a date range (max 30 days)."""
    if (to_date - from_date).days > 30:
        raise HTTPException(status_code=400, detail="Date range cannot exceed 30 days")
    result = await db.execute(
        select(TimeSlot).where(
            TimeSlot.doctor_id == doctor_id,
            TimeSlot.slot_date >= from_date,
            TimeSlot.slot_date <= to_date,
            TimeSlot.status == SlotStatus.AVAILABLE,
        ).order_by(TimeSlot.slot_date, TimeSlot.start_time)
    )
    return result.scalars().all()


@router.get("/{doctor_id}/reviews")
async def get_doctor_reviews(
    doctor_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """Get reviews for a doctor."""
    from app.models import Review
    stmt = (
        select(Review)
        .options(selectinload(Review.patient))
        .where(Review.doctor_id == doctor_id, Review.is_approved == True)
        .order_by(Review.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    reviews = result.scalars().all()
    count = await db.execute(
        select(func.count()).where(Review.doctor_id == doctor_id, Review.is_approved == True)
    )
    total = count.scalar()
    return {
        "total": total, "page": page, "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
        "results": [
            {
                "id": r.id, "rating": r.rating, "comment": r.comment,
                "is_anonymous": r.is_anonymous,
                "patient_name": "Anonymous" if r.is_anonymous else r.patient.full_name,
                "created_at": r.created_at,
            }
            for r in reviews
        ]
    }
