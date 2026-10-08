# Only the frontend is public; the REST API stays inside Docker

Browsers only talk to the NiceGUI frontend. The frontend calls the backend's REST API over the Docker network (ADR 0003), and it serves Project photos to the browser through its own route. So Caddy forwards only `/api/health` to the backend, for the Deploy workflow's health check, and answers every other `/api/...` request with 404. Anyone on the VIVES network can reach the site, and this keeps the API out of their reach: its endpoints, error messages and the test login (`DEV_LOGIN`).

Together with this, Caddy sets the security headers `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer` and a restrictive `Permissions-Policy`, and drops the `Server` header. The frontend's session cookie carries the `Secure` flag (`SECURE_COOKIES=true`) and `SameSite=Lax`. The backend locks an email for 15 minutes after 5 wrong passwords.

## Considered options

- **Keep the whole API public**: it would allow a separate client later, such as a mobile app, but nothing needs that now. When something does, open the needed paths in the `Caddyfile` deliberately.

## Consequences

- To try the API by hand, use the backend container on the VM (`docker exec pmp-backend-1 ...`) or a local run, not `https://10.20.10.33/api/...`.
- No HSTS while the certificate is signed by Caddy's internal CA. With HSTS, browsers would no longer let people click through the certificate warning. Add it once VIVES IT provides a hostname with a trusted certificate.
- The login lockout is kept in the backend's memory: a restart (every deploy) clears it, and it assumes one backend process.
