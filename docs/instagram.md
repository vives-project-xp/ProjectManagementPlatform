# Automatic publishing on Instagram (#117)

Scheduled posts are published on Instagram at their Posting time by `services/publishing.py`. Reels are uploaded directly. Photo posts need a Publish link that Instagram downloads from (ADR 0010). Without the settings below, every post goes through **To post today**, as before.

## Settings (`/opt/pmp/.env` only, never in the repo)

| Setting | What |
|---|---|
| `INSTAGRAM_TOKEN` | The long-lived token of the team's Instagram **Business** account (Instagram API with Instagram Login). It is only the first one: the backend stores it in `channel_tokens`, refreshes it a week before it expires (tokens last 60 days), and keeps using the stored one. Removing the setting turns publishing off. |
| `INSTAGRAM_ACCOUNT_ID` | The account's Instagram user id; `me` (the default) means the token's own account. |
| `PUBLIC_MEDIA_URL` | `https://<public hostname>`, only once the VM is reachable from the internet. Without it, Reels are still published automatically, but photo posts go to To post today with a notice. |

After changing `.env`, recreate the backend:

```
COMPOSE_PROJECT_NAME=pmp docker compose --env-file /opt/pmp/.env up -d --no-build backend
```

(run it from the runner checkout).

## Getting the token

1. Make the team's test Instagram account a **Business** (or Creator) account.
2. In a Meta app with the *Instagram API with Instagram Login* product, add the account as a tester. Then generate a token with `instagram_business_basic` and `instagram_business_content_publish`.
3. Put the token in a local file (for example `C:\ProjectManagement\instagram-token.txt`) and in `/opt/pmp/.env`. Never put it in chat.

## Real try

1. Set `INSTAGRAM_TOKEN` (no `PUBLIC_MEDIA_URL` yet), recreate the backend, and check **Scheduled posts**. The notice should say Reels are automatic.
2. Post a suggestion whose chosen medium is the **video**. At its Posting time it should appear on the account. **Scheduled posts → Published** then shows **View on Instagram**.
3. Once VIVES IT makes the VM reachable, set `PUBLIC_MEDIA_URL` and try a photo post the same way.
4. Comment the result on #117.

## Failures

- A failed publish is tried once more 10 minutes later. After that, the post moves to To post today, showing the reason.
- A failed token refresh shows a notice on Scheduled posts, with the date the token stops working. It is tried again a day later.
- Publish links stop working after 1 hour or as soon as their post is published. The daily clean-up deletes the expired ones.
