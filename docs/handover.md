# Handover to VIVES IT

The platform runs today on **the student team's own test accounts**: a team Gmail, a GitHub test organisation, a team member's Trello account, a personal school LLM key, and test Instagram and TikTok accounts. This guide moves every one of them to accounts owned by VIVES. Follow it from top to bottom and nothing keeps depending on the team.

Secret values never go in this repository, in chat, or in an issue. They live in **one file on the server**, `/opt/pmp/.env`, plus `/opt/pmp/logins.txt` for the starting accounts. Both are owned by the `github-runner` user, mode `600`.

## 1. What is replaced

| What | Today (student team test) | Replace with (VIVES) | Section |
|---|---|---|---|
| Server | VM `10.20.10.33`, internal network only, no hostname | Same VM (or a new one), with a **hostname** and **certificate**, and `/social/*` reachable from the internet for Instagram/TikTok photos | 2 |
| Code and deploys | Repo `vives-project-xp/ProjectManagementPlatform`, self-hosted runner `px6-vm` | Same repo (or a fork owned by VIVES), runner registered by VIVES | 3 |
| Project repositories | GitHub test organisation `ProjectManagementVives` | The VIVES organisation for student projects (e.g. `vives-project-xp`) and a token from its owner | 4 |
| Trello boards | A team member's **personal** Trello account | A **dedicated** Trello account of VIVES | 5 |
| Daily email | The team's Gmail with an app password | A VIVES mailbox (or VIVES SMTP relay) | 6 |
| AI for Post suggestions | A personal key from the school's LiteLLM portal | A key for VIVES (a service key, not a person's) | 7 |
| Instagram | Test account `@vivesbruggepx6` with the team's Meta app *VIVES PMP* | The real VIVES Instagram, with a Meta app owned by VIVES | 8 |
| TikTok | Team developer app *VIVES PMP* (sandbox), team test account | The real VIVES TikTok, with a TikTok developer app owned by VIVES | 9 |
| Logins | Starting accounts and test Users, **Test login** switched on | Real Superuser, Teachers and Students; Test login off | 10 |

## 2. Server

Requirements: Debian (or another Linux) with **Docker** and **Docker Compose v2**, 2 vCPU, 4 GB RAM, 40 GB disk (more if many videos are kept; staff see a warning above 80%).

1. **Hostname and certificate.** Ask for a DNS name, e.g. `pmp.vives.be`. Then set `SITE_ADDRESS` (and `SITE_URL=https://pmp.vives.be`) in `/opt/pmp/.env`. With a public name, Caddy gets a real certificate by itself. Remove `tls internal` and `default_sni` from the `Caddyfile` in a small PR; they exist only because the site runs on a bare IP.
2. **Open to the internet, at least `/social/*`.** Instagram and TikTok download photos from short-lived links (ADR 0010). Caddy already forwards only `/social/<code>` and the health check to the backend (ADR 0006); everything else stays the normal site. Set `PUBLIC_MEDIA_URL=https://pmp.vives.be`.
3. **Ports:** 80 and 443 in, and 443 out (GitHub, Trello, Meta, TikTok, the LLM, Google Fonts) plus 587 out (SMTP).
4. **Backups:** the `backup` service writes nightly database dumps and weekly media archives to `/opt/pmp/backups` on the same VM, so they still need copying off the VM. See [`backups.md`](backups.md).

## 3. Code and deploys

1. **Repository:** keep `vives-project-xp/ProjectManagementPlatform`, or fork it into a VIVES organisation. Every change goes through a pull request; CI runs on GitHub's own runners.
2. **Self-hosted runner** on the VM (Deploy only, ADR 0001):
   - Repo → **Settings → Actions → Runners → New self-hosted runner** (Linux x64). Install it under a user `github-runner` in the `docker` group, with the labels `self-hosted, linux, x64, vm`, as a systemd service (`./svc.sh install github-runner && ./svc.sh start`).
   - Remove the old runner `px6-vm` from the repo settings.
   - The repo is **public**, so the runner is only used for pushes to `main`, never for pull requests. Keep it that way.
3. **First deploy:** create `/opt/pmp/.env` (section 11) and `/opt/pmp/logins.txt` (section 10), owned by `github-runner`, mode `600`. Then push to `main` (or re-run the last **Deploy** workflow). The Deploy builds the images, runs the database migrations, starts everything, checks `/api/health` and runs a restore test of the backup.

## 4. GitHub: Project repositories

The platform creates one public, empty repository per Project in an organisation, and gives Members write access and the Product Owner admin access (spec #49).

1. Pick the organisation, e.g. `vives-project-xp`. Its **owner** creates a **fine-grained personal access token**:
   - Resource owner: that organisation. Repository access: **All repositories**.
   - Permissions: Repository **Administration: Read and write** (creating repositories, inviting collaborators) and **Metadata: Read**; Organisation **Members: Read**.
   - The longest expiry the organisation allows, with a calendar reminder to renew it.
2. In `/opt/pmp/.env`: `GITHUB_ORG=<organisation>` and `GITHUB_TOKEN=<token>`.
3. **Clean up the test organisation:** the repositories already created in `ProjectManagementVives` stay there; move them with GitHub's **Transfer** if they should be kept, otherwise delete them. Then delete the team's old token (GitHub → Settings → Developer settings → Fine-grained tokens).
4. Projects that already have a repository keep pointing at the old one. Re-linking isn't built in, so transfer those repositories first, or ask the team for a small script.

## 5. Trello: Project boards

One free Workspace per Project with one private board (lists Backlog/To do/Doing/Review/Done), owned by **one dedicated Trello account** (spec #61, ADR 0007).

1. Create a Trello account for VIVES, e.g. `pmp@vives.be` (not a person's own account).
2. Logged in as that account, go to <https://trello.com/power-ups/admin> → **New** (a Power-Up / API key for "VIVES PMP") → **API key**. Next to the key, click **Token** and allow it. That gives the token.
3. In `/opt/pmp/.env`: `TRELLO_API_KEY=<key>` and `TRELLO_TOKEN=<token>`.
4. **Clean up:** the boards made so far belong to the team member's personal account. Either keep them and add the VIVES account as admin (Trello → board → Share), or let the platform make new ones. Then the team member **revokes** the old token: Trello → Account → Settings → Applications → Revoke.

## 6. Email: the 08:30 Daily email

1. A VIVES mailbox that may send over SMTP with STARTTLS (port 587), or the VIVES SMTP relay.
2. In `/opt/pmp/.env`: `SMTP_HOST`, `SMTP_PORT=587`, `SMTP_USER`, `SMTP_PASSWORD`, `MAIL_FROM="VIVES Project Experience <pmp@vives.be>"`, and `SITE_URL` (the address in the email's link).
3. **Clean up:** in the team's Gmail, delete the app password (Google account → Security → App passwords) and change the account's password.

## 7. AI: Post suggestions

The school's shared LLM endpoint (ADR 0009) at `https://api.llm.mechatronics.be/v1`, model `qwen3.8-27b`.

1. Ask the endpoint's owner for a key in VIVES' name (a service key), not a person's.
2. In `/opt/pmp/.env`: `LLM_API_KEY=<key>` (keep `LLM_BASE_URL` and `LLM_MODEL` unless the endpoint changes).
3. **Clean up:** the team member deletes their personal key in the LiteLLM portal.

## 8. Instagram

Full details are in [`instagram.md`](instagram.md). In short:

1. The VIVES Instagram account must be a **Business** (professional) account.
2. A **Meta developer app** owned by VIVES, under a **business portfolio** of VIVES (business.facebook.com). Since 2026, Meta gives new apps **API setup with Unified login**: Instagram API → configuration with the Instagram account as asset → **2. Generate access tokens** lists the account with its id (`1784…`).
3. In `/opt/pmp/.env`:
   - `INSTAGRAM_TOKEN=<token>`
   - `INSTAGRAM_API_URL=https://graph.facebook.com/v23.0`
   - `INSTAGRAM_ACCOUNT_ID=<the 1784… id>`
   - `INSTAGRAM_REFRESH_URL=` (empty: this token never expires)
   - `PUBLIC_MEDIA_URL=https://<hostname>` (for photo posts; section 2)
4. To post for real (not only for app roles), the app needs Meta's **App Review** for `instagram_business_basic` / `instagram_content_publish` and a **verified business portfolio**.
5. **Clean up:**
   - remove the test Reel on `@vivesbruggepx6`;
   - in the team's portfolio, remove the team's people, or **transfer the app**: add VIVES admins to the app (App roles) and the portfolio, then remove the students;
   - stop using the old token.

## 9. TikTok

The TikTok part (Weekly slideshow, Project videos) is the next spec. What exists today: the team's developer app *VIVES PMP* (organisation "PX6 Project Management team", sandbox `test`) at <https://developers.tiktok.com>.

1. A TikTok developer **organisation** for VIVES, with an app (type **Other**): products **Login Kit** and **Content Posting API** (Direct Post), scopes `user.info.basic`, `video.upload`, `video.publish`.
2. Terms of Service and Privacy Policy: [`legal/terms-of-service.md`](legal/terms-of-service.md) and [`legal/privacy-policy.md`](legal/privacy-policy.md) (adapt the contact to VIVES). TikTok wants **verified URLs** (URL properties) for production. Put them on the VIVES domain, or verify a GitHub Pages address.
3. Until TikTok's **audit** is approved, everything an app posts is visible only to the account itself, and the account must be set to **Private** in the TikTok app (otherwise TikTok refuses every post). The audit needs a demo video of the working flow.
4. **Settings** in `/opt/pmp/.env` (see [`tiktok.md`](tiktok.md)):
   - `TIKTOK_CLIENT_KEY` and `TIKTOK_CLIENT_SECRET`: the VIVES app's **Client key** and **Client secret** (app page, "Credentials");
   - `TIKTOK_REDIRECT_URI`: the redirect URI registered under Login Kit. Today it's the GitHub repo's address; with a hostname it can be any page of the VIVES site. The value in `.env` must match the registered one exactly.

   - once the VM is public (`PUBLIC_MEDIA_URL`): in the developer portal, add the URL prefix `<PUBLIC_MEDIA_URL>/social/` for the Content Posting API; TikTok gives a file name and content to put at that prefix: set them as `TIKTOK_VERIFICATION_FILE` and `TIKTOK_VERIFICATION_CONTENT`, recreate the backend, then press Verify. Until then the Weekly slideshow is posted by hand from To post today.

   Recreate the backend, then the Superuser clicks **Connect TikTok** on the **Social media** screen, logs in with the VIVES TikTok account and pastes the address TikTok opens. The platform keeps the account's tokens in the database and refreshes them every day. The connection lasts a year without use; the screen says when to connect again.
5. **Clean up:** invite VIVES into the team's TikTok organisation and hand over ownership, or delete the team's app once VIVES has its own.

## 10. Logins and test data

**VIVES login (Authentik) replaces all of this.** Follow [`authentik.md`](authentik.md): connect the platform to VIVES' Authentik on the **VIVES login** screen, test it and switch it on. From then on people exist only in Authentik (Role from a group, a Student's Programme and Year from attributes), there is no password login and no Test login on the site, and the way in when Authentik fails is `docker exec pmp-backend-1 pmp-break-glass` on the VM. The steps below are for before that switch.

1. `/opt/pmp/logins.txt`: one line per Role, `role,email,password`, for the **first** Superuser, Teacher and Student. They're created only when there are no Users at all, and each must choose a new password at the first login. On an existing database this file changes nothing.
2. **Switch off the Test login:** remove `DEV_LOGIN=true` from `/opt/pmp/.env` and recreate the backend (section 12). Until then anyone on the network can log in as any User.
3. **Remove the team's test Users and data:** the dummy Students and Teachers (`…+studentNN` / `…+teacherNN` addresses of the team Gmail), test Projects, test Weekly updates and the demo Post suggestion. The Superuser can delete Users without links; others are deactivated.
4. Create the real Users: **Users → New user** or **Import CSV** (Teacher, Student or Client, with generated Temporary passwords).

## 11. `/opt/pmp/.env`: every setting

Empty or missing optional settings switch that feature off (the platform keeps working).

| Setting | Required | What |
|---|---|---|
| `SITE_ADDRESS` | yes | What Caddy serves: the hostname (or the bare IP for now) |
| `SITE_URL` | | The site's address in emails, e.g. `https://pmp.vives.be` |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | yes | The database. Changing them on an existing database needs a manual step, so keep them |
| `JWT_SECRET` | yes | Signs login tokens: `openssl rand -hex 32`. Changing it logs everyone out |
| `STORAGE_SECRET` | yes | Signs the browser session: `openssl rand -hex 32` |
| `LOGINS_PATH` | yes | `/opt/pmp/logins.txt` |
| `DEV_LOGIN` | | `true` only while testing; **remove for real use** |
| `GITHUB_ORG`, `GITHUB_TOKEN` | | Section 4 |
| `TRELLO_API_KEY`, `TRELLO_TOKEN` | | Section 5 |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `MAIL_FROM` | | Section 6 |
| `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY` | | Section 7 |
| `INSTAGRAM_TOKEN`, `INSTAGRAM_API_URL`, `INSTAGRAM_ACCOUNT_ID`, `INSTAGRAM_REFRESH_URL` | | Section 8 |
| `PUBLIC_MEDIA_URL` | | Section 2: the public address Instagram/TikTok download photos from |
| `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET`, `TIKTOK_REDIRECT_URI` | | Section 9 |
| `AUTHENTIK_ISSUER_URL`, `AUTHENTIK_CLIENT_ID`, `AUTHENTIK_CLIENT_SECRET` | | VIVES login, as an alternative to the VIVES login screen ([`authentik.md`](authentik.md)) |
| `TIKTOK_VERIFICATION_FILE`, `TIKTOK_VERIFICATION_CONTENT` | | Section 9: TikTok's URL-prefix verification of `PUBLIC_MEDIA_URL/social/` |
| `FOOTER_INSTAGRAM`, `FOOTER_TIKTOK`, `FOOTER_YOUTUBE`, `FOOTER_LINKEDIN`, `FOOTER_PRIVACY_URL`, `FOOTER_ADDRESS` | | The footer links; empty keeps the VIVES default, `none` hides one |
| `BACKUP_PATH` | | Where backups go, default `/opt/pmp/backups` |

How to write the file safely:
- one `KEY=value` per line, no spaces around `=`, and no quotes unless the value has spaces;
- **Unix line endings**: a Windows `\r` at the end of a line becomes part of the value and breaks tokens;
- `chown github-runner:github-runner /opt/pmp/.env && chmod 600 /opt/pmp/.env`.

## 12. After changing `.env`

From the runner's checkout (`/home/github-runner/actions-runner/_work/ProjectManagementPlatform/ProjectManagementPlatform`):

```bash
COMPOSE_PROJECT_NAME=pmp docker compose --env-file /opt/pmp/.env up -d --no-build backend frontend
```

(`caddy` too after changing `SITE_ADDRESS`.) The site is unreachable for a few seconds. Check it with `curl -s https://<hostname>/api/health`, which should answer `{"status":"ok","database":"ok"}`.

## 13. Checklist

- [ ] Hostname + certificate, `SITE_ADDRESS`/`SITE_URL`, `/social/*` reachable, `PUBLIC_MEDIA_URL`
- [ ] Runner registered by VIVES, old runner `px6-vm` removed
- [ ] GitHub: VIVES organisation + token; test repositories transferred or deleted; old token deleted
- [ ] Trello: dedicated VIVES account + key/token; the personal token revoked
- [ ] Email: VIVES mailbox; the team Gmail app password deleted
- [ ] LLM: VIVES key; the personal key deleted
- [ ] Instagram: VIVES Business account, VIVES Meta app + App Review; the team's app handed over or removed; test Reel deleted
- [ ] TikTok: VIVES developer organisation + app + audit; the team's app handed over or removed
- [ ] `DEV_LOGIN` removed; test Users and test data removed; real Users created
- [ ] VM root password changed; backups copied off the VM
