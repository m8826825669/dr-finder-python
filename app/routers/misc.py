from typing import List
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update

from app.database import get_db
from app.models import Notification, User, DoctorProfile, Appointment, AppointmentStatus
from app.schemas import NotificationOut, MessageResponse
from app.auth import get_current_user, get_current_admin

# ─── Notifications ────────────────────────────────────────────────────────────
notif_router = APIRouter(prefix="/notifications", tags=["Notifications"])


@notif_router.get("", response_model=List[NotificationOut])
async def get_notifications(
    unread_only: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stmt = (
        select(Notification)
        .where(Notification.user_id == current_user.id)
        .order_by(Notification.created_at.desc())
    )
    if unread_only:
        stmt = stmt.where(Notification.is_read == False)
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    return result.scalars().all()


@notif_router.post("/{notif_id}/read", response_model=MessageResponse)
async def mark_read(
    notif_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await db.execute(
        update(Notification)
        .where(Notification.id == notif_id, Notification.user_id == current_user.id)
        .values(is_read=True)
    )
    return {"message": "Marked as read"}


@notif_router.post("/read-all", response_model=MessageResponse)
async def mark_all_read(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await db.execute(
        update(Notification)
        .where(Notification.user_id == current_user.id, Notification.is_read == False)
        .values(is_read=True)
    )
    return {"message": "All notifications marked as read"}


# ─── Admin Dashboard ──────────────────────────────────────────────────────────
admin_router = APIRouter(prefix="/admin", tags=["Admin"])


@admin_router.get("/stats")
async def get_stats(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    """Platform-level statistics."""
    from app.models import UserRole

    total_users = (await db.execute(select(func.count(User.id)))).scalar()
    total_doctors = (await db.execute(select(func.count(DoctorProfile.id)))).scalar()
    total_patients = (await db.execute(
        select(func.count(User.id)).where(User.role == UserRole.PATIENT)
    )).scalar()
    verified_doctors = (await db.execute(
        select(func.count(DoctorProfile.id)).where(DoctorProfile.is_verified == True)
    )).scalar()
    pending_verification = (await db.execute(
        select(func.count(DoctorProfile.id)).where(DoctorProfile.is_verified == False)
    )).scalar()
    total_appts = (await db.execute(select(func.count(Appointment.id)))).scalar()
    completed = (await db.execute(
        select(func.count(Appointment.id)).where(Appointment.status == AppointmentStatus.COMPLETED)
    )).scalar()
    pending = (await db.execute(
        select(func.count(Appointment.id)).where(Appointment.status == AppointmentStatus.PENDING)
    )).scalar()

    return {
        "total_users": total_users,
        "total_doctors": total_doctors,
        "total_patients": total_patients,
        "verified_doctors": verified_doctors,
        "pending_verification": pending_verification,
        "total_appointments": total_appts,
        "completed_appointments": completed,
        "pending_appointments": pending,
    }


@admin_router.post("/doctors/{doctor_id}/verify", response_model=MessageResponse)
async def verify_doctor(
    doctor_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    doctor = await db.get(DoctorProfile, doctor_id)
    if not doctor:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Doctor not found")
    doctor.is_verified = True
    return {"message": f"Doctor {doctor_id} verified"}


@admin_router.post("/doctors/{doctor_id}/feature", response_model=MessageResponse)
async def feature_doctor(
    doctor_id: int,
    featured: bool = True,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    doctor = await db.get(DoctorProfile, doctor_id)
    if not doctor:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Doctor not found")
    doctor.is_featured = featured
    return {"message": f"Doctor {doctor_id} {'featured' if featured else 'unfeatured'}"}
