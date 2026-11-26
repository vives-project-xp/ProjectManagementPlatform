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
            "role IN ('superuser', 'teacher', 'student', 'client')",
            name="ck_users_role",
        ),
        # Only Clients have an Organisation (spec #132).
        CheckConstraint(
            "organisation IS NULL OR role = 'client'",
            name="ck_users_organisation_client",
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
    # Authentik's fixed id for this person, once they used VIVES login (#161).
    authentik_sub: Mapped[str | None] = mapped_column(String(255), unique=True)
    # As GitHub spells it (spec #49); None until the User saves one.
    github_username: Mapped[str | None] = mapped_column(String(39))
    # The 08:30 Daily email on days with deadlines or meetings (spec #68).
    daily_email: Mapped[bool] = mapped_column(default=True, server_default=true())
    # Browser notifications (spec #145): for new Chat messages (#148), and the
    # staff's TikTok alerts (#151).
    chat_notifications: Mapped[bool] = mapped_column(
        default=True, server_default=true()
    )
    tiktok_alerts: Mapped[bool] = mapped_column(default=True, server_default=true())
    role: Mapped[str] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(default=True)
    must_change_password: Mapped[bool] = mapped_column(default=True)
    programme: Mapped[str | None] = mapped_column(String(100))
    year: Mapped[str | None] = mapped_column(String(20))
    # A Client's company or institution, optional (spec #132).
    organisation: Mapped[str | None] = mapped_column(String(120))
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

    @property
    def display_name(self) -> str:
        """The name with a Client's Organisation: "Jan Peeters (Barco)"."""
        if self.organisation:
            return f"{self.full_name} ({self.organisation})"
        return self.full_name


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
    # When it was archived (null while Active): its Chat is deleted 6 months later.
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
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
    # The Clients who follow it (spec #132), by name.
    client_links: Mapped[list["ProjectClient"]] = relationship(
        lazy="selectin",
        viewonly=True,
    )

    @property
    def clients(self) -> list["ProjectClient"]:
        return sorted(
            self.client_links,
            key=lambda link: (link.client.last_name, link.client.first_name),
        )

    @property
    def member_count(self) -> int:
        return len(self.members)

    @property
    def team_size_label(self) -> str:
        """Members against the Team size, e.g. "3 / 4–6"."""
        return f"{self.member_count} / {self.team_size_min}–{self.team_size_max}"


class ProjectClient(Base):
    """A Client following a Project (spec #132, #134); at most one of a
    Project's Clients carries the Client Product Owner label."""

    __tablename__ = "project_clients"
    __table_args__ = (
        Index(
            "uq_project_clients_one_client_product_owner",
            "project_id",
            unique=True,
            postgresql_where=text("is_client_product_owner"),
        ),
    )

    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    client_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), primary_key=True, index=True
    )
    is_client_product_owner: Mapped[bool] = mapped_column(
        default=False, server_default=false()
    )

    client: Mapped[User] = relationship(lazy="joined")


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
    reactions: Mapped[list["ChatReaction"]] = relationship(
        lazy="selectin",
        order_by="ChatReaction.created_at",
        cascade="all, delete-orphan",
    )
    mentions: Mapped[list["ChatMention"]] = relationship(
        lazy="selectin", cascade="all, delete-orphan"
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


# The six emoji a Chat message can get as a reaction, in the order shown.
CHAT_REACTIONS = ("👍", "❤️", "😂", "😮", "😢", "🎉")


class ChatReaction(Base):
    """One User's emoji reaction to a Chat message; several per User allowed."""

    __tablename__ = "chat_reactions"
    __table_args__ = (
        CheckConstraint(
            "emoji IN (" + ", ".join(f"'{e}'" for e in CHAT_REACTIONS) + ")",
            name="ck_chat_reactions_emoji",
        ),
    )

    message_id: Mapped[int] = mapped_column(
        ForeignKey("chat_messages.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    emoji: Mapped[str] = mapped_column(String(8), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped[User] = relationship(lazy="joined")


class ChatMention(Base):
    """A Chat person mentioned in a message (@name, or @team for every Member
    at the time it was sent or edited)."""

    __tablename__ = "chat_mentions"

    message_id: Mapped[int] = mapped_column(
        ForeignKey("chat_messages.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True
    )


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


class SocialSettings(Base):
    """The social media settings (spec #110), one row, set by the Superuser; no
    row yet means the defaults. Weekday 0 is Monday, times are Belgian time."""

    __tablename__ = "social_settings"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_social_settings_single"),
        CheckConstraint(
            "upload_weekday BETWEEN 0 AND 6", name="ck_social_settings_weekday"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # The Upload deadline; both null until the Superuser sets it.
    upload_weekday: Mapped[int | None] = mapped_column(SmallInteger)
    upload_time: Mapped[time | None] = mapped_column(Time)
    # Instagram's Posting times: these weekdays, at these "HH:MM" times.
    instagram_weekdays: Mapped[list[int]] = mapped_column(JSONB)
    instagram_times: Mapped[list[str]] = mapped_column(JSONB)
    fixed_hashtags: Mapped[str] = mapped_column(String(500))
    # TikTok (spec #145): the videos' Posting times, the Weekly slideshow's
    # Posting time and its cut-off.
    tiktok_weekdays: Mapped[list[int]] = mapped_column(JSONB)
    tiktok_times: Mapped[list[str]] = mapped_column(JSONB)
    slideshow_weekday: Mapped[int] = mapped_column(SmallInteger)
    slideshow_time: Mapped[time] = mapped_column(Time)
    slideshow_cutoff_weekday: Mapped[int] = mapped_column(SmallInteger)
    slideshow_cutoff_time: Mapped[time] = mapped_column(Time)


class WeeklyUpdate(Base):
    """What a Project's team did in one Upload week, identified by the moment
    that week closes. `edited_by_id` null after that User was deleted."""

    __tablename__ = "weekly_updates"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "closes_at", name="uq_weekly_updates_project_week"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE")
    )
    closes_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    text: Mapped[str] = mapped_column(Text)
    edited_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    edited_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # When the never-posted Media were deleted, 4 months after the week (#118).
    media_removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    edited_by: Mapped[User | None] = relationship(lazy="joined")
    media: Mapped[list["WeeklyMedium"]] = relationship(
        order_by="WeeklyMedium.id", lazy="selectin", passive_deletes=True
    )
    suggestion: Mapped["PostSuggestion | None"] = relationship(
        lazy="selectin", viewonly=True
    )


class WeeklyMedium(Base):
    """A photo (or, from #113, the video) of a Weekly update, stored as a file
    named after its id. `uploaded_by_id` null after that User was deleted;
    `posted` once it was part of a published post (never cleaned up)."""

    __tablename__ = "weekly_media"
    __table_args__ = (
        CheckConstraint("kind IN ('photo', 'video')", name="ck_weekly_media_kind"),
        CheckConstraint(
            "state IN ('processing', 'ready', 'failed')", name="ck_weekly_media_state"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    weekly_update_id: Mapped[int] = mapped_column(
        ForeignKey("weekly_updates.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(10))
    size: Mapped[int] = mapped_column(BigInteger)
    width: Mapped[int] = mapped_column()
    height: Mapped[int] = mapped_column()
    # The Quality check's sharpness; the AI gets the best photos.
    quality_score: Mapped[float | None] = mapped_column()
    # A video is "processing" until both copies are made (#113).
    state: Mapped[str] = mapped_column(
        String(12), default="ready", server_default="ready"
    )
    seconds: Mapped[float | None] = mapped_column()
    uploaded_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    posted: Mapped[bool] = mapped_column(default=False, server_default=false())

    uploaded_by: Mapped[User | None] = relationship(lazy="joined")
    # The Weekly slideshows it is in (#150).
    slideshow_photos: Mapped[list["WeeklySlideshowPhoto"]] = relationship(
        lazy="selectin", viewonly=True
    )


class PostSuggestion(Base):
    """What the AI (or a reviewer) proposes to post for one Weekly update
    (spec #110). `chosen_medium_id` and the `ranking` of medium ids point at
    the Weekly update's Media."""

    __tablename__ = "post_suggestions"
    __table_args__ = (
        CheckConstraint(
            "state IN ('generating', 'waiting', 'failed', 'refused', 'scheduled', "
            "'published', 'to_post_by_hand', 'posted_by_hand')",
            name="ck_post_suggestions_state",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    weekly_update_id: Mapped[int] = mapped_column(
        ForeignKey("weekly_updates.id", ondelete="CASCADE"), unique=True
    )
    state: Mapped[str] = mapped_column(String(20), default="generating")
    title: Mapped[str | None] = mapped_column(String(200))
    caption: Mapped[str | None] = mapped_column(Text)
    chosen_medium_id: Mapped[int | None] = mapped_column(
        ForeignKey("weekly_media.id", ondelete="SET NULL")
    )
    ranking: Mapped[list[int]] = mapped_column(JSONB, default=list)
    why: Mapped[str | None] = mapped_column(Text)
    # Failed tries of the AI; after 3 the state is "failed".
    attempts: Mapped[int] = mapped_column(default=0)
    last_error: Mapped[str | None] = mapped_column(String(500))
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # The Review (#115): who last edited, refused or regenerated it, and when;
    # null reviewer after that User was deleted.
    reviewed_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    refusal_reason: Mapped[str | None] = mapped_column(String(500))
    # Planning (#116): when it was Posted (its place in the Channel's line) and
    # the Posting time it got; who posted it by hand, and when.
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    posted_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Automatic publishing (#117): failed tries, when the retry is due, the
    # last error, and the post's Instagram link once published (posted_at is
    # then the moment it was published).
    publish_attempts: Mapped[int] = mapped_column(default=0, server_default="0")
    publish_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    publish_error: Mapped[str | None] = mapped_column(String(500))
    published_url: Mapped[str | None] = mapped_column(String(500))

    weekly_update: Mapped[WeeklyUpdate] = relationship(lazy="joined")
    reviewed_by: Mapped[User | None] = relationship(
        lazy="joined", foreign_keys=[reviewed_by_id]
    )
    posted_by: Mapped[User | None] = relationship(
        lazy="joined", foreign_keys=[posted_by_id]
    )
    # Its post on TikTok when the reviewer ticked Also on TikTok (#147).
    tiktok_post: Mapped["TikTokPost | None"] = relationship(
        lazy="selectin", viewonly=True
    )


class TikTokPost(Base):
    """A Post suggestion's video on TikTok (spec #145, #147): Posted with Also
    on TikTok ticked, with its own Posting time and state next to the
    Instagram post. Pulled back means the row is deleted."""

    __tablename__ = "tiktok_posts"
    __table_args__ = (
        CheckConstraint(
            "state IN ('scheduled', 'published', 'to_post_by_hand', 'posted_by_hand')",
            name="ck_tiktok_posts_state",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    suggestion_id: Mapped[int] = mapped_column(
        ForeignKey("post_suggestions.id", ondelete="CASCADE"), unique=True
    )
    # The Weekly update's video; null once it was deleted.
    medium_id: Mapped[int | None] = mapped_column(
        ForeignKey("weekly_media.id", ondelete="SET NULL")
    )
    state: Mapped[str] = mapped_column(String(20), default="scheduled")
    # The reviewer's choices for TikTok (from TikTok's creator info).
    privacy_level: Mapped[str] = mapped_column(String(40))
    allow_comment: Mapped[bool] = mapped_column(default=True)
    allow_duet: Mapped[bool] = mapped_column(default=False)
    allow_stitch: Mapped[bool] = mapped_column(default=False)
    # Its place in TikTok's line and the Posting time it got.
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Publishing: failed tries, the retry, the last error, TikTok's publish id
    # and the post's link once public.
    attempts: Mapped[int] = mapped_column(default=0)
    retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(String(500))
    publish_id: Mapped[str | None] = mapped_column(String(100))
    published_url: Mapped[str | None] = mapped_column(String(500))
    # Published automatically (posted_at) or by hand (posted_by too).
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    posted_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    suggestion: Mapped[PostSuggestion] = relationship(lazy="joined")
    posted_by: Mapped[User | None] = relationship(lazy="joined")


class WeeklySlideshow(Base):
    """TikTok's photo post of one Upload week (spec #145, #149): put together
    at the Slideshow cut-off from the Projects Posted that week, with a title
    and caption the AI writes, reviewed by any Teacher or the Superuser.
    `closes_at` is the Upload week's closing moment."""

    __tablename__ = "weekly_slideshows"
    __table_args__ = (
        CheckConstraint(
            "state IN ('generating', 'waiting', 'failed', 'refused', 'none', "
            "'scheduled', 'in_inbox', 'to_post_by_hand', 'posted', 'dropped')",
            name="ck_weekly_slideshows_state",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    closes_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), unique=True)
    # "generating" (the AI is writing), "waiting" (for Review), "failed" (the
    # AI couldn't), "refused", or "none" (no Posted Project had a photo); once
    # Posted (#150): "scheduled", "in_inbox" (waiting in the TikTok app for
    # its song), "to_post_by_hand", "posted"; "dropped" when it wasn't Posted
    # by the next cut-off.
    state: Mapped[str] = mapped_column(String(20))
    title: Mapped[str | None] = mapped_column(String(200))
    caption: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(default=0)
    last_error: Mapped[str | None] = mapped_column(String(500))
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    reviewed_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    refusal_reason: Mapped[str | None] = mapped_column(String(500))
    # Posting (#150): when it was Posted and its Posting time; publishing tries,
    # the retry, the last error and TikTok's publish id; who marked it posted
    # (after the Song check), and when.
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    publish_attempts: Mapped[int] = mapped_column(default=0, server_default="0")
    publish_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    publish_error: Mapped[str | None] = mapped_column(String(500))
    publish_id: Mapped[str | None] = mapped_column(String(100))
    posted_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    photos: Mapped[list["WeeklySlideshowPhoto"]] = relationship(
        lazy="selectin",
        order_by="WeeklySlideshowPhoto.position",
        viewonly=True,
    )
    reviewed_by: Mapped[User | None] = relationship(
        lazy="joined", foreign_keys=[reviewed_by_id]
    )
    posted_by: Mapped[User | None] = relationship(
        lazy="joined", foreign_keys=[posted_by_id]
    )


class WeeklySlideshowPhoto(Base):
    """One photo of a Weekly slideshow, in order (#149)."""

    __tablename__ = "weekly_slideshow_photos"

    slideshow_id: Mapped[int] = mapped_column(
        ForeignKey("weekly_slideshows.id", ondelete="CASCADE"), primary_key=True
    )
    medium_id: Mapped[int] = mapped_column(
        ForeignKey("weekly_media.id", ondelete="CASCADE"), primary_key=True
    )
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column()

    slideshow: Mapped[WeeklySlideshow] = relationship(lazy="joined", viewonly=True)


class PublishLink(Base):
    """A short-lived public link to one Medium of one Scheduled post, for the
    Channel to download it from (ADR 0010): valid until `expires_at` or until
    that post is published (the link is then deleted)."""

    __tablename__ = "publish_links"

    # Random, at least 128 bits (secrets.token_urlsafe).
    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    # A Scheduled post's, or (#150) a Weekly slideshow's.
    suggestion_id: Mapped[int | None] = mapped_column(
        ForeignKey("post_suggestions.id", ondelete="CASCADE"), index=True
    )
    slideshow_id: Mapped[int | None] = mapped_column(
        ForeignKey("weekly_slideshows.id", ondelete="CASCADE"), index=True
    )
    medium_id: Mapped[int] = mapped_column(
        ForeignKey("weekly_media.id", ondelete="CASCADE")
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ChannelToken(Base):
    """A Channel's long-lived access token (#117), refreshed before it expires;
    never returned by the API. First taken from the settings (INSTAGRAM_TOKEN)."""

    __tablename__ = "channel_tokens"

    channel: Mapped[str] = mapped_column(String(20), primary_key=True)
    token: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Why the last refresh failed; null after a successful one.
    refresh_error: Mapped[str | None] = mapped_column(String(500))
    # TikTok (#146): the refresh token and its expiry, the connected account's
    # name and when the Superuser connected it; null for Instagram.
    refresh_token: Mapped[str | None] = mapped_column(Text)
    refresh_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    account_name: Mapped[str | None] = mapped_column(String(200))
    connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
