# Post suggestions from the school LLM with fixed inputs

Post suggestions are made by the school's shared LLM endpoint (`https://api.llm.mechatronics.be/v1`, OpenAI-compatible, model `qwen3.8-27b`), called only by the backend with a personal API key from the school's LiteLLM portal. Users never talk to the AI: there is no chat box, and the AI has no tools and no database access. The backend sends a fixed set of inputs: the Project's title, the Weekly update's text and the chosen Media (the 3 best photos by the Quality check's score, plus a small copy of the video; a test on 2026-11-12 showed the endpoint understands video, including 3 photos and a video in one request), and nothing else, so no names, emails, settings or keys. Its reply is untrusted: it must match a strict JSON schema, is cut to length and escaped, and is never published without a person's Review.

The endpoint takes at most 4 images per request (8,847,360 pixels and 40 MiB in total; JPEG, PNG or WebP as base64), which is why the photos are pre-selected locally.

## Considered options

- **A commercial API** (OpenAI, Anthropic, …): more capable, but costs money per call, needs a payment method and sends Students' photos to a third party outside the school.
- **An AI the reviewer can chat with** ("make it funnier"): handy, but every message is a way in for social engineering (the reason for this decision), and editing the text by hand does the same job.

## Consequences

- A Student who writes instructions in the Weekly update ("ignore your rules…") can at worst change the suggested caption, which a Teacher reads before Posting.
- The key lives only in `/opt/pmp/.env` on the VM and in a local file outside the repo; tests use a fake AI client.
- When the endpoint is down or replies badly, staff Generate again or write the post themselves; nothing else depends on it.
- Switching models is a setting, not code.
