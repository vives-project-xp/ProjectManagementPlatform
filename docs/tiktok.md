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

## Weekly slideshow: put together and reviewed

At the **Slideshow cut-off** (Friday 12:00 by default, Social media screen) the platform puts the Weekly slideshow together for the latest Upload week whose Post suggestions were made, from every Project whose suggestion was **Posted** (scheduled, published or posted by hand), in the order they were Posted:

- per Project one photo: a different one than its Instagram post when it has one, otherwise the same;
- with fewer than 4 photos, more photos of the same Projects (best first) until there are 4; never one photo twice; at most 35;
- no Posted Project with a photo: no slideshow that week (the card says so).

The AI (ADR 0009) then writes a title (at most 90 characters) and a Dutch caption from the Projects' titles only, with the Fixed hashtags; it gets no photos and no names. After 3 failed tries staff write it themselves.

Any Teacher or the Superuser reviews it in the **Weekly slideshow** card at the top of **Post suggestions**: move photos earlier or later, swap one for another photo of the same Project, remove one, edit the title and caption, **Generate again** (puts it together again, also with Projects Posted after the cut-off) or **Refuse** (no slideshow that week). Then **Post** it (below).

## Weekly slideshow: posting

**Post** on the card: posted before its Posting time (Friday 18:00 by default) it waits for that time; posted after it, it goes out within a minute. Until then **Pull back** takes it back to Review. A slideshow that still isn't Posted when the next one is put together (the next cut-off) is dropped: "Not posted in time".

At its Posting time:

- **Automatically**, once the site is reachable from the internet (`PUBLIC_MEDIA_URL`) and TikTok is connected: the platform makes a Publish link per photo and sends the slideshow to the account's **TikTok inbox** (upload mode, with TikTok's automatic music). It shows **"In the TikTok app: choose the song"**: open TikTok on the account, find it in the inbox, pick and listen to a song, choose who can see it, post it. A failure is tried once more 10 minutes later, then it goes to To post today.
- **By hand** until then: it appears on **Scheduled posts** under *To post today: Weekly slideshow* with **Download photos** (one zip in order, `01-<project>.jpg` …) and **Copy caption**: make the photo post in the TikTok app with a song.

Either way, **Posted** only works after ticking *"I listened to the song and posted it in the TikTok app"* (the Song check). The team's Weekly update then says "In the Weekly slideshow of <date>", and its photos are kept by the 4-month clean-up.

**Verified URL prefix.** TikTok only downloads photos from a verified address. Once `PUBLIC_MEDIA_URL` is set, add the URL prefix `<PUBLIC_MEDIA_URL>/social/` in the developer portal (Content Posting API), and put the file name and content TikTok gives in `TIKTOK_VERIFICATION_FILE` and `TIKTOK_VERIFICATION_CONTENT`; the backend serves it at that prefix. Recreate the backend, then press Verify.

