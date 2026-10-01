from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "role IN ('superuser', 'teacher', 'student')", name="ck_users_role"
        ),
        # Emails are stored lower-cased so uniqueness is case-insensitive.
        CheckConstraint("email = lower(email)", name="ck_users_email_lowercase"),
        # Programme and Year belong to Students only, and every Student has both.
        CheckConstraint(
            "(role = 'student') = (programme IS NOT NULL AND year IS NOT NULL)",
            name="ck_users_student_fields",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(default=True)
    must_change_password: Mapped[bool] = mapped_column(default=True)
    programme: Mapped[str | None] = mapped_column(String(100))
    year: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
