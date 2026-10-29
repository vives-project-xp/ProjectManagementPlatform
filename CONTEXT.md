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
A finished Project, kept read-only for the history overview. Archiving frees its Students, and restoring it does not bring them back. It can never be deleted, nor can a restored Project that has Makers. It is never Open for choice: archiving switches that off. Its Project repository is archived on GitHub too (read-only), and unarchived when the Project is restored; likewise its Trello board is closed and reopened.
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
The public GitHub repository of a Project, in the organisation the platform is connected to; created completely empty by "Create repos for all Projects" for every Active Project with Members. Its name is suggested from the title (`SmartGreenhouse`) and can be changed until it exists; renaming the Project doesn't rename it. A Project that has one can't be deleted, only archived.
_Avoid_: Repo (in UI text), GitHub project, code base

**Trello board**:
The private Trello board of a Project, alone in a Trello Workspace of its own (ADR 0007), both named after the Project's title and owned by the platform's dedicated Trello account. Created by "Create Trello boards for all Projects" for every Active Project with Members, with the lists Backlog, To do, Doing, Review and Done. Its Members join as normal members and its Product Owner as admin, invited by their platform email; someone without a Trello account with that email stays invited until they sign up. The board and its Workspace follow the Project's title; a Project with a board can't be deleted, only archived.
_Avoid_: Trello project, task board, Kanban (for the platform itself)

**Check members**:
Bringing a Project repository's access in line with the Project: active Members with a GitHub username get write access and the Product Owner admin access (GitHub sends them an invitation to accept); expired invitations are sent again; people the platform knows (a User's GitHub username, or an account the platform itself invited there) who no longer belong lose their access. Accounts the platform doesn't know, such as coaches added by hand, are never touched. Runs right after a repository is created, per Project, or for all repositories at once. For a Trello board it works the same way by platform email: active Members join as normal members and the Product Owner as admin; members the platform added who no longer belong (including the old member after a User's email changed) are removed; members it didn't add and the owner account are never touched; the board and its Workspace get the Project's title again.
_Avoid_: Sync, refresh access

**Daily email**:
The one email a User gets at 08:30 Belgian time on a day with Deadlines or Meetings for them (including their Weekly slot, unless that date is skipped): active Members and the Product Owner of Active Projects only, never the Superuser. Sent once a day, catching up until 18:00 when the site was down; switched off per User on My account (on by default).
_Avoid_: Notification, reminder, digest

**Deadline**:
A moment something is due, in Belgian time: for one Project (set by a Teacher or the Superuser on its page) or for every Active Project (on the Planning screen), never for Archived ones. It has a title and an optional description but no "done" state; tasks belong in Trello. Today's deadlines are shown in the Today banner; past ones are greyed under "Earlier". An Archived Project keeps its own deadlines, read-only.
_Avoid_: Due date, task, milestone

**Meeting**:
A one-off meeting of a Project's team: a date, a start and end time in Belgian time, a place (a room, or a link to an online meeting) and an optional note. Planned by a Teacher or the Superuser; an Archived Project keeps its Meetings, read-only.
_Avoid_: Appointment, event, session

**Weekly slot**:
A Project's one fixed weekly meeting: a weekday, a start and end time in Belgian time, and a place. Single dates can be skipped (holidays); clearing it stops it (e.g. during exams). Its meetings of the coming seven days show alongside the Deadlines and Meetings; an Archived Project has none.
_Avoid_: Recurring meeting, standup, timetable

**Chat**:
A Project's one group chat (spec #91): short messages of its Chat people, shown oldest first, with new ones appearing within seconds. Every Teacher and the Superuser can also read and write in every Chat without being one of its Chat people. An Archived Project's Chat is read-only and only Teachers and the Superuser still read it; its messages and files are deleted 6 months after archiving (restoring the Project before then brings it back with its history). Deleting a Project deletes its Chat; a deleted User's messages stay as "Deleted user".
_Avoid_: Forum, channel, conversation, group

**Chat file**:
A photo or other file attached to a Chat message: up to 5 per message, 10 MB each, never a program (.exe, .bat, .sh, .apk, …). Photos (JPG, PNG, WebP, GIF) show as thumbnails that open full size; other files are downloads with their name and size. Only people who can read the Chat get them; they are in the nightly backup, and deleting the Project deletes them.
_Avoid_: Attachment, upload, media

**Reply**:
A Chat message that answers another one in the same Chat; it shows a quote of the original (its author and first line) that scrolls to it when clicked.
_Avoid_: Thread, quote-reply

**Mention**:
"@First Last" of one of a Chat's Chat people, or "@team" for all its Members, in a Chat message (typing @ suggests them). The mentioned person sees the message highlighted, and the Chat gets a red @ marker (navigation and Chats screen) until they have read past it. Teachers and the Superuser who only read along can't be mentioned; there are no emails.
_Avoid_: Tag, ping, notification

**Reaction**:
One of six emoji (👍 ❤️ 😂 😮 😢 🎉) a User adds to a Chat message, shown with a count and, on hover, the names; several per person, and clicking your own takes it back.
_Avoid_: Like, emoji vote

**Seen by**:
On a User's own Chat message, how many of the Chat people have read up to it, with their names on click. Teachers and the Superuser who only read along don't count.
_Avoid_: Read receipts, viewed by

**Deleted message**:
A Chat message removed by its author, or by a Teacher or the Superuser (moderation): its text and files are gone, but it stays in the Chat as "This message was deleted.", and so do quotes of it. Authors can also edit their own messages, shown "(edited)".
_Avoid_: Removed message, hidden message

**Chat people**:
Whom a Project's Chat is for: its Members, its Product Owner and its Guests. Only they count for the Unread badge; a Member who is removed or moved loses access to the Chat at once, and a new Member sees its whole history.
_Avoid_: Participants, chat members

**Guest**:
Any active User added to a Project's Chat on top of its team, by the Product Owner, a Teacher or the Superuser (never by Members). A Guest reads the whole history and writes like the team, can leave, and can be removed by the same staff; archiving the Project ends their access.
_Avoid_: Visitor, external member, invitee

**Unread**:
The messages of others in a Chat after the last one a User has seen; opening the Chat reads them. The Chat item in the navigation shows how many there are in the User's own Chats (for a Teacher: those where they are one of the Chat people).
_Avoid_: New messages, notifications

**Makers**:
The permanent record of the Students (name, Programme, Year) who were Members of a Project when it was archived. Nobody is ever removed from it: archiving a restored Project again only adds the new Members (a Student already listed is not added twice). Shown as "Made by".
_Avoid_: History, former members, credits

**Programme**:
The VIVES study programme a Student is enrolled in, picked from the list the Superuser manages. Renaming a Programme renames it for every User, but not in Makers; a Programme can only be removed while no User has it.
_Avoid_: Course, study course, opleiding

**Year**:
Where a Student stands in their Programme: 1, 2, 3, or International for exchange students who belong to no year.
_Avoid_: Level, grade
