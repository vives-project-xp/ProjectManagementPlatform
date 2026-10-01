from nicegui import ui

from pmp_frontend import api
from pmp_frontend.theme import frame


def _status_label(name: str, online: bool) -> None:
    # Text stays black (house style); only the icon signals status, in VIVES red
    # when something is offline.
    with ui.row().classes("items-center gap-2"):
        if online:
            ui.icon("check_circle", color="dark")
        else:
            ui.icon("error", color="primary")
        ui.label(f"{name}: {'online' if online else 'offline'}")


def register_pages() -> None:
    @ui.page("/")
    async def start_page() -> None:
        with frame("Project Management Platform"):
            ui.label("Project Management Platform").classes("text-h4")
            ui.label("VIVES Project Experience").classes("text-subtitle1")
            health = await api.get_health()
            with ui.card().classes("w-full"):
                ui.label("System status").classes("text-h6")
                _status_label("Backend", health.backend_online)
                _status_label("Database", health.database_online)
