from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from pmp_backend.domain import ProjectStatus


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
        # Only Students are Members (the single column already means: at most
        # one Project per Student).
        CheckConstraint(
            "project_id IS NULL OR role = 'student'", name="ck_users_project_student"
        ),
        # One GitHub account belongs to one User, whatever the capitalisation.
        Index(
            "uq_users_github_username_lower",
            func.lower(text("github_username")),
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    # As GitHub spells it (spec #49); None until the User saves one.
    github_username: Mapped[str | None] = mapped_column(String(39))
    role: Mapped[str] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(default=True)
    must_change_password: Mapped[bool] = mapped_column(default=True)
    programme: Mapped[str | None] = mapped_column(String(100))
    year: Mapped[str | None] = mapped_column(String(20))
    # The Project this Student is a Member of (Students only; see #9).
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    project: Mapped["Project | None"] = relationship(
        back_populates="members", foreign_keys=[project_id]
    )

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"


class Programme(Base):
    """A study programme in the list the Superuser manages (ADR 0004)."""

    __tablename__ = "programmes"
    __table_args__ = (
        Index("uq_programmes_name_lower", func.lower(text("name")), unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint(
            "team_size_min >= 1 AND team_size_min <= team_size_max",
            name="ck_projects_team_size",
        ),
        CheckConstraint("status IN ('active', 'archived')", name="ck_projects_status"),
        # Titles are unique regardless of case, Archived Projects included.
        Index("uq_projects_title_lower", func.lower(text("title")), unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    product_owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    team_size_min: Mapped[int]
    team_size_max: Mapped[int]
    status: Mapped[str] = mapped_column(String(20), default=ProjectStatus.ACTIVE.value)
    # Snapshot of the Members at archive time (name, Programme, Year); see #10.
    makers: Mapped[list[dict]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    # Null: no photo. Raised on every upload, so pages can bust caches (#29).
    photo_version: Mapped[int | None]
    # Students may pick it in their Top 3 (spec #37); never for Archived Projects.
    open_for_choice: Mapped[bool] = mapped_column(default=False, server_default=false())
    # Its GitHub repository (spec #49): the chosen name (None: suggested from the
    # title), and the id and URL once it exists.
    repo_name: Mapped[str | None] = mapped_column(String(100))
    github_repo_id: Mapped[int | None] = mapped_column(BigInteger)
    github_repo_url: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    product_owner: Mapped[User] = relationship(
        lazy="joined", foreign_keys=[product_owner_id]
    )
    # Every Top 3 place that names this Project (spec #37), loaded on access.
    top3_choices: Mapped[list["Top3Choice"]] = relationship(viewonly=True)
    # Deactivated Students stay Members and count towards the Team size.
    members: Mapped[list[User]] = relationship(
        back_populates="project",
        foreign_keys=[User.project_id],
        order_by=(User.last_name, User.first_name),
        lazy="selectin",
    )

    @property
    def member_count(self) -> int:
        return len(self.members)

    @property
    def team_size_label(self) -> str:
        """Members against the Team size, e.g. "3 / 4–6"."""
        return f"{self.member_count} / {self.team_size_min}–{self.team_size_max}"


class Top3Round(Base):
    """The one Top 3 round: open while its deadline is in the future."""

    __tablename__ = "top3_round"
    __table_args__ = (CheckConstraint("id = 1", name="ck_top3_round_single"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Top3Choice(Base):
    """One ranked place of a Student's Top 3. A deleted Project leaves
    `project_id` null: "no longer available"."""

    __tablename__ = "top3_choices"
    __table_args__ = (
        CheckConstraint("rank BETWEEN 1 AND 3", name="ck_top3_choices_rank"),
        UniqueConstraint("student_id", "project_id", name="uq_top3_choices_project"),
    )

    student_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    rank: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL")
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
