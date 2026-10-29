"""VIVES house style (Huisstijlgids 2024) shared by every page."""

from collections.abc import Callable
from contextlib import contextmanager, nullcontext
from datetime import date
from pathlib import Path

from nicegui import app, ui

from pmp_frontend.settings import Settings

VIVES_RED = "#e00020"
BLACK = "#1e1e1e"
SAND = "#efeee9"

STATIC_DIR = Path(__file__).parent / "static"

# Wide enough for the tables on a laptop screen (#89); forms keep their own
# narrow cards.
CONTENT_WIDTH = "max-w-7xl"
# Table column classes for long values without spaces, such as email addresses.
BREAK_ANYWHERE = "break-anywhere"

# The footer's social links; their URLs come from the settings (#79).
SOCIALS = ["Instagram", "TikTok", "YouTube", "LinkedIn"]
# Bootstrap Icons (MIT, see static/icons/LICENSE-bootstrap-icons.txt), inlined so
# they take the text colour and nothing loads from elsewhere.
ICONS_DIR = STATIC_DIR / "icons"

# Poppins is the primary typeface; the guide never uses weights above semibold (600).
_HEAD_HTML = f"""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600&display=swap"
      rel="stylesheet">
<style>
  body {{
    font-family: 'Poppins', Arial, sans-serif; color: {BLACK}; background: {SAND};
  }}
  b, strong, h1, h2, h3, h4, .text-bold {{ font-weight: 600 !important; }}
  /* Tables fit the screen instead of scrolling sideways (#89): cells wrap
     between words; columns with BREAK_ANYWHERE (email addresses) anywhere. */
  .q-table td {{ white-space: normal; }}
  .q-table td.break-anywhere {{ overflow-wrap: anywhere; }}
  /* Links in Chat messages look like links (text colour, underlined). */
  .chat-text a {{ color: inherit; text-decoration: underline; }}
</style>
"""


def register_static_files() -> None:
    app.add_static_files("/static", STATIC_DIR)


@contextmanager
def frame(
    title: str, header: Callable[[], None] | None = None, home: str | None = None
):
    """Page layout: white header with the VIVES logo, content on a sand background.

    `header` adds content (navigation, the User's name) to the right of the logo;
    with `home`, the logo is a link to that page.
    """
    ui.colors(primary=VIVES_RED, dark=BLACK)
    ui.add_head_html(_HEAD_HTML)
    ui.page_title(f"{title} | VIVES")
    with ui.header().classes("bg-white text-dark items-center px-6 py-3 shadow-sm"):
        with ui.link(target=home) if home else nullcontext() as link:
            # The guide asks for clear space of one smile height around the logo.
            ui.image("/static/vives-logo.png").props("fit=contain no-spinner").classes(
                "w-40 h-10"
            ).mark("logo")
        if link is not None:
            link.mark("logo")
        if header is not None:
            ui.space()
            header()
    with ui.column().classes(f"w-full {CONTENT_WIDTH} mx-auto p-6 gap-6"):
        yield
    footer()


def footer() -> None:
    """Black, with white text (house style): VIVES' socials, the campus address,
    the privacy policy and the copyright. Scrolls with the page. The links and
    the address come from the settings, so they change without a new release."""
    settings = Settings()
    with (
        ui.footer(fixed=False)
        .classes(f"bg-[{BLACK}] text-white px-6 py-4")
        .mark("footer")
    ):
        with ui.row().classes(
            f"w-full {CONTENT_WIDTH} mx-auto items-center gap-x-6 gap-y-2"
        ):
            for label in SOCIALS:
                name = label.lower()
                url = getattr(settings, f"footer_{name}")
                if not url:
                    continue
                with (
                    ui.link(target=url, new_tab=True)
                    .classes("text-white flex items-center gap-1")
                    .mark(f"footer-{name}")
                ):
                    # Our own files, so no sanitising needed.
                    ui.html(
                        (ICONS_DIR / f"{name}.svg").read_text(encoding="utf-8"),
                        sanitize=False,
                    ).classes("flex").mark(f"icon-{name}")
                    ui.label(label)
            ui.space()
            if settings.footer_privacy_url:
                ui.link(
                    "Privacy policy", settings.footer_privacy_url, new_tab=True
                ).classes("text-white").mark("footer-privacy")
        with ui.column().classes(f"w-full {CONTENT_WIDTH} mx-auto gap-0 text-caption"):
            if settings.footer_address:
                ui.label(settings.footer_address)
            ui.label(f"© {date.today().year} VIVES. All rights reserved.")
