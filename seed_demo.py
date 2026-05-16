"""
Seed demo data for DoctorFinder.
Idempotent: safe to re-run.
Run: /var/www/doctor/backend/.venv/bin/python seed_demo.py
"""
import asyncio
import random
from datetime import date, time, timedelta, datetime

from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models import (
    User, UserRole, PatientProfile, DoctorProfile, Specialization,
    DoctorAvailability, TimeSlot, Appointment, Review, Notification,
    ConsultationType, AppointmentStatus, SlotStatus, Gender,
)
from app.auth import hash_password

PASSWORD = "Demo@1234"
PWHASH = hash_password(PASSWORD)

SPECIALIZATIONS = [
    ("General Physician", "Primary care for everyday health concerns", None),
    ("Cardiology", "Heart and vascular system specialists", None),
    ("Dermatology", "Skin, hair, and nail conditions", None),
    ("Pediatrics", "Healthcare for infants, children, and adolescents", None),
    ("Orthopedics", "Bones, joints, and musculoskeletal system", None),
    ("Neurology", "Brain, spinal cord, and nervous system", None),
]

DOCTORS = [
    {"name": "Dr. Priya Mehta",     "email": "priya.mehta@vexen.demo",    "spec": "Cardiology",        "gender": Gender.FEMALE, "exp": 15, "fee": 800,  "video_fee": 600, "city": "Delhi",     "clinic": "HeartCare Clinic, CP",         "languages": ["English","Hindi"],          "video": True,  "reg": "DMC/R/12345"},
    {"name": "Dr. Arjun Sharma",    "email": "arjun.sharma@vexen.demo",   "spec": "General Physician", "gender": Gender.MALE,   "exp": 10, "fee": 500,  "video_fee": 400, "city": "Delhi",     "clinic": "Wellness Family Clinic, GK-2", "languages": ["English","Hindi","Punjabi"], "video": True,  "reg": "DMC/R/23456"},
    {"name": "Dr. Anjali Iyer",     "email": "anjali.iyer@vexen.demo",    "spec": "Dermatology",       "gender": Gender.FEMALE, "exp": 8,  "fee": 700,  "video_fee": 500, "city": "Mumbai",    "clinic": "GlowSkin, Bandra",             "languages": ["English","Hindi","Marathi"], "video": True,  "reg": "MMC/R/34567"},
    {"name": "Dr. Rohan Desai",     "email": "rohan.desai@vexen.demo",    "spec": "Orthopedics",       "gender": Gender.MALE,   "exp": 20, "fee": 1200, "video_fee": None,"city": "Mumbai",    "clinic": "BoneFit Ortho, Andheri",       "languages": ["English","Hindi","Gujarati"],"video": False, "reg": "MMC/R/45678"},
    {"name": "Dr. Kavya Reddy",     "email": "kavya.reddy@vexen.demo",    "spec": "Pediatrics",        "gender": Gender.FEMALE, "exp": 12, "fee": 600,  "video_fee": 450, "city": "Bangalore", "clinic": "LittleStars Pediatrics",       "languages": ["English","Telugu","Kannada"],"video": True,  "reg": "KMC/R/56789"},
    {"name": "Dr. Vikram Singh",    "email": "vikram.singh@vexen.demo",   "spec": "Neurology",         "gender": Gender.MALE,   "exp": 22, "fee": 1500, "video_fee": 1200,"city": "Bangalore", "clinic": "NeuroCare Institute",          "languages": ["English","Hindi"],          "video": True,  "reg": "KMC/R/67890"},
    {"name": "Dr. Fatima Khan",     "email": "fatima.khan@vexen.demo",    "spec": "General Physician", "gender": Gender.FEMALE, "exp": 7,  "fee": 400,  "video_fee": 300, "city": "Delhi",     "clinic": "City Health, Lajpat Nagar",    "languages": ["English","Hindi","Urdu"],   "video": True,  "reg": "DMC/R/78901"},
    {"name": "Dr. Sandeep Pillai",  "email": "sandeep.pillai@vexen.demo", "spec": "Cardiology",        "gender": Gender.MALE,   "exp": 18, "fee": 1000, "video_fee": 800, "city": "Bangalore", "clinic": "Pulse Cardio Centre",          "languages": ["English","Malayalam","Kannada"], "video": True, "reg": "KMC/R/89012"},
]

PATIENTS = [
    ("Aakash Verma",   "aakash.verma@vexen.demo"),
    ("Meera Krishnan", "meera.krishnan@vexen.demo"),
    ("Rahul Joshi",    "rahul.joshi@vexen.demo"),
    ("Sneha Patil",    "sneha.patil@vexen.demo"),
    ("Imran Ali",      "imran.ali@vexen.demo"),
]


async def get_or_create_user(db, email, full_name, role):
    res = await db.execute(select(User).where(User.email == email))
    user = res.scalar_one_or_none()
    if user:
        return user, False
    user = User(
        email=email, full_name=full_name, hashed_password=PWHASH,
        role=role, is_active=True, is_verified=True,
        phone=f"+9198{random.randint(10000000, 99999999)}",
    )
    db.add(user)
    await db.flush()
    return user, True


async def get_or_create_spec(db, name, desc):
    res = await db.execute(select(Specialization).where(Specialization.name == name))
    spec = res.scalar_one_or_none()
    if spec:
        return spec
    spec = Specialization(name=name, description=desc)
    db.add(spec)
    await db.flush()
    return spec


async def seed_admin(db):
    user, created = await get_or_create_user(db, "admin@vexenlabs.com", "Admin", UserRole.ADMIN)
    return user, created


async def seed_specializations(db):
    out = {}
    for name, desc, _icon in SPECIALIZATIONS:
        out[name] = await get_or_create_spec(db, name, desc)
    return out


async def seed_doctor(db, specs, info):
    user, created = await get_or_create_user(db, info["email"], info["name"], UserRole.DOCTOR)
    res = await db.execute(select(DoctorProfile).where(DoctorProfile.user_id == user.id))
    profile = res.scalar_one_or_none()
    if profile:
        return user, profile, False
    profile = DoctorProfile(
        user_id=user.id,
        specialization_id=specs[info["spec"]].id,
        registration_number=info["reg"],
        gender=info["gender"],
        bio=f"{info['name']} is a {info['spec']} specialist with {info['exp']}+ years of experience.",
        languages=info["languages"],
        experience_years=info["exp"],
        qualifications=[{"degree": "MBBS"}, {"degree": "MD" if info["exp"] > 10 else "DNB"}],
        consultation_fee=info["fee"],
        video_fee=info["video_fee"],
        clinic_name=info["clinic"],
        city=info["city"],
        state={"Delhi": "Delhi", "Mumbai": "Maharashtra", "Bangalore": "Karnataka"}[info["city"]],
        is_verified=True,
        available_for_video=info["video"],
        accepting_new_patients=True,
        avg_rating=0.0,
        total_reviews=0,
        total_patients=0,
    )
    db.add(profile)
    await db.flush()
    return user, profile, True


async def seed_availability(db, doctor_profile):
    res = await db.execute(
        select(DoctorAvailability).where(DoctorAvailability.doctor_id == doctor_profile.id)
    )
    if res.scalars().first():
        return  # already has availability
    # Mon-Fri morning slots, Tue-Sat evening for some variety
    for dow in range(0, 5):  # 0=Mon ... 4=Fri
        db.add(DoctorAvailability(
            doctor_id=doctor_profile.id,
            day_of_week=dow,
            start_time=time(9, 0),
            end_time=time(13, 0),
            slot_duration_minutes=30,
            consultation_type=ConsultationType.IN_PERSON,
            max_patients_per_slot=1,
            is_active=True,
        ))
    for dow in [1, 2, 3, 4, 5]:  # Tue-Sat
        db.add(DoctorAvailability(
            doctor_id=doctor_profile.id,
            day_of_week=dow,
            start_time=time(17, 0),
            end_time=time(20, 0),
            slot_duration_minutes=30,
            consultation_type=ConsultationType.VIDEO if doctor_profile.available_for_video else ConsultationType.IN_PERSON,
            max_patients_per_slot=1,
            is_active=True,
        ))


async def seed_slots(db, doctor_profile, num_days=30):
    res = await db.execute(
        select(TimeSlot).where(TimeSlot.doctor_id == doctor_profile.id).limit(1)
    )
    if res.scalars().first():
        return  # slots already generated
    avails = (await db.execute(
        select(DoctorAvailability).where(DoctorAvailability.doctor_id == doctor_profile.id, DoctorAvailability.is_active == True)
    )).scalars().all()
    today = date.today()
    for offset in range(num_days):
        d = today + timedelta(days=offset)
        weekday = d.weekday()  # Mon=0 ... Sun=6
        for av in avails:
            if av.day_of_week != weekday:
                continue
            cur = datetime.combine(d, av.start_time)
            end = datetime.combine(d, av.end_time)
            while cur + timedelta(minutes=av.slot_duration_minutes) <= end:
                slot_start = cur.time()
                slot_end = (cur + timedelta(minutes=av.slot_duration_minutes)).time()
                db.add(TimeSlot(
                    doctor_id=doctor_profile.id,
                    slot_date=d,
                    start_time=slot_start,
                    end_time=slot_end,
                    consultation_type=av.consultation_type,
                    status=SlotStatus.AVAILABLE,
                ))
                cur += timedelta(minutes=av.slot_duration_minutes)


async def seed_patient(db, full_name, email):
    user, created = await get_or_create_user(db, email, full_name, UserRole.PATIENT)
    res = await db.execute(select(PatientProfile).where(PatientProfile.user_id == user.id))
    profile = res.scalar_one_or_none()
    if not profile:
        profile = PatientProfile(user_id=user.id)
        db.add(profile)
        await db.flush()
    return user, profile


async def seed_completed_appointments_and_reviews(db, doctors_data, patients):
    """For each doctor, create 3-7 completed appointments + reviews so ratings appear."""
    for user, profile in doctors_data:
        existing = await db.execute(
            select(Review).where(Review.doctor_id == profile.id).limit(1)
        )
        if existing.scalars().first():
            continue
        num_reviews = random.randint(3, 7)
        avg = 0
        for i in range(num_reviews):
            patient_user, patient_profile = random.choice(patients)
            # Use a past date for the appointment
            past_date = date.today() - timedelta(days=random.randint(7, 60))
            # Create a phantom completed slot
            
	    # Randomized past slot — avoid collisions on unique (doctor, date, time, type)
            past_hour = random.randint(9, 17)
            past_minute = random.choice([0, 15, 30, 45])
            slot_start = time(past_hour, past_minute)
            slot_end_dt = datetime.combine(past_date, slot_start) + timedelta(minutes=30)
            slot = TimeSlot(
                doctor_id=profile.id,
                slot_date=past_date,
                start_time=slot_start,
                end_time=slot_end_dt.time(),
                consultation_type=ConsultationType.IN_PERSON,
                status=SlotStatus.BOOKED,
            )
            db.add(slot)
            await db.flush()
            appt = Appointment(
                patient_id=patient_user.id,
                doctor_id=profile.id,
                time_slot_id=slot.id,
                status=AppointmentStatus.COMPLETED,
                consultation_type=ConsultationType.IN_PERSON,
                symptoms="General consultation",
                diagnosis="Routine check-up; no immediate concerns",
                prescription="As discussed",
            )
            db.add(appt)
            await db.flush()
            rating = round(random.uniform(4.0, 5.0), 1)
            avg += rating
            review = Review(
                appointment_id=appt.id,
                patient_id=patient_user.id,
                doctor_id=profile.id,
                rating=rating,
                comment=random.choice([
                    "Very thorough consultation, explained everything clearly.",
                    "Highly recommended. Took time to address all concerns.",
                    "Excellent doctor, very knowledgeable and friendly.",
                    "Good experience overall. Will visit again.",
                    "Professional and caring approach.",
                ]),
                is_anonymous=False,
            )
            db.add(review)
        profile.avg_rating = round(avg / num_reviews, 2)
        profile.total_reviews = num_reviews
        profile.total_patients = num_reviews
        db.add(profile)


async def main():
    async with AsyncSessionLocal() as db:
        async with db.begin():
            print("→ Seeding admin user...")
            admin, _ = await seed_admin(db)

            print("→ Seeding specializations...")
            specs = await seed_specializations(db)

            print("→ Seeding patient users...")
            patients = []
            for name, email in PATIENTS:
                u, p = await seed_patient(db, name, email)
                patients.append((u, p))

            print("→ Seeding doctor users + profiles...")
            doctors_data = []
            for info in DOCTORS:
                user, profile, created = await seed_doctor(db, specs, info)
                doctors_data.append((user, profile))
                if created:
                    print(f"   ✓ {info['name']} ({info['spec']}, {info['city']})")

            print("→ Seeding doctor availability...")
            for _, profile in doctors_data:
                await seed_availability(db, profile)

            print("→ Generating 30 days of time slots...")
            for _, profile in doctors_data:
                await seed_slots(db, profile, num_days=30)

            print("→ Seeding completed appointments + reviews...")
            await seed_completed_appointments_and_reviews(db, doctors_data, patients)

        print()
        print("✅ Seed complete.")
        print(f"   Admin:    admin@vexenlabs.com / {PASSWORD}")
        print(f"   Patient:  aakash.verma@vexen.demo / {PASSWORD}")
        print(f"   Doctor:   priya.mehta@vexen.demo / {PASSWORD}")
        print(f"   ({len(DOCTORS)} doctors, {len(PATIENTS)} patients, ~{len(DOCTORS)*5} reviews)")


if __name__ == "__main__":
    asyncio.run(main())
