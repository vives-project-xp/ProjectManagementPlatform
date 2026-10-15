"""VIVES house style (Huisstijlgids 2024) shared by every page."""

from collections.abc import Callable
from contextlib import contextmanager, nullcontext
from datetime import date
from pathlib import Path

from nicegui import app, ui

VIVES_RED = "#e00020"
BLACK = "#1e1e1e"
SAND = "#efeee9"

STATIC_DIR = Path(__file__).parent / "static"

# VIVES' official accounts, as linked in the footer of vives.be (#76).
SOCIALS = [
    ("Instagram", "https://www.instagram.com/viveshogeschool"),
    ("TikTok", "https://www.tiktok.com/@viveshogeschool"),
    ("YouTube", "https://www.youtube.com/vivesvideo"),
    ("LinkedIn", "https://www.linkedin.com/school/vives/"),
]
PRIVACY_POLICY = "https://www.vives.be/nl/over-vives/privacyverklaring"
# Bootstrap Icons (MIT, see static/icons/LICENSE-bootstrap-icons.txt), inlined so
# they take the text colour and nothing loads from elsewhere.
ICONS_DIR = STATIC_DIR / "icons"
ADDRESS = "VIVES Brugge Xaverianenstraat · Xaverianenstraat 10, 8200 Brugge"

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
    with ui.column().classes("w-full max-w-4xl mx-auto p-6 gap-6"):
        yield
    footer()


def footer() -> None:
    """Black, with white text (house style): VIVES' socials, the campus address,
    the privacy policy and the copyright. Scrolls with the page."""
    with (
        ui.footer(fixed=False)
        .classes(f"bg-[{BLACK}] text-white px-6 py-4")
        .mark("footer")
    ):
        with ui.row().classes("w-full max-w-4xl mx-auto items-center gap-x-6 gap-y-2"):
            for label, url in SOCIALS:
                name = label.lower()
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
            ui.link("Privacy policy", PRIVACY_POLICY, new_tab=True).classes(
                "text-white"
            ).mark("footer-privacy")
        with ui.column().classes("w-full max-w-4xl mx-auto gap-0 text-caption"):
            ui.label(ADDRESS)
            ui.label(f"© {date.today().year} VIVES. All rights reserved.")
