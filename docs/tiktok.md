# TikTok

TikTok is the platform's second Channel (spec #145): Projects' videos ticked **Also on TikTok** and the **Weekly slideshow**. This page covers the developer app and connecting the account. Replacing the team's test app with VIVES' own is in [`handover.md`](handover.md) section 9.

## The developer app

At <https://developers.tiktok.com>, under an organisation (today "PX6 Project Management team"), an app of type **Other** with:

- **Login Kit**, with a **redirect URI**. Today it's `https://github.com/vives-project-xp/ProjectManagementPlatform`: the VM has no public address, so TikTok sends the Superuser to the repo page, and the platform only needs the `code` in that address.
- **Content Posting API**, with **Direct Post** switched on.
- **Scopes:** `user.info.basic`, `video.upload`, `video.publish`.
- **Terms of Service** and **Privacy Policy** URLs: [`legal/`](legal/).

A **sandbox** works with the accounts listed as its target users. Until TikTok's **audit** approves the app, everything it posts is visible only to the account itself ("Only me").

## Settings

In `/opt/pmp/.env` (never in the repo):

| Setting | What |
|---|---|
| `TIKTOK_CLIENT_KEY` | The app's (or sandbox's) Client key |
| `TIKTOK_CLIENT_SECRET` | Its Client secret |
| `TIKTOK_REDIRECT_URI` | The redirect URI exactly as registered (default: the repo URL) |

Then recreate the backend: `COMPOSE_PROJECT_NAME=pmp docker compose --env-file /opt/pmp/.env up -d --no-build backend`.

## Connecting the account

Superuser, on **Social media**:

1. Click **Connect TikTok**. TikTok's login opens in a new tab; log in with the account the platform should post to and allow the access.
2. TikTok opens the redirect URI, e.g. `https://github.com/vives-project-xp/ProjectManagementPlatform?code=…&state=…`. Copy the **whole address** from the address bar.
3. Paste it on the Social media screen and click **Connect**, within a few minutes: a code works only once.

The card then shows "Connected as <name>". The access token lasts 24 hours and the platform refreshes it about once a day; the refresh token lasts a year. If a refresh fails, or the access is withdrawn in TikTok, the card shows why and TikTok posts go to To post today until someone clicks **Connect again**.

## Also on TikTok (videos)

In **Review**, a suggestion whose Weekly update has a video shows the tick **Also on TikTok**. Ticked, the reviewer chooses:

- **who can see it**: the options TikTok gives the account (asked at that moment), with no default;
- whether **comments**, **Duet** and **Stitch** are allowed (comments on, Duet and Stitch off by default);
- TikTok's **Music Usage Confirmation** is shown next to it.

Post then puts the video in TikTok's own line, with the same title and caption as the Instagram post: Monday–Friday 17:00 by default (Social media screen), one per Posting time, never the same Project twice in a row. Each Channel's post has its own state: **Pull back from TikTok** takes only the video off, and pulling back the Instagram post leaves the video in TikTok's line.

At its Posting time the platform asks TikTok for the account's creator info and uploads the video file (Direct Post); no public address is needed. A failure is tried once more 10 minutes later; then the video moves to **To post today** (TikTok videos) with the reason: download the video, copy the caption, post it in the TikTok app, press Posted. Without a connected account every video goes there.

**Before the audit** TikTok only lets the app post to a **private** account, and only as "Only me": set the account to Private in the TikTok app (Settings and privacy, Privacy, Private account). Otherwise TikTok refuses with `unaudited_client_can_only_post_to_private_accounts`, which the platform shows as a readable reason.

