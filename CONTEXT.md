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
The only User who creates, edits, deactivates and deletes other Users and resets their passwords. The Superuser can never be deleted.
_Avoid_: Admin

**Teacher**:
A VIVES staff member who creates and manages Projects.
_Avoid_: Coach, docent, lecturer

**Student**:
A User who can work in a Project, described by their Programme and Year.
_Avoid_: Pupil, participant

**Deactivated User**:
A User who can no longer log in but is kept, together with their links to Projects. The way to retire a User who is linked to a Project.
_Avoid_: Removed user

**Deleted User**:
A Student or Teacher removed for good by the Superuser, typically one created by mistake. Only possible while the User is not linked to any Project: not a Member, not in any Makers, and not the Product Owner of any Project (Active or Archived); otherwise they are deactivated instead. Their session ends at once and their email is free again.
_Avoid_: Deactivated user (that User is kept)

**Temporary password**:
A password set by the Superuser that the User must replace at their next login.
_Avoid_: Default password, reset code

**Starting account**:
One of the three Users (one per Role) created from the deployment's `logins.txt` the first time the backend starts, never overwritten afterwards; its password from that file counts as a Temporary password. Starting accounts are only created while there are no Users at all, so editing or deleting one never brings the original back. The only sanctioned use of "account" for a User.
_Avoid_: Default user, seed user, admin account

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
The permanent record of the Students (name, Programme, Year) who were Members of a Project when it was archived. Nobody is ever removed from it: archiving a restored Project again only adds the new Members (a Student already listed is not added twice). Shown as "Made by".
_Avoid_: History, former members, credits

**Programme**:
The VIVES study programme a Student is enrolled in, picked from the list the Superuser manages. Renaming a Programme renames it for every User, but not in Makers; a Programme can only be removed while no User has it.
_Avoid_: Course, study course, opleiding

**Year**:
Where a Student stands in their Programme: 1, 2, 3, or International for exchange students who belong to no year.
_Avoid_: Level, grade
