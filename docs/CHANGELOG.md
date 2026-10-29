# Changelog

Everything that has been built, changed and fixed in the Project Management Platform, from the first commit on 2026-10-01 until now.

How to read this file:

1. **[Change requests from the team](#change-requests-from-the-team)** comes first. Each time the team asked for something to be done differently, it shows what it was **before**, what the team **asked**, and what was **changed**, with the issue, the PR and the files involved.
2. **[History by date](#history-by-date)** lists every spec, ticket and fix, newest first, split into **New**, **Changed** and **Fixed**.
3. **[All commits](#all-commits)** is the complete commit list, oldest first, so nothing is missing.

Numbers like #24 are GitHub issues or pull requests on [vives-project-xp/ProjectManagementPlatform](https://github.com/vives-project-xp/ProjectManagementPlatform). A **spec** is a parent issue that describes a feature; its **tickets** are the sub-issues, each implemented in one PR. Every PR runs CI (Ruff, backend and frontend tests), and after merging into `main` the Deploy workflow puts it live on the VIVES VM.

---

## Change requests from the team

Newest first. Each request has the same four parts: **Before**, **Asked**, **Changed**, **Where**.

### R13. Tables fit the screen (2026-10-22, #89, PR #90)

**Before.** Page content was at most 896 px wide, and table cells never wrapped. The **Users** table (Name, Email, GitHub, Role, Programme, Year, Status) was wider than that, so on a laptop you had to **scroll to the right** to see Year and Status.

**Asked.** *"change users table so it fits the whole screen, we have to go to the right to view year and status good, make it autoscale"*.

**Changed.**
- **Wider pages:** the content of every page (and the footer) can now be up to 1280 px wide. Forms and cards keep their narrow width; tables and lists use the extra room.
- **Tables adapt to the screen:**
  - table cells wrap between words;
  - email addresses and GitHub names may break anywhere.

  Every table now fits without scrolling sideways. At 1366 px the Users table fits with one line per row. In an 800 px window it fits too: only the emails and GitHub names break over lines, and words stay whole.

**Where.** `frontend/src/pmp_frontend/theme.py` (`CONTENT_WIDTH`, `BREAK_ANYWHERE`, table CSS), `users_page.py`; test in `frontend/tests/test_navigation.py`.

### R12. Tidy the buttons on the Projects screen (2026-10-22, #81, PR #85)

**Before.** The Projects screen had the heading and **five buttons on one row**: "Create repos for all Projects", "Check all members", "Create Trello boards for all Projects", "Check all Trello members" and "New Project". On a normal screen they wrapped onto several lines and looked cluttered. On a Project's page, the status, the Archive and Delete buttons and the "Open for choice" switch were **loose under the title**, and in the Members card the "Add a Student" select and the "Add Member" button were on separate lines.

**Asked.** *"knoppen bij projects aanpassen, is niet mooi nu, ongeordend"*. You had already got these buttons, but found the layout unclear and crowded. Of the two layouts offered, the team chose **one menu per service**.

**Changed.**
- **Projects screen:** next to the heading there is now only **New Project** (red, with a + icon). Below it is one row with the **Active / Archived** filter on the left and two menu buttons on the right:
  - **GitHub ▾** holds "Create repos for all Projects" and "Check all members";
  - **Trello ▾** holds "Create Trello boards for all Projects" and "Check all Trello members".

  When GitHub or Trello isn't connected, its note ("GitHub isn't connected.") shows instead of the menu, as before.
- **A Project's page:** a new **Status** card holds:
  - a status badge (green *Active* or grey *Archived*);
  - the *Open for choice* switch;
  - **Archive / Restore** on the left and a flat red **Delete** on the right.
- **Members card:** the Student select and **Add Member** now sit on one row.
- Nothing changed in what the buttons do.

**Where.** `frontend/src/pmp_frontend/projects_page.py`, `repos.py`, `trello.py`; test `frontend/tests/test_archive.py`.

### R11. Add a Student to a Project they didn't choose (2026-10-22, #80, PR #84)

**Before.** On the **Top 3** screen, each Student card only had "Add to …" buttons for the three Projects in that Student's Top 3. A Student who hadn't chosen yet had no add option there at all. To put a Student in any other Project, a Teacher had to leave the Top 3 screen and open that Project's page.

**Asked.** *"studenten kunnen toevoegen aan projecten die ze niet gekozen hebben"*. When asked, the team confirmed this is a **new feature** for the Top 3 screen, not a rule to forbid it.

**Changed.** Every Student card on the Top 3 screen now has an **"Add to another Project"** select (you can type to search) and an **Add** button.
- The select lists every Active Project that isn't the Student's current Project and isn't already one of their Top 3 buttons.
- It is also shown for Students who haven't chosen yet.
- The usual Members rules apply: the maximum Team size, and a confirmation when the Student is a Member of another Project and would be moved.

**Where.** `frontend/src/pmp_frontend/top3_page.py`; tests in `frontend/tests/test_top3_overview.py`.

### R10. Footer links in the environment (2026-10-22, #79, PR #83)

**Before.** The footer's links (Instagram, TikTok, YouTube, LinkedIn, privacy policy) and the campus address were **written in the code** (`theme.py`). Changing a link meant changing the code and deploying again.

**Asked.** *"footer: dit moet in een environment zodat je de links makkelijk kan aanpassen"*.

**Changed.** The links and the address are now settings, read from the environment:
- the settings are `FOOTER_INSTAGRAM`, `FOOTER_TIKTOK`, `FOOTER_YOUTUBE`, `FOOTER_LINKEDIN`, `FOOTER_PRIVACY_URL` and `FOOTER_ADDRESS`;
- set them in `/opt/pmp/.env` on the VM and recreate the frontend (`docker compose up -d frontend`); no new release is needed;
- a setting that is left out (or left empty) keeps the VIVES default;
- `none` hides that link (or the address).

**Where.** `frontend/src/pmp_frontend/settings.py`, `theme.py`, `compose.yml`, `.env.example`; test in `frontend/tests/test_navigation.py`.

### R9. Icons in the footer (2026-10-15, follow-up to #76, PR #78)

**Before.** The footer from PR #77 showed the social links as **text only**: "Instagram", "TikTok", "YouTube", "LinkedIn".

**Asked.** Icons for the social media links.

**Changed.**
- Each link now has its own icon in front of the name.
- The icons are Bootstrap Icons (MIT licence), stored in the repo (`frontend/src/pmp_frontend/static/icons/`). They are placed inline, so they take the white text colour and nothing is loaded from another website.

**Where.** `frontend/src/pmp_frontend/theme.py`, `static/icons/`.

### R8. A footer on every page (2026-10-15, #76, PR #77)

**Before.** The pages had **no footer**. Below the content there was nothing.

**Asked.** A footer on every page (the login page too, but not in the daily email). It should have the official VIVES social links as on vives.be, the privacy policy, the Brugge campus address and a copyright line, in the house style.

**Changed.** A black footer with white text on every page:
- the Instagram, TikTok, YouTube and LinkedIn links of VIVES;
- the privacy policy;
- the address "VIVES Brugge Xaverianenstraat · Xaverianenstraat 10, 8200 Brugge";
- "© <year> VIVES. All rights reserved.".

Links open in a new tab.

**Where.** `theme.footer()` in `frontend/src/pmp_frontend/theme.py`.

### R7. The daily email without a link to the bare IP address (2026-10-15, PR #75)

**Before.** The 08:30 daily email (#71) ended with a link to `https://10.20.10.33`. The first real email landed in Gmail's **spam** folder, and a link to a bare IP address is one of the things spam filters distrust.

**Asked.** After the real try, the team wanted the email out of spam.

**Changed.**
- While `SITE_URL` is an IP address, the email says "Open the Project Management Platform to see your planning." **without a link**.
- As soon as VIVES IT gives the site a hostname and `SITE_URL` is changed, the link comes back automatically.

**Where.** `backend/src/pmp_backend/services/daily_email.py` (and its tests).

### R6. Import Users from a CSV file, with generated passwords (2026-10-08, #56, PR #57)

**Before.**
- The Superuser created Users **one by one** in the "New User" dialog.
- They **typed a Temporary password** for each User themselves.
- "Reset password" also asked for a password to be typed.

**Asked.** The team asked for this outside the GitHub spec. They wanted to import a whole class at once, and the platform should make the passwords.

**Changed.**
- **Generated passwords:** the platform now generates every Temporary password itself: random, at least 12 characters, without look-alike characters (0/O/1/l).
  - "New User" and "Reset password" show the generated password **once**.
  - Only its hash is stored.
- **Import CSV** on the Users screen:
  - **Format:** one `Firstname,Lastname,email` per line (a header line and `;` as separator are allowed; UTF-8 with or without BOM; at most 1000 lines).
  - **Role, Programme and Year:** one Role for the whole file, and for Students one Programme and Year.
  - **Skipped lines:** wrong lines are skipped and listed with their line number and the reason.
  - **Passwords file:** afterwards the Superuser downloads `temporary-passwords.csv` **once**.

**Where.** `backend/src/pmp_backend/security.py`, `services/users.py`, `api/users.py`; `frontend/src/pmp_frontend/user_import.py`, `users_page.py`; `CONTEXT.md`.

### R5. Security hardening (2026-10-08, PR #42 and fix PR #43)

**Before.**
- **API:** Caddy forwarded **every** `/api/...` request to the backend, so the whole REST API could be reached from the network.
- **Headers:** there were no security headers.
- **Cookie:** the session cookie wasn't marked `Secure`.
- **Passwords:** you could try passwords as often as you liked.

**Asked.** The team asked for a security round before starting on the Top 3.

**Changed.**
- **Private API** (ADR 0006): only `/api/health` is reachable through Caddy; every other `/api/...` gives 404. The frontend talks to the backend inside the Docker network.
- **Security headers:** `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer` and a strict `Permissions-Policy`; the `Server` header is removed.
- **Session cookie:** marked `Secure` and `SameSite=Lax`.
- **Login lockout:** after 5 wrong passwords for one email within 15 minutes, that email is locked for 15 minutes.
- **Certificate warning:** the team chose to keep it. A trusted certificate isn't possible for a private IP; we'll ask VIVES IT for a hostname.
- **Fix, PR #43:** after deploying, Caddy still ran with the old configuration. Deploy now restarts `caddy` and `backup`, so files they mount from the checkout are read again.

**Where.** `Caddyfile`, `compose.yml`, `backend/src/pmp_backend/services/auth.py`, `frontend/src/pmp_frontend/main.py`, `.github/workflows/deploy.yml`, `docs/adr/0006-only-the-frontend-is-public.md`.

### R4. A test login for the team (2026-10-08, PR #36)

**Before.** To test as a Superuser, a Teacher or a Student, you had to **type the email and password** of each account every time.

**Asked.** A quick way to log in as any User while testing.

**Changed.**
- With `DEV_LOGIN=true` in `.env`, the login page shows a **"Test login" card**: pick an active User and log in without a password, with a red warning.
- It is **off by default** and must be turned off before real Students use the site.

**Where.** `backend/src/pmp_backend/api/dev_login.py`, `frontend/src/pmp_frontend/pages.py`, `compose.yml`, `.env.example`.

### R3. Stay logged in after a deploy (2026-10-08, PR #33)

**Before.** **Every deploy logged everyone out.** The frontend kept the login token in a folder inside its container, and a deploy recreates the container.

**Asked.** The team reported it as a problem.

**Changed.**
- A named Docker volume `frontend-storage` now holds that folder, so logins survive a deploy.
- The very first deploy with the change logged everyone out once.

**Where.** `compose.yml`.

### R2. Post-MVP improvements from using the MVP (2026-10-01/08, spec #24, tickets #25–#29)

After the MVP went live, the team tried it and listed what bothered them. The list was turned into spec #24 in a grilling session (Q1–Q13). There are five changes in it.

**a. Navigation polish (#25, PR #30)**
- **Before:** clicking the VIVES logo did nothing; the navigation was plain text; the login page showed a technical "System status: Backend / Database online" card.
- **Asked:** the logo should go home, the menu should have icons, and the technical block should go.
- **Changed:**
  - the logo goes to your home screen (Users for the Superuser, Projects for a Teacher, My project for a Student). It is not a link on the login page or while a Temporary password must still be changed;
  - every navigation item has a black icon next to its label;
  - the System status card is gone.

**b. Programmes managed in the app (#26, PR #31)**
- **Before:** the list of Programmes (opleidingen) was **fixed in the code**; a new Programme needed a developer.
- **Asked:** the Superuser should manage it.
- **Changed:** a new Programmes screen: add, rename, and remove a Programme that no Student has (new `programmes` table, migration `0004`).

**c. Deleting Users (#27, PR #32)**
- **Before:** a User created by mistake (a typo, a duplicate) could only be **deactivated**, so it stayed visible forever.
- **Asked:** be able to delete such a User.
- **Changed:**
  - the Superuser can **delete** a Student or Teacher who isn't linked to anything (not a Member, not a Maker, not a Product Owner). Others still get "Deactivate them instead.";
  - the starting accounts from `logins.txt` are now only created when the database is empty, so a deleted starting account doesn't come back.

**d. Deleting Projects (#28, PR #34)**
- **Before:** a Project created by mistake could only be **archived**.
- **Asked:** be able to delete it.
- **Changed:** Teachers and the Superuser can delete an **Active** Project **without Members** (and without Makers).

**e. A cover photo per Project (#29, PR #35)**
- **Before:** Projects had **no picture**, so the screens were walls of text.
- **Asked:** a photo per Project.
- **Changed:** one cover photo per Project. It is shown on the Project's page, on My project and as a thumbnail in the Projects table, and it is included in the nightly backup (migration `0005`, volume `photos`).

### R1. One ticket at a time, PRs always against `main` (2026-10-08, process)

**Before.**
- **Stacked PRs:** tickets #40 and #41 were built as **stacked PRs** (#46 on top of #45, #47 on top of #46). When #45 was merged, the repo kept its branch, so #46 and #47 were merged into the feature branches instead of `main`. An extra PR #48 had to bring them to `main`.
- **Parallel agents:** the team also asked whether several tickets could be built at once by parallel agents.

**Asked / agreed.** Keep the README rule: one ticket at a time, and always open PRs against `main`.

**Changed.** Since then, every PR is opened against `main` and tickets are built one after the other.

---

## History by date

Newest first. "Live" means deployed to the VIVES VM by the Deploy workflow. "Migration" is the Alembic database version after that change.

### 2026-10-29: Project chat, continued (spec #91)

| | What | Issue | PR |
|---|---|---|---|
| New | **Chat photos and files:** up to 5 per message, 10 MB each, programs refused; photos as thumbnails that open full size, other files as downloads with their size; a message may be files only; volume `chat-files`, in the nightly backup and the restore test; migration `0016` | #94 | #102 |
| New | Weekly scrum notes of the team in `Scrum/scrum.md` (newest week on top) | – | #103 |
| New | **Chat edit, delete and reply:** edit your own messages ("(edited)"), delete them ("This message was deleted.", files go too); Teachers and the Superuser delete any message; reply with a quote that scrolls to the original; edits and deletions appear live (open chats poll `since` a revision); migration `0017` | #95 | #104 |

### 2026-10-22: Project chat (spec #91)

Grilling Q1–Q22 with the team, spec #91 and tickets #92–#98. Built one ticket at a time.

| | What | Issue | PR |
|---|---|---|---|
| New | **Chat basics:** one chat per Project (Members, Product Owner; every Teacher and the Superuser can also read and write), text messages with clickable links, new messages within ~2 s (ADR 0008), Unread badge on the Chat / Chats item, Chats screen, Chat button on a Project's page; migration `0014` | #92 | #99 |
| Fixed | The restore test after a Deploy failed when the site wrote meanwhile (first seen after #99, with the new chat in use): it now compares with the row counts taken just before and after the dump, and backs up again (max 3 times) when they differ | – | #100 |
| New | **Chat Guests:** the Product Owner, a Teacher or the Superuser adds any active User to a chat (People list, Add Guest, Remove); Guests can leave; "Only my chats" on the Chats screen (on by default); a Teacher's badge also counts chats where they are a Guest; Students in several chats get a list; migration `0015` | #93 | #101 |

### 2026-10-22: team change requests

| | What | Issue | PR |
|---|---|---|---|
| Changed | Footer links and address from the environment (`FOOTER_*`) | #79 | #83 |
| New | Top 3 screen: add a Student to a Project outside their Top 3 | #80 | #84 |
| Changed | Tables fit the screen: wider pages (1280 px), cells wrap, emails break (R13) | #89 | #90 |
| Changed | Projects screen: GitHub ▾ / Trello ▾ menus; Status card on a Project's page | #81 | #85 |
| New | This changelog (`docs/CHANGELOG.md`) | #82 | #86 |
| Fixed | "Create Trello boards for all Projects" said *The server cannot be reached*: the frontend waited only 5 s. The four actions for all Projects now wait up to 5 minutes and show a spinning "Working…" notification (found in the team's dummy test) | #87 | #88 |

### 2026-10-15: deadlines, meetings, daily email, footer (spec #68, #76)

**Spec #68 Deadlines and meeting times, with a daily email at 08:30** (grilling Q1–Q17).

| | What | Issue | PR |
|---|---|---|---|
| New | Deadlines for one or all Active Projects, the **Planning** screen (upcoming by day, "Only my Projects"), the **Today** banner; migration `0011` | #69 | #72 |
| New | One-off **meetings** and one **weekly slot** per Project with skipped dates; migration `0012` | #70 | #73 |
| New | The **daily email** at 08:30 Belgian time (once a day, catch-up until 18:00), a switch on My account; migration `0013`; live since 14:47 via the team Gmail | #71 | #74 |
| Fixed | Daily email: no link to the bare IP address (spam) | – | #75 |
| New | Footer with VIVES socials, privacy policy, address and copyright | #76 | #77 |
| Changed | Footer icons for the social links | #76 | #78 |

**Spec #61 Trello boards** (grilling Q1–Q16, ADR 0007: one free Trello Workspace per Project).

| | What | Issue | PR |
|---|---|---|---|
| New | Trello settings (`TRELLO_API_KEY`, `TRELLO_TOKEN`), **Create Trello boards for all Projects** (private board with lists Backlog / To do / Doing / Review / Done); migration `0010` | #62 | #65 |
| Fixed | Trello's "Member already invited" counts as already on the board | #62 | #65 |
| New | Trello **Check members**, statuses per person, the Students' view on My project | #63 | #66 |
| New | Boards follow archive (closed), restore (reopened) and rename; deleting a Project with a board is refused | #64 | #67 |

**Spec #49 GitHub repositories, finished.**

| | What | Issue | PR |
|---|---|---|---|
| New | Students see their repository and their next step; archive/restore follows on GitHub (warning instead of failing); deleting a Project with a repository is refused | #53 | #60 |

### 2026-10-08: delete, photos, hardening, Top 3, GitHub, CSV import

**Spec #24 Post-MVP improvements, finished** (see R2).

| | What | Issue | PR |
|---|---|---|---|
| New | Superuser deletes Users without links; seeding only on an empty database | #27 | #32 |
| Fixed | Logins survive deploys (`frontend-storage` volume) | – | #33 |
| New | Delete Active Projects without Members | #28 | #34 |
| New | Project cover photo, included in the backup; migration `0005` | #29 | #35 |

**Tools and security.**

| | What | Issue | PR |
|---|---|---|---|
| New | Test login (`DEV_LOGIN`) | – | #36 |
| Changed | Hardening: private API, security headers, Secure cookie, login lockout (ADR 0006) | – | #42 |
| Fixed | Deploy restarts Caddy and backup so mounted files reload | – | #43 |

**Spec #37 Top 3: Students choose their Projects each semester** (grilling Q1–Q23).

| | What | Issue | PR |
|---|---|---|---|
| New | **Open for choice** per Project and the **Top 3 round** with a deadline (Belgian time); migration `0006` | #38 | #44 |
| New | Students submit their Top 3 (final once submitted) | #39 | #45 |
| New | Top 3 overview for Teachers (filters, summary per Project) and reset | #40 | #46 → #48 |
| New | Assign Members straight from the Top 3s; the Members select shows the rank | #41 | #47 → #48 |

**Spec #49 GitHub repositories** (grilling Q1–Q21).

| | What | Issue | PR |
|---|---|---|---|
| New | GitHub usernames; **My account** page (replaces Change password); migration `0007` | #50 | #54 |
| Fixed | Test helpers wait longer (CI was slower) | – | #55 |
| New | CSV import and generated Temporary passwords (team request, see R6) | #56 | #57 |
| New | Repository names, **Create repos for all Projects**; migration `0008` | #51 | #58 |
| New | **Check members** (invite, change rights, remove who left) and repository status; migration `0009` | #52 | #59 |

### 2026-10-01: discovery, the MVP and the first improvements

**Discovery.**

| | What | Issue | PR |
|---|---|---|---|
| New | Repository, README, agent skills config (issue tracker, triage labels, domain docs) | – | #1 |
| New | MVP discovery (Q1–Q32): `CONTEXT.md` glossary, ADR 0001–0004, `docs/coding-standards.md` | – | #2 |

**Spec #3 MVP: accounts, Projects and Members, deployed via CI/CD.**

| | What | Issue | PR |
|---|---|---|---|
| New | Walking skeleton: VIVES start page, CI, Deploy to the VM via the self-hosted runner; old "library" project removed | #4 | #14 |
| New | Starting accounts, login, logout, forced password change | #5 | #15 |
| New | Superuser creates Teachers and Students | #6 | #16 |
| New | Teachers create and edit Projects | #7 | #17 |
| New | Superuser edits, deactivates, reactivates and resets Users | #8 | #18 |
| New | Teachers add, move and remove Members (Team size, move confirmation) | #9 | #19 |
| New | Archive and restore Projects; Members saved as **Makers** ("Made by") | #10 | #20 |
| New | Members overview with filters | #11 | #21 |
| New | My project for Students | #12 | #22 |
| New | Nightly database backups with a restore test after every deploy (ADR 0005) | #13 | #23 |

**Spec #24 Post-MVP improvements, started** (see R2).

| | What | Issue | PR |
|---|---|---|---|
| Changed | Navigation polish: logo link, icons, no system status | #25 | #30 |
| New | Superuser manages Programmes; migration `0004` | #26 | #31 |

**Code review fixes.** Most MVP tickets got a code review before merging, and the fixes were committed in the same PR. They were improvements to the code, not changes the team asked for:

| PR | Fixes |
|---|---|
| #15 | the Role in the login token; a missing `logins.txt` no longer breaks the deploy; dropped a password rule the spec didn't ask for |
| #16 | readable validation errors instead of "Something went wrong."; one place for the Student-only Programme/Year rule; duplicate email gives 409 |
| #17 | `ProjectStatus` enum; one error handler; only a real duplicate title says "already exists" |
| #18 | Project queries kept in the project service; separate deactivate/reactivate calls |
| #19 | row locks so Team size and moves can't be skipped by two clicks at once; shared helpers |
| #20 | Members locked while archiving; Makers wording in `CONTEXT.md` |
| #22, #35 | small review fixes for My project and the cover photo |

---

## All commits

Every commit on `main`, oldest first.
- **Author** is the git author; the work was done with Claude Code (co-author line in each commit).
- **Merge commits** ("Merge pull request #N") show which teammate merged the PR.
- **Pending:** the change requests of 2026-10-22 (PRs #83, #84, #85 and this changelog) are added to `main` when they are merged.

| # | Commit | Date (UTC+2) | Author | Message |
|---|---|---|---|---|
| 1 | [`e5d45c1`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/e5d45c1) | 2026-10-01 08:44 | Ocean Dekeyser | chore: initialize repository with README |
| 2 | [`fa00e5d`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/fa00e5d) | 2026-10-01 08:48 | finn6698 | Update README.md |
| 3 | [`5dff20d`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/5dff20d) | 2026-10-01 08:49 | Delmar Ramcic | Update README.md |
| 4 | [`4d991e6`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/4d991e6) | 2026-10-01 09:45 | Ocean | chore: add agent skills config (issue tracker, triage labels, domain docs) (#1) |
| 5 | [`026988e`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/026988e) | 2026-10-01 10:59 | finn6698 | Add files via upload |
| 6 | [`8b77ab7`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/8b77ab7) | 2026-10-01 11:02 | Ocean | docs: record MVP discovery (glossary, ADRs, coding standards) (#2) |
| 7 | [`259895a`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/259895a) | 2026-10-01 11:31 | Ocean | feat: walking skeleton with CI/CD to the VM (#14) |
| 8 | [`0187554`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/0187554) | 2026-10-01 12:57 | Ocean Dekeyser | Add login, starting accounts and forced password change (#5) |
| 9 | [`345bca0`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/345bca0) | 2026-10-01 12:59 | Ocean Dekeyser | Address review of #5: Role in token, non-fatal logins file |
| 10 | [`7ba02bc`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/7ba02bc) | 2026-10-01 13:02 | finn6698 | Merge pull request #15 from vives-project-xp/feat/login |
| 11 | [`d39a590`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/d39a590) | 2026-10-01 13:14 | Ocean Dekeyser | Superuser lists and creates Teachers and Students (#6) |
| 12 | [`108bd6f`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/108bd6f) | 2026-10-01 13:16 | Ocean Dekeyser | Address review of #6: readable validation errors, one User constructor |
| 13 | [`27ab0e8`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/27ab0e8) | 2026-10-01 13:20 | Delmar Ramcic | Merge pull request #16 from vives-project-xp/feat/users |
| 14 | [`9d4ec4b`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/9d4ec4b) | 2026-10-01 13:32 | Ocean Dekeyser | Teachers create and edit Projects (#7) |
| 15 | [`43c42bf`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/43c42bf) | 2026-10-01 13:34 | Ocean Dekeyser | Address review of #7: ProjectStatus, one error handler |
| 16 | [`4ac4197`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/4ac4197) | 2026-10-01 13:35 | Delmar Ramcic | Merge pull request #17 from vives-project-xp/feat/projects |
| 17 | [`93c3d46`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/93c3d46) | 2026-10-01 13:45 | Ocean Dekeyser | Superuser edits, deactivates, reactivates and resets Users (#8) |
| 18 | [`d9ba6f1`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/d9ba6f1) | 2026-10-01 13:48 | Ocean Dekeyser | Address review of #8: keep Project queries in the project service |
| 19 | [`31a36c8`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/31a36c8) | 2026-10-01 13:50 | Delmar Ramcic | Merge pull request #18 from vives-project-xp/feat/manage-users |
| 20 | [`5ed13f3`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/5ed13f3) | 2026-10-01 14:02 | Ocean Dekeyser | Teachers add, move and remove Members (#9) |
| 21 | [`b1aafc7`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/b1aafc7) | 2026-10-01 14:06 | Ocean Dekeyser | Address review of #9: lock Team size edits, shared helpers |
| 22 | [`1972268`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/1972268) | 2026-10-01 14:08 | finn6698 | Merge pull request #19 from vives-project-xp/feat/members |
| 23 | [`5dcdb7c`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/5dcdb7c) | 2026-10-01 14:21 | Ocean Dekeyser | Teachers archive and restore Projects; Makers (#10) |
| 24 | [`898fc60`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/898fc60) | 2026-10-01 14:24 | Ocean Dekeyser | Address review of #10: lock Members while archiving, Makers wording |
| 25 | [`f1b4c1a`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/f1b4c1a) | 2026-10-01 14:26 | finn6698 | Merge pull request #20 from vives-project-xp/feat/archive |
| 26 | [`802ae7a`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/802ae7a) | 2026-10-01 14:43 | Ocean | Members overview with filters (#11) (#21) |
| 27 | [`34029de`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/34029de) | 2026-10-01 14:51 | Ocean Dekeyser | My project for Students (#12) |
| 28 | [`2a17546`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/2a17546) | 2026-10-01 14:51 | Ocean Dekeyser | Review fixes for My project |
| 29 | [`39b47aa`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/39b47aa) | 2026-10-01 14:54 | Delmar Ramcic | Merge pull request #22 from vives-project-xp/feat/my-project |
| 30 | [`9909d5e`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/9909d5e) | 2026-10-01 15:04 | Ocean Dekeyser | Nightly database backups (#13) |
| 31 | [`d894370`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/d894370) | 2026-10-01 15:09 | finn6698 | Merge pull request #23 from vives-project-xp/feat/nightly-backups |
| 32 | [`0486037`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/0486037) | 2026-10-01 15:27 | Ocean Dekeyser | Navigation polish: logo link, navigation icons, no system status (#25) |
| 33 | [`63fd11c`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/63fd11c) | 2026-10-01 15:30 | finn6698 | Merge pull request #30 from vives-project-xp/feat/navigation-polish |
| 34 | [`ec83377`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/ec83377) | 2026-10-01 15:43 | Ocean Dekeyser | Superuser manages Programmes (#26) |
| 35 | [`95e03b5`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/95e03b5) | 2026-10-01 15:45 | Delmar Ramcic | Merge pull request #31 from vives-project-xp/feat/programmes |
| 36 | [`e56a6f0`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/e56a6f0) | 2026-10-08 08:45 | Ocean Dekeyser | Superuser deletes Users without links (#27) |
| 37 | [`80e3859`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/80e3859) | 2026-10-08 08:49 | finn6698 | Merge pull request #32 from vives-project-xp/feat/delete-users |
| 38 | [`152fc5b`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/152fc5b) | 2026-10-08 08:58 | Ocean Dekeyser | Keep logins across deploys |
| 39 | [`9112402`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/9112402) | 2026-10-08 09:00 | Delmar Ramcic | Merge pull request #33 from vives-project-xp/fix/keep-logins-on-deploy |
| 40 | [`ddb4a9e`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/ddb4a9e) | 2026-10-08 09:07 | Ocean Dekeyser | Delete Active Projects without Members (#28) |
| 41 | [`ec17d88`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/ec17d88) | 2026-10-08 09:10 | Delmar Ramcic | Merge pull request #34 from vives-project-xp/feat/delete-projects |
| 42 | [`7a1b42e`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/7a1b42e) | 2026-10-08 09:25 | Ocean Dekeyser | Project cover photo, including backup (#29) |
| 43 | [`d7e12f5`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/d7e12f5) | 2026-10-08 09:30 | Ocean Dekeyser | Photo review fixes (#29) |
| 44 | [`0e48fdf`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/0e48fdf) | 2026-10-08 09:33 | Delmar Ramcic | Merge pull request #35 from vives-project-xp/feat/project-photos |
| 45 | [`13f69d9`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/13f69d9) | 2026-10-08 09:54 | Ocean | Test login: pick a User on the login page (DEV_LOGIN) (#36) |
| 46 | [`016ec5b`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/016ec5b) | 2026-10-08 10:43 | Ocean Dekeyser | Harden the site: private API, security headers, Secure cookie, login lockout |
| 47 | [`5fa3c91`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/5fa3c91) | 2026-10-08 10:52 | Delmar Ramcic | Merge pull request #42 from vives-project-xp/feat/hardening |
| 48 | [`8843986`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/8843986) | 2026-10-08 11:03 | Ocean | Deploy: recreate Caddy and backup so mounted files reload (#43) |
| 49 | [`42d183a`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/42d183a) | 2026-10-08 11:30 | Ocean | Open for choice and the Top 3 round (#38) (#44) |
| 50 | [`fafedb5`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/fafedb5) | 2026-10-08 11:44 | Ocean Dekeyser | Students submit their Top 3 (#39) |
| 51 | [`a382649`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/a382649) | 2026-10-08 12:50 | Delmar Ramcic | Merge pull request #45 from vives-project-xp/feat/submit-top3 |
| 52 | [`9f909cb`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/9f909cb) | 2026-10-08 12:51 | Ocean Dekeyser | Top 3 overview and reset (#40) |
| 53 | [`455a553`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/455a553) | 2026-10-08 13:10 | Ocean | Assign Members from the Top 3s (#41) (#47) |
| 54 | [`45d42cd`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/45d42cd) | 2026-10-08 13:14 | Delmar Ramcic | Merge pull request #48 from vives-project-xp/feat/top3-overview |
| 55 | [`d4ee865`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/d4ee865) | 2026-10-08 14:12 | Ocean | GitHub usernames and My account (#50) (#54) |
| 56 | [`e3451c5`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/e3451c5) | 2026-10-08 14:17 | Ocean Dekeyser | Test helper: wait longer for the created-Project notification |
| 57 | [`20d2e89`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/20d2e89) | 2026-10-08 14:17 | Ocean Dekeyser | Test helper: also wait longer for the password change page |
| 58 | [`5e7bc77`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/5e7bc77) | 2026-10-08 14:27 | Delmar Ramcic | Merge pull request #55 from vives-project-xp/fix/create-project-helper-wait |
| 59 | [`02ee9b8`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/02ee9b8) | 2026-10-08 14:41 | Ocean | Import Users from a CSV file, with generated Temporary passwords (#56) (#57) |
| 60 | [`20442e1`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/20442e1) | 2026-10-08 15:04 | Ocean Dekeyser | Repository names and Create repos for all Projects (#51) |
| 61 | [`d840eca`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/d840eca) | 2026-10-08 15:11 | finn6698 | Merge pull request #58 from vives-project-xp/feat/create-repos |
| 62 | [`371bc73`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/371bc73) | 2026-10-08 15:28 | Ocean Dekeyser | Check members and repository status (#52) |
| 63 | [`c80e8ec`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/c80e8ec) | 2026-10-08 15:34 | Delmar Ramcic | Merge pull request #59 from vives-project-xp/feat/check-members |
| 64 | [`2d21316`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/2d21316) | 2026-10-15 08:32 | Ocean | Students' repository view, archiving repositories and delete refusal (#53) (#60) |
| 65 | [`046fae7`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/046fae7) | 2026-10-15 09:21 | Ocean Dekeyser | Trello settings and 'Create Trello boards for all Projects' (#62) |
| 66 | [`ebb4bf7`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/ebb4bf7) | 2026-10-15 09:24 | Ocean Dekeyser | Treat Trello's 'Member already invited' as already on the board (#62) |
| 67 | [`1cd5cbd`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/1cd5cbd) | 2026-10-15 09:29 | Delmar Ramcic | Merge pull request #65 from vives-project-xp/feat/trello-boards |
| 68 | [`acc29cb`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/acc29cb) | 2026-10-15 09:46 | Ocean | Trello Check members, statuses and the Students' view (#63) (#66) |
| 69 | [`617aa95`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/617aa95) | 2026-10-15 09:54 | Ocean Dekeyser | Trello boards follow archive, restore and rename; delete refusal (#64) |
| 70 | [`656c102`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/656c102) | 2026-10-15 10:01 | Delmar Ramcic | Merge pull request #67 from vives-project-xp/feat/trello-lifecycle |
| 71 | [`1d8aff1`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/1d8aff1) | 2026-10-15 13:32 | Ocean Dekeyser | Deadlines for one or all Projects, the Planning screen and the Today banner (#69) |
| 72 | [`cd11e02`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/cd11e02) | 2026-10-15 13:36 | Delmar Ramcic | Merge pull request #72 from vives-project-xp/feat/deadlines |
| 73 | [`4120df8`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/4120df8) | 2026-10-15 13:52 | Ocean Dekeyser | Meetings: one-off meetings and the weekly slot with skipped dates (#70) |
| 74 | [`98c897c`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/98c897c) | 2026-10-15 14:02 | Delmar Ramcic | Merge pull request #73 from vives-project-xp/feat/meetings |
| 75 | [`d3a1c02`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/d3a1c02) | 2026-10-15 14:22 | Ocean | The daily email at 08:30 and the switch on My account (#71) (#74) |
| 76 | [`4f0491f`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/4f0491f) | 2026-10-15 15:01 | Ocean Dekeyser | Daily email: no link to the site's bare IP address |
| 77 | [`974bb1b`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/974bb1b) | 2026-10-15 15:25 | finn6698 | Merge pull request #75 from vives-project-xp/fix/daily-email-no-ip-link |
| 78 | [`74ce500`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/74ce500) | 2026-10-15 15:40 | Ocean | Footer with VIVES socials, address and copyright (#76) (#77) |
| 79 | [`37735ee`](https://github.com/vives-project-xp/ProjectManagementPlatform/commit/37735ee) | 2026-10-15 15:56 | Ocean | Footer: icons for the social media links (#76) (#78) |
