"""The 08:30 Daily email (spec #68): one email per person on a day with
deadlines or meetings for them, sent once, catching up until 18:00."""

import asyncio
import ipaddress
import logging
from datetime import UTC, datetime, time
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from pmp_backend.domain import ProjectStatus
from pmp_backend.models import DailyEmailSent, Project, User
from pmp_backend.services import mail
from pmp_backend.services.mail import Mailer
from pmp_backend.services.planning import BRUSSELS, DEADLINE, AgendaItem, items_on
from pmp_backend.settings import Settings

log = logging.getLogger(__name__)

SEND_FROM = time(8, 30)
# After this, a missed email is no longer worth sending.
SEND_UNTIL = time(18, 0)
EVERY_SECONDS = 5 * 60


def _line(item: AgendaItem) -> str:
    start = item.starts_at.astimezone(BRUSSELS).strftime("%H:%M")
    if item.kind == DEADLINE:
        line = f"- {start} Deadline: {item.title}"
    else:
        end = item.ends_at.astimezone(BRUSSELS).strftime("%H:%M")
        line = f"- {start}–{end} {item.title} · {item.place}"
    if item.details:
        line += f"\n  {item.details}"
    return line


def _where(site_url: str) -> str:
    """Where to look: a link, but not to a bare IP address, which spam filters
    distrust; the link appears once the site has a hostname."""
    host = urlsplit(site_url).hostname or ""
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return f"See your planning on {site_url}"
    return "Open the Project Management Platform to see your planning."


def _body(user: User, per_project: dict[str, list[AgendaItem]], site_url: str) -> str:
    parts = [f"Hello {user.first_name},", ""]
    for title, items in per_project.items():
        parts.append(f"Today for {title}:")
        parts += [_line(item) for item in items]
        parts.append("")
    parts += [
        _where(site_url),
        "",
        "You get this email on days with deadlines or meetings. You can switch it "
        "off on My account.",
    ]
    return "\n".join(parts)


def _recipients(session: Session, day) -> dict[int, tuple[User, dict]]:
    """Per User with the Daily email on: what each of their Active Projects has
    on `day` (active Members and the Product Owner only)."""
    recipients: dict[int, tuple[User, dict[str, list[AgendaItem]]]] = {}
    projects = session.scalars(
        select(Project).where(Project.status == ProjectStatus.ACTIVE.value)
    )
    for project in projects:
        items = items_on(session, project, day)
        if not items:
            continue
        for user in [*project.members, project.product_owner]:
            if user.is_active and user.daily_email:
                _, per_project = recipients.setdefault(user.id, (user, {}))
                per_project[project.title] = items
    return recipients


def send_daily_emails(
    session: Session, mailer: Mailer, settings: Settings, now: datetime
) -> int:
    """Send today's Daily emails that weren't sent yet, between 08:30 and 18:00
    Belgian time; how many were sent. A failing address is logged and tried
    again on the next run."""
    local = now.astimezone(BRUSSELS)
    if not mail.is_configured(settings) or not SEND_FROM <= local.time() < SEND_UNTIL:
        return 0
    day = local.date()
    already = set(
        session.scalars(select(DailyEmailSent.user_id).where(DailyEmailSent.day == day))
    )
    sent = 0
    for user_id, (user, per_project) in _recipients(session, day).items():
        if user_id in already:
            continue
        try:
            mailer.send(
                user.email,
                f"Your planning for today, {day:%A %d/%m/%Y}",
                _body(user, per_project, settings.site_url),
            )
        except Exception:
            log.exception("The daily email to %s could not be sent", user.email)
            continue
        session.add(DailyEmailSent(user_id=user_id, day=day))
        # Saved one by one, so a crash never sends anyone's email twice.
        session.commit()
        sent += 1
    return sent


async def run_forever(
    make_session: sessionmaker, mailer: Mailer, settings: Settings
) -> None:
    """Every 5 minutes, send what is due; never crashes the backend."""

    def run_once() -> None:
        with make_session() as session:
            send_daily_emails(session, mailer, settings, datetime.now(UTC))

    while True:
        try:
            # SMTP and the database block, so off the event loop.
            await asyncio.to_thread(run_once)
        except Exception:
            log.exception("The daily email run failed")
        await asyncio.sleep(EVERY_SECONDS)
