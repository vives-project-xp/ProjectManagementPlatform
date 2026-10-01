from nicegui import ui

from pmp_frontend.pages import register_pages
from pmp_frontend.settings import Settings
from pmp_frontend.theme import register_static_files

register_static_files()
register_pages()

ui.run(
    host="0.0.0.0",
    port=8080,
    title="Project Management Platform | VIVES",
    reload=False,
    show=False,
    storage_secret=Settings().storage_secret,
)
