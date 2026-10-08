"""A Project's cover photo (spec #24): one file per Project in the photos folder,
named after the Project's id; the Project row only records its version."""

from pathlib import Path

from sqlalchemy.orm import Session

from pmp_backend.errors import NotFound, Refused
from pmp_backend.models import Project
from pmp_backend.services.projects import changeable_project, get_project

MAX_BYTES = 5 * 1024 * 1024
# The first bytes of each accepted format, by its media type.
SIGNATURES = {"image/jpeg": b"\xff\xd8\xff", "image/png": b"\x89PNG\r\n\x1a\n"}


class PhotoError(Refused):
    """A photo could not be saved as asked; the message is fit to show."""


class NoPhotoError(PhotoError, NotFound):
    pass


def _path(photos_dir: Path, project_id: int) -> Path:
    # Never the uploaded file name, so nothing outside the folder can be written.
    return photos_dir / str(project_id)


def _media_type(data: bytes) -> str | None:
    return next(
        (kind for kind, start in SIGNATURES.items() if data.startswith(start)), None
    )


def save_photo(
    session: Session, photos_dir: Path, project_id: int, data: bytes, content_type: str
) -> Project:
    """Give the Project this photo, replacing any earlier one. `data` may hold one
    byte more than allowed, so that a too large file is recognised."""
    project = changeable_project(session, project_id)
    if content_type not in SIGNATURES or _media_type(data) != content_type:
        raise PhotoError("Only JPG and PNG photos are accepted.")
    if len(data) > MAX_BYTES:
        raise PhotoError("The photo is larger than 5 MB.")
    photos_dir.mkdir(parents=True, exist_ok=True)
    # Written under another name first, so a failed write never replaces a photo.
    partial = photos_dir / f"{project_id}.partial"
    partial.write_bytes(data)
    partial.replace(_path(photos_dir, project_id))
    project.photo_version = (project.photo_version or 0) + 1
    session.commit()
    return project


def remove_photo(session: Session, photos_dir: Path, project_id: int) -> Project:
    project = changeable_project(session, project_id)
    project.photo_version = None
    session.commit()
    discard(photos_dir, project_id)
    return project


def discard(photos_dir: Path, project_id: int) -> None:
    """Delete the Project's photo file, if there is one."""
    _path(photos_dir, project_id).unlink(missing_ok=True)


def read_photo(
    session: Session, photos_dir: Path, project_id: int
) -> tuple[bytes, str]:
    """The photo's bytes and media type."""
    project = get_project(session, project_id)
    path = _path(photos_dir, project_id)
    if project.photo_version is None or not path.is_file():
        raise NoPhotoError(f"{project.title} has no photo.")
    data = path.read_bytes()
    return data, _media_type(data) or "application/octet-stream"
