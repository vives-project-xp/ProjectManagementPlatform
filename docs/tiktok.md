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
