from nicegui import ui

from pmp_frontend import api
from pmp_frontend.theme import frame


def _status_label(name: str, online: bool) -> None:
    color = "text-green-8" if online else "text-negative"
    ui.label(f"{name}: {'online' if online else 'offline'}").classes(color)


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
