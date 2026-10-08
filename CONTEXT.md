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

**GitHub username**:
The GitHub account a User saved, confirmed by its profile picture and name and stored as GitHub spells it. One account belongs to one User (ignoring case). It decides who gets access to a Project repository.
_Avoid_: GitHub login, GitHub handle, GitHub account (for the saved name)

**Temporary password**:
A password the platform generates (different for every User) when the Superuser creates, imports or resets a User, shown to the Superuser only once; the User must replace it at their next login. Starting accounts use the one from `logins.txt`.
_Avoid_: Default password, reset code

**Starting account**:
One of the three Users (one per Role) created from the deployment's `logins.txt` the first time the backend starts, never overwritten afterwards; its password from that file counts as a Temporary password. Starting accounts are only created while there are no Users at all, so editing or deleting one never brings the original back. The only sanctioned use of "account" for a User.
_Avoid_: Default user, seed user, admin account

### Projects

**Project**:
A piece of work a team of Students carries out for its Product Owner. A Teacher or the Superuser can delete an Active Project created by mistake while it has no Members and no Makers.
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
A finished Project, kept read-only for the history overview. Archiving frees its Students, and restoring it does not bring them back. It can never be deleted, nor can a restored Project that has Makers. It is never Open for choice: archiving switches that off.
_Avoid_: Deleted project, closed project, historical project

**Project photo**:
The one optional cover photo of a Project (JPG or PNG, at most 5 MB), uploaded, replaced and removed by Teachers and the Superuser. Shown on the Project's details, as a thumbnail in the Projects table and on a Member's My project. An Archived Project keeps its photo, read-only; deleting a Project deletes its photo.
_Avoid_: Image, picture, logo, avatar

**Open for choice**:
An Active Project that a Teacher or the Superuser has marked so that Students can pick it in their Top 3. Off for a new Project; switched off when the Project is archived.
_Avoid_: Visible, published, available

**Top 3**:
A Student's ranked choice of 3 different Projects that are Open for choice (fewer when fewer are open), submitted once during the Top 3 round and final after that; only a Teacher or the Superuser can reset it. Only Students without a Project submit one; Teachers form the teams from them. A chosen Project that is later deleted, archived or closed for choice shows as "no longer available".
_Avoid_: Preference, wish list, vote

**Top 3 round**:
The one period, ending at a deadline in Belgian time, in which Students submit their Top 3. A Teacher or the Superuser opens it, moves the deadline, closes it early or reopens it; every Top 3 is kept. Starting a new Top 3 round (each semester) clears every Top 3.
_Avoid_: Election, vote, enrolment period

**Project repository**:
The public GitHub repository of a Project, in the organisation the platform is connected to; created completely empty by "Create repos for all Projects" for every Active Project with Members. Its name is suggested from the title (`SmartGreenhouse`) and can be changed until it exists; renaming the Project doesn't rename it.
_Avoid_: Repo (in UI text), GitHub project, code base

**Makers**:
The permanent record of the Students (name, Programme, Year) who were Members of a Project when it was archived. Nobody is ever removed from it: archiving a restored Project again only adds the new Members (a Student already listed is not added twice). Shown as "Made by".
_Avoid_: History, former members, credits

**Programme**:
The VIVES study programme a Student is enrolled in, picked from the list the Superuser manages. Renaming a Programme renames it for every User, but not in Makers; a Programme can only be removed while no User has it.
_Avoid_: Course, study course, opleiding

**Year**:
Where a Student stands in their Programme: 1, 2, 3, or International for exchange students who belong to no year.
_Avoid_: Level, grade
