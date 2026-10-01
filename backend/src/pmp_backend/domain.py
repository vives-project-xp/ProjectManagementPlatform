"""Domain values from CONTEXT.md."""

from enum import StrEnum


class Role(StrEnum):
    SUPERUSER = "superuser"
    TEACHER = "teacher"
    STUDENT = "student"


class Programme(StrEnum):
    # Fixed list in code for the MVP (ADR 0004).
    ELECTRONICS_ICT = "Electronics-ICT"


class Year(StrEnum):
    FIRST = "1"
    SECOND = "2"
    THIRD = "3"
    INTERNATIONAL = "International"
