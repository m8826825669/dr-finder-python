# 🏥 DoctorFinder API

A production-grade **Doctor Search & Appointment Booking** backend built with **FastAPI**, **PostgreSQL**, **Elasticsearch**, and **Redis**.

---

## ⚡ Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| Framework | **FastAPI** | Async, high-throughput, auto OpenAPI docs |
| Database | **PostgreSQL 16** | ACID, full-text search via `pg_trgm` |
| Search Engine | **Elasticsearch 8** | Sub-ms fuzzy/geo doctor search |
| Cache | **Redis 7** | Search result caching, slot availability |
| Auth | **JWT (jose)** | Access + Refresh token pair |
| ORM | **SQLAlchemy 2 (async)** | Async sessions, type-safe queries |
| Validation | **Pydantic v2** | Fast schema validation |
| Server | **Uvicorn** | ASGI, production-ready |

---

## 📁 Project Structure

```
doctor_app/
├── app/
│   ├── main.py                  # FastAPI app, middleware, routers
│   ├── config.py                # Settings (pydantic-settings + .env)
│   ├── database.py              # Async SQLAlchemy engine + session
│   ├── models.py                # All ORM models
│   ├── schemas.py               # All Pydantic request/response schemas
│   ├── auth.py                  # JWT utils, password hashing, role deps
│   ├── cache.py                 # Redis async helpers
│   ├── elasticsearch_service.py # ES index + search (with PG fallback)
│   └── routers/
│       ├── auth.py              # Register, Login, Refresh, Me
│       ├── doctors.py           # Search, Profile, Availability, Slots
│       ├── appointments.py      # Book, Confirm, Cancel, Complete, Review
│       └── misc.py              # Notifications, Admin
├── migrations/
│   └── versions/0001_initial.py
├── requirements.txt
├── .env.example
├── Dockerfile
└── docker-compose.yml
```

---

## 🚀 Quick Start

### Option A — Docker (recommended)

```bash
git clone <repo>
cd doctor_app
cp .env.example .env
docker-compose up --build
```

API live at: **http://localhost:8000**
Swagger UI: **http://localhost:8000/docs**

### Option B — Local (Windows)

```bash
# 1. Create venv
python -m venv venv
venv\Scripts\activate

# 2. Install deps
pip install -r requirements.txt

# 3. Start services (need PostgreSQL, Redis, Elasticsearch running)
cp .env.example .env
# Edit .env with your DB credentials

# 4. Run
uvicorn app.main:app --reload --port 8000
```

---

## 🗺️ Full API Reference

### 🔐 Authentication — `/api/v1/auth`

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/register` | ❌ | Register patient or doctor |
| POST | `/login` | ❌ | Login → access + refresh tokens |
| POST | `/refresh` | ❌ | Rotate tokens |
| GET | `/me` | ✅ | Current user info |
| POST | `/change-password` | ✅ | Change password |

**Register body:**
```json
{
  "email": "ravi@example.com",
  "phone": "9876543210",
  "full_name": "Dr. Ravi Sharma",
  "password": "secure123",
  "role": "doctor"
}
```

**Login response:**
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 86400
}
```

---

### 🔍 Doctor Search — `/api/v1/doctors/search`

**The most powerful endpoint** — backed by Elasticsearch with automatic PostgreSQL fallback.

| Query Param | Type | Description |
|-------------|------|-------------|
| `q` | string | Full-text: name, specialization, clinic, bio |
| `specialization_id` | int | Filter by specialty |
| `city` | string | City filter |
| `lat` / `lng` / `radius_km` | float | Geo-distance search |
| `min_fee` / `max_fee` | float | Fee range |
| `min_rating` | float | Minimum rating (1-5) |
| `min_experience` | int | Minimum years experience |
| `gender` | enum | male / female / other |
| `available_for_video` | bool | Video consultation filter |
| `available_on` | date | Has open slots on this date |
| `language` | string | Speaks this language |
| `is_verified` | bool | Only verified doctors |
| `sort_by` | enum | relevance / rating / fee_asc / fee_desc / experience / distance |
| `page` / `page_size` | int | Pagination |

**Example:**
```
GET /api/v1/doctors/search?q=cardiologist&city=Delhi&min_rating=4&available_for_video=true&sort_by=rating
```

**Response:**
```json
{
  "total": 42,
  "page": 1,
  "page_size": 10,
  "total_pages": 5,
  "results": [
    {
      "id": 1,
      "full_name": "Dr. Priya Mehta",
      "specialization": "Cardiology",
      "experience_years": 12,
      "consultation_fee": 800,
      "avg_rating": 4.8,
      "total_reviews": 234,
      "city": "Delhi",
      "is_verified": true,
      "available_for_video": true
    }
  ]
}
```

---

### 👨‍⚕️ Doctor Profile — `/api/v1/doctors`

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/specializations` | ❌ | List all specializations |
| POST | `/specializations` | Admin | Create specialization |
| POST | `/profile` | Doctor | Create doctor profile |
| GET | `/{doctor_id}` | ❌ | Get doctor detail |
| PUT | `/profile` | Doctor | Update own profile |
| GET | `/{doctor_id}/reviews` | ❌ | Get doctor reviews |

---

### 📅 Availability & Slots — `/api/v1/doctors`

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/{id}/availability` | Doctor | Add weekly recurring schedule |
| GET | `/{id}/availability` | ❌ | View weekly schedule |
| DELETE | `/{id}/availability/{avid}` | Doctor | Remove a schedule |
| POST | `/{id}/slots/generate` | Doctor | Auto-generate slots from schedule |
| GET | `/{id}/slots?slot_date=YYYY-MM-DD` | ❌ | Available slots on a date |
| GET | `/{id}/slots/range` | ❌ | Available slots over a date range |

**Add availability example:**
```json
{
  "day_of_week": 1,
  "start_time": "09:00:00",
  "end_time": "13:00:00",
  "slot_duration_minutes": 30,
  "consultation_type": "in_person"
}
```

**Generate slots:**
```json
{
  "from_date": "2025-02-01",
  "to_date": "2025-02-28"
}
```

---

### 🗓️ Appointments — `/api/v1/appointments`

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/` | Patient | Book appointment |
| GET | `/my` | Patient | My appointments |
| GET | `/doctor` | Doctor | Doctor's appointments |
| GET | `/{id}` | Patient/Doctor | Get appointment detail |
| PATCH | `/{id}` | Doctor | Add prescription / diagnosis |
| POST | `/{id}/confirm` | Doctor | Confirm appointment |
| POST | `/{id}/cancel` | Patient/Doctor | Cancel appointment |
| POST | `/{id}/complete` | Doctor | Mark as completed |
| POST | `/{id}/review` | Patient | Submit review after completion |

**Book appointment:**
```json
{
  "doctor_id": 5,
  "time_slot_id": 42,
  "consultation_type": "in_person",
  "symptoms": "Chest pain and shortness of breath for 2 days"
}
```

**Add prescription (doctor):**
```json
{
  "prescription": "Tab. Aspirin 75mg OD, Tab. Atorvastatin 20mg HS",
  "diagnosis": "Stable Angina",
  "follow_up_date": "2025-03-01"
}
```

**Submit review (patient):**
```json
{
  "rating": 4.5,
  "comment": "Very thorough and explained everything clearly",
  "is_anonymous": false
}
```

---

### 🔔 Notifications — `/api/v1/notifications`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Get all notifications |
| POST | `/{id}/read` | Mark one as read |
| POST | `/read-all` | Mark all as read |

---

### 🛡️ Admin — `/api/v1/admin`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/stats` | Platform stats |
| POST | `/doctors/{id}/verify` | Verify a doctor |
| POST | `/doctors/{id}/feature` | Feature/unfeature a doctor |

---

## 🏗️ Architecture: How Search Works

```
Client Request
     │
     ▼
FastAPI  ──► Redis Cache ──► Cache HIT? ──► Return instantly
     │              (miss)
     ▼
Elasticsearch ──► Available? ──► ES Query (fuzzy + geo + filters)
     │                 (down)
     ▼
PostgreSQL ──► pg_trgm ILIKE + composite indexes
     │
     ▼
Cache result in Redis (60s TTL)
     │
     ▼
Return to Client
```

**Search latency targets:**
- Cache hit: `< 1ms`
- Elasticsearch: `5–20ms`
- PostgreSQL fallback: `20–80ms`

---

## 🔒 Security

- Passwords hashed with **bcrypt** (cost factor 12)
- JWT **access tokens** expire in 24h; **refresh tokens** in 30 days
- Role-based access: `patient`, `doctor`, `admin`
- Row-level locking on slot booking (`SELECT ... FOR UPDATE`) — prevents double booking
- CORS configurable per environment

---

## 📊 Database Indexes

```sql
-- Fast city + specialization combo search
ix_doctor_city_spec (city, specialization_id)

-- Sorting
ix_doctor_rating    (avg_rating)
ix_doctor_fee       (consultation_fee)

-- Slot lookups
ix_slot_doctor_date (doctor_id, slot_date)

-- Appointment queries
ix_appt_patient     (patient_id)
ix_appt_doctor      (doctor_id)

-- Trigram index for ILIKE fuzzy search (pg_trgm)
ix_doctor_fullname_trgm  USING gin(city gin_trgm_ops)
```

---

## 🌱 Seed Data (quick test)

```python
# Run in Python shell after startup:
import httpx

base = "http://localhost:8000/api/v1"

# 1. Register admin
httpx.post(f"{base}/auth/register", json={
    "email": "admin@doctorfinder.in", "full_name": "Admin",
    "password": "admin1234", "role": "admin"
})

# 2. Create specialization
token = httpx.post(f"{base}/auth/login", json={"email":"admin@doctorfinder.in","password":"admin1234"}).json()["access_token"]
httpx.post(f"{base}/doctors/specializations",
    json={"name": "Cardiology", "description": "Heart specialist"},
    headers={"Authorization": f"Bearer {token}"}
)
```
