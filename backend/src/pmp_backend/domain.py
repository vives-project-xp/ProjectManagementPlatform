"""Domain values from CONTEXT.md."""

from enum import StrEnum


class Role(StrEnum):
    SUPERUSER = "superuser"
    TEACHER = "teacher"
    STUDENT = "student"
    # Someone outside VIVES who follows Projects (spec #132).
    CLIENT = "client"


class ProjectStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class Year(StrEnum):
    FIRST = "1"
    SECOND = "2"
    THIRD = "3"
    INTERNATIONAL = "International"
