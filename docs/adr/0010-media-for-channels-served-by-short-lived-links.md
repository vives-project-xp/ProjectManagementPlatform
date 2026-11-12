# Media for Channels served by short-lived links from our VM

Instagram's API doesn't accept an uploaded photo: it downloads it from a public link (TikTok's photo posts work the same way). Once the VM moves to a network the internet can reach, Caddy also serves `/social/<random code>` publicly: each link points to one Medium of one Scheduled post and works for 1 hour or until that post is published, whichever comes first. Everything else stays unreachable from outside, as ADR 0006 decided.

Until the move, every post goes through the To post today list (Download media, Copy caption, Posted), which also stays the fallback when automatic publishing fails.

## Considered options

- **Temporary cloud storage** (S3, R2, …) with a short-lived link: works today, but adds a paid external service and its credentials, and copies Students' photos to a third party.
- **Waiting with all posting until the move**: simpler, but leaves the Review and planning unused until then.

## Consequences

- Automatic publishing to a Channel goes live only after the VM move; the tickets can be built and tested against a test account before that.
- A guessed link finds nothing: codes are random, single-purpose and expire.
- Videos may be uploadable directly without a link; the real try settles that, and doesn't change this decision for photos.
