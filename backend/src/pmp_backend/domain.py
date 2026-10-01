"""Domain values from CONTEXT.md."""

from enum import StrEnum


class Role(StrEnum):
    SUPERUSER = "superuser"
    TEACHER = "teacher"
    STUDENT = "student"


class ProjectStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class Year(StrEnum):
    FIRST = "1"
    SECOND = "2"
    THIRD = "3"
    INTERNATIONAL = "International"
