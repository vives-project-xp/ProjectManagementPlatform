from pathlib import Path

from nicegui import ui

from pmp_frontend.pages import register_pages
from pmp_frontend.settings import Settings
from pmp_frontend.theme import register_static_files

settings = Settings()
# VIVES' own favicon (the red smile, as on vives.be), R18.
FAVICON = Path(__file__).parent / "static" / "favicon.ico"
register_static_files()
register_pages()

ui.run(
    host="0.0.0.0",
    port=8080,
    title="Project Management Platform | VIVES",
    favicon=FAVICON,
    reload=False,
    show=False,
    storage_secret=settings.storage_secret,
    # Lax (the default) keeps the cookie off requests other sites start, except
    # plain links; https_only adds the Secure flag.
    session_middleware_kwargs={
        "https_only": settings.secure_cookies,
        "same_site": "lax",
    },
)
