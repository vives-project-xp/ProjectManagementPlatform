from datetime import date, datetime, time

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Sequence,
    SmallInteger,
    String,
    Text,
    Time,
    UniqueConstraint,
    false,
    func,
    text,
    true,
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
    # The 08:30 Daily email on days with deadlines or meetings (spec #68).
    daily_email: Mapped[bool] = mapped_column(default=True, server_default=true())
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
    # Its own Trello Workspace and board (spec #61), once they exist.
    trello_workspace_id: Mapped[str | None] = mapped_column(String(64))
    trello_board_id: Mapped[str | None] = mapped_column(String(64))
    trello_board_url: Mapped[str | None] = mapped_column(String(300))
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


class RepoGrant(Base):
    """A GitHub account the platform itself invited to a Project's repository
    (lower-cased), so "Check members" may take its access back (spec #49)."""

    __tablename__ = "repo_grants"
    __table_args__ = (
        CheckConstraint("login = lower(login)", name="ck_repo_grants_login_lower"),
    )

    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    login: Mapped[str] = mapped_column(String(39), primary_key=True)


class TrelloGrant(Base):
    """A Trello member the platform itself invited to a Project's board, and the
    User and email it was for (spec #61): Trello never shows email addresses, so
    this is how "Check members" knows who is who and whom it may remove. A
    Deleted User leaves `user_id` null."""

    __tablename__ = "trello_grants"

    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    trello_member_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    email: Mapped[str] = mapped_column(String(254))


class Deadline(Base):
    """A Deadline (spec #68): for one Project, or for every Active Project when
    `project_id` is null."""

    __tablename__ = "deadlines"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    project: Mapped[Project | None] = relationship()


class Meeting(Base):
    """A one-off Meeting of a Project's team (spec #68)."""

    __tablename__ = "meetings"
    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="ck_meetings_end_after_start"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # A room, or a link to an online meeting.
    place: Mapped[str] = mapped_column(String(500))
    note: Mapped[str | None] = mapped_column(Text)

    project: Mapped[Project] = relationship()


class WeeklySlot(Base):
    """A Project's fixed Weekly slot (spec #68): weekday 0 is Monday, the times
    are Belgian time."""

    __tablename__ = "weekly_slots"
    __table_args__ = (
        CheckConstraint("weekday BETWEEN 0 AND 6", name="ck_weekly_slots_weekday"),
        CheckConstraint("ends > starts", name="ck_weekly_slots_end_after_start"),
    )

    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    weekday: Mapped[int] = mapped_column(SmallInteger)
    starts: Mapped[time] = mapped_column(Time)
    ends: Mapped[time] = mapped_column(Time)
    place: Mapped[str] = mapped_column(String(500))

    project: Mapped[Project] = relationship()
    skips: Mapped[list["WeeklySlotSkip"]] = relationship(
        order_by="WeeklySlotSkip.day", cascade="all, delete-orphan", lazy="selectin"
    )


class WeeklySlotSkip(Base):
    """A date on which the Weekly slot doesn't take place."""

    __tablename__ = "weekly_slot_skips"

    project_id: Mapped[int] = mapped_column(
        ForeignKey("weekly_slots.project_id", ondelete="CASCADE"), primary_key=True
    )
    day: Mapped[date] = mapped_column(Date, primary_key=True)


class DailyEmailSent(Base):
    """Who already got the Daily email of a day, so nobody gets it twice."""

    __tablename__ = "daily_emails_sent"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    day: Mapped[date] = mapped_column(Date, primary_key=True)


# Numbers every change to a Chat message (sent, edited, deleted), so an open
# Chat can ask for everything that changed since the last number it saw.
chat_revision = Sequence("chat_revision")


class ChatMessage(Base):
    """A message in a Project's Chat (spec #91). A Deleted User leaves
    `author_id` null: shown as "Deleted user". A deleted message keeps its row
    (without text or files), so replies can say the original was deleted."""

    __tablename__ = "chat_messages"
    __table_args__ = (
        CheckConstraint("char_length(body) <= 4000", name="ck_chat_messages_length"),
        Index("ix_chat_messages_project_revision", "project_id", "revision"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    author_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    body: Mapped[str] = mapped_column(Text)
    reply_to_id: Mapped[int | None] = mapped_column(
        ForeignKey("chat_messages.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revision: Mapped[int] = mapped_column(
        BigInteger, chat_revision, server_default=chat_revision.next_value()
    )

    author: Mapped[User | None] = relationship(lazy="joined")
    reply_to: Mapped["ChatMessage | None"] = relationship(
        remote_side="ChatMessage.id", lazy="joined", join_depth=1
    )
    files: Mapped[list["ChatFile"]] = relationship(
        lazy="selectin", order_by="ChatFile.id", cascade="all, delete-orphan"
    )


class ChatFile(Base):
    """A photo or file attached to a Chat message. Its bytes live in the chat
    files folder, at <project id>/<file id>; the row keeps the uploaded name."""

    __tablename__ = "chat_files"

    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[int] = mapped_column(
        ForeignKey("chat_messages.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    size: Mapped[int]
    # An image/... type for accepted photos; otherwise application/octet-stream.
    media_type: Mapped[str] = mapped_column(String(100))


class ChatRead(Base):
    """How far a User has read a Project's Chat: the last message they saw.
    Messages after it are Unread for them."""

    __tablename__ = "chat_reads"

    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    last_read_id: Mapped[int] = mapped_column(default=0)


class ChatGuest(Base):
    """A Guest in a Project's Chat: any User added by the Product Owner, a
    Teacher or the Superuser, on top of the Members and the Product Owner."""

    __tablename__ = "chat_guests"

    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped[User] = relationship(lazy="joined")
