"""Initial migration

Revision ID: 0001_initial
Revises:
Create Date: 2024-01-01
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON

revision = '0001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Enable pg_trgm for fast LIKE/ILIKE search
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")

    # ── users ──────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id",              sa.Integer(), primary_key=True),
        sa.Column("email",           sa.String(255), nullable=False, unique=True),
        sa.Column("phone",           sa.String(20),  nullable=True),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name",       sa.String(255), nullable=False),
        sa.Column("role",            sa.String(20),  nullable=False, server_default="patient"),
        sa.Column("is_active",       sa.Boolean(),   server_default=sa.true()),
        sa.Column("is_verified",     sa.Boolean(),   server_default=sa.false()),
        sa.Column("created_at",      sa.DateTime(),  server_default=sa.func.now()),
        sa.Column("updated_at",      sa.DateTime(),  server_default=sa.func.now()),
    )
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_phone", "users", ["phone"])

    # ── specializations ────────────────────────────
    op.create_table(
        "specializations",
        sa.Column("id",          sa.Integer(), primary_key=True),
        sa.Column("name",        sa.String(200), nullable=False, unique=True),
        sa.Column("description", sa.Text(),      nullable=True),
        sa.Column("icon_url",    sa.String(500), nullable=True),
    )

    # ── doctor_profiles ────────────────────────────
    op.create_table(
        "doctor_profiles",
        sa.Column("id",                    sa.Integer(), primary_key=True),
        sa.Column("user_id",               sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), unique=True),
        sa.Column("specialization_id",     sa.Integer(), sa.ForeignKey("specializations.id")),
        sa.Column("registration_number",   sa.String(100), nullable=False, unique=True),
        sa.Column("gender",                sa.String(10)),
        sa.Column("date_of_birth",         sa.Date()),
        sa.Column("avatar_url",            sa.String(500)),
        sa.Column("bio",                   sa.Text()),
        sa.Column("languages",             JSON,  server_default="[]"),
        sa.Column("experience_years",      sa.Integer(), server_default="0"),
        sa.Column("qualifications",        JSON,  server_default="[]"),
        sa.Column("awards",                JSON,  server_default="[]"),
        sa.Column("publications",          JSON,  server_default="[]"),
        sa.Column("consultation_fee",      sa.Float(), nullable=False, server_default="500"),
        sa.Column("video_fee",             sa.Float()),
        sa.Column("follow_up_fee",         sa.Float()),
        sa.Column("clinic_name",           sa.String(255)),
        sa.Column("clinic_address",        sa.Text()),
        sa.Column("city",                  sa.String(100)),
        sa.Column("state",                 sa.String(100)),
        sa.Column("pincode",               sa.String(10)),
        sa.Column("latitude",              sa.Float()),
        sa.Column("longitude",             sa.Float()),
        sa.Column("available_for_video",   sa.Boolean(), server_default=sa.false()),
        sa.Column("available_for_home",    sa.Boolean(), server_default=sa.false()),
        sa.Column("accepting_new_patients",sa.Boolean(), server_default=sa.true()),
        sa.Column("avg_rating",            sa.Float(),   server_default="0"),
        sa.Column("total_reviews",         sa.Integer(), server_default="0"),
        sa.Column("total_patients",        sa.Integer(), server_default="0"),
        sa.Column("is_verified",           sa.Boolean(), server_default=sa.false()),
        sa.Column("is_featured",           sa.Boolean(), server_default=sa.false()),
        sa.Column("created_at",            sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at",            sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_doctor_city_spec", "doctor_profiles", ["city", "specialization_id"])
    op.create_index("ix_doctor_rating",    "doctor_profiles", ["avg_rating"])
    op.create_index("ix_doctor_fee",       "doctor_profiles", ["consultation_fee"])

    # Trigram indexes for fast ILIKE search on name/city
    op.execute("""
        CREATE INDEX ix_doctor_fullname_trgm
        ON doctor_profiles USING gin (city gin_trgm_ops)
    """)

    # ── Remaining tables (availability, time_slots, appointments, reviews, notifications)
    # ... (auto-created by SQLAlchemy create_tables in dev; add here for prod)


def downgrade():
    op.drop_table("doctor_profiles")
    op.drop_table("specializations")
    op.drop_table("users")