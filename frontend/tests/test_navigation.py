import pytest
from nicegui import ui
from nicegui.testing import User

from tests.conftest import log_in, ready_to_work


def logo_link(user: User) -> ui.link | None:
    found = user.find(marker="logo").elements
    return next((e for e in found if isinstance(e, ui.link)), None)


def navigation_icons(user: User) -> set[str]:
    icons = {icon.props.get("name") for icon in user.find(kind=ui.icon).elements}
    buttons = user.find(kind=ui.button).elements
    icons |= {button.props.get("icon") for button in buttons}
    return icons - {None}


@pytest.mark.parametrize(
    ("role", "home"),
    [("superuser", "/users"), ("teacher", "/projects"), ("student", "/my-project")],
)
async def test_logo_leads_to_the_roles_home_screen(user: User, role: str, home: str):
    await ready_to_work(user, role)
    await user.open("/account")
    await user.should_see("Change your password")

    link = logo_link(user)

    assert link is not None
    assert link.props["href"] == home


async def test_logo_is_no_link_before_logging_in(user: User):
    await user.open("/login")
    await user.should_see(marker="log-in")

    assert logo_link(user) is None


async def test_logo_is_no_link_during_the_forced_password_change(user: User):
    await log_in(user, "teacher")
    await user.should_see("Choose a new password of your own before you continue.")

    assert logo_link(user) is None


@pytest.mark.parametrize(
    ("role", "icons"),
    [
        (
            "superuser",
            {
                "group",
                "folder",
                "badge",
                "format_list_numbered",
                "account_circle",
                "logout",
            },
        ),
        (
            "teacher",
            {"folder", "badge", "format_list_numbered", "account_circle", "logout"},
        ),
        ("student", {"work", "account_circle", "logout"}),
    ],
)
async def test_navigation_items_have_icons(user: User, role: str, icons: set[str]):
    await ready_to_work(user, role)

    assert icons <= navigation_icons(user)


async def test_every_page_has_the_vives_footer(user: User):
    await user.open("/login")
    await user.should_see(marker="footer", retries=30)

    await user.should_see("Xaverianenstraat 10, 8200 Brugge")
    await user.should_see("VIVES. All rights reserved.")
    expected = {
        "footer-instagram": "https://www.instagram.com/viveshogeschool",
        "footer-tiktok": "https://www.tiktok.com/@viveshogeschool",
        "footer-youtube": "https://www.youtube.com/vivesvideo",
        "footer-linkedin": "https://www.linkedin.com/school/vives/",
        "footer-privacy": "https://www.vives.be/nl/over-vives/privacyverklaring",
    }
    for marker, url in expected.items():
        link = user.find(marker=marker).elements.pop()
        assert isinstance(link, ui.link)
        assert link.props["href"] == url
        assert link.props["target"] == "_blank"
    for name in ("instagram", "tiktok", "youtube", "linkedin"):
        icon = user.find(marker=f"icon-{name}").elements.pop()
        assert isinstance(icon, ui.html)
        assert f"bi-{name}" in icon.content

    await ready_to_work(user, "student")
    await user.should_see(marker="footer", retries=30)
