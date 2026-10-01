# Project Management Platform

A web application for VIVES Project Experience in which staff set up and follow up student projects, and students take part in them.

## Language

### People

**User**:
Anyone with a login on the platform. Every User has exactly one Role.
_Avoid_: Account, member (for people without a Project)

**Role**:
The platform-wide kind of User: Superuser, Teacher or Student.
_Avoid_: Permission level, user type

**Superuser**:
The only User who creates, edits and deactivates other Users and resets their passwords.
_Avoid_: Admin

**Teacher**:
A VIVES staff member who creates and manages Projects.
_Avoid_: Coach, docent, lecturer

**Student**:
A User who can work in a Project, described by their Programme and Year.
_Avoid_: Pupil, participant

**Deactivated User**:
A User who can no longer log in but is kept, together with their links to Projects; Users are never deleted.
_Avoid_: Deleted user, removed user

**Temporary password**:
A password set by the Superuser that the User must replace at their next login.
_Avoid_: Default password, reset code

### Projects

**Project**:
A piece of work a team of Students carries out for its Product Owner.
_Avoid_: Assignment, task

**Product Owner**:
The Teacher who owns a Project; every Project has exactly one, and one Teacher can be the Product Owner of many Projects.
_Avoid_: PO (in UI text), coach, project lead

**Member**:
A Student assigned to a Project. A Student is a Member of at most one Project at a time.
_Avoid_: Team member, participant

**Team size**:
The minimum and maximum number of Members a Project wants.
_Avoid_: Capacity, group size

**Archived Project**:
A finished Project, kept read-only for the history overview. Archiving frees its Students, and restoring it does not bring them back.
_Avoid_: Deleted project, closed project, historical project

**Makers**:
The fixed record of the Students (name, Programme, Year) who were Members of a Project at the moment it was archived; it never changes afterwards.
_Avoid_: History, former members, credits

**Programme**:
The VIVES study programme a Student is enrolled in, picked from a list.
_Avoid_: Course, study course, opleiding

**Year**:
Where a Student stands in their Programme: 1, 2, 3, or International for exchange students who belong to no year.
_Avoid_: Level, grade
