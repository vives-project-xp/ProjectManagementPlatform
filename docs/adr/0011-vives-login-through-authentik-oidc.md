# VIVES login through Authentik (OpenID Connect), checked by the backend

People log in through VIVES' existing Authentik with OpenID Connect (Authorization Code flow with PKCE). The frontend only sends the browser to Authentik and receives it back at `/auth/callback`: that redirect is done by the browser, so it works while the site has only a private IP. The frontend hands the code (with the PKCE verifier) to the backend, which exchanges it at Authentik's token endpoint, checks the ID token (signature from Authentik's published keys, issuer, audience, nonce, expiry), finds or creates the User from its claims and issues the platform's usual session token. The REST API stays private (ADR 0006); the VM only needs outgoing HTTPS to Authentik.

Roles come from Authentik groups (one Role group per Role) and a Student's Programme and Year from user attributes, so Authentik is the one place where people are managed. The connection is set up on a Superuser screen (stored in the database; `AUTHENTIK_*` in `.env` as an alternative) and only switched on after a Setup test that gave the Superuser Role. Once on, the site has no password login and no Test login at all; the way in when Authentik fails is a one-time Break-glass link printed by a command on the VM, and switching VIVES login off is also only a VM command.

## Considered options

- **Run our own Authentik on the VM**: a database, Redis, a server and a worker on a 4 GB VM, maintained by the team. VIVES already runs one.
- **SAML or LDAP**: OIDC is the simplest fit for a web app and Authentik's standard.
- **Let the frontend do the token exchange**: the backend owns Users and sessions; checking tokens there keeps one place that decides who is who.
- **A hidden password form for the Superuser as break-glass**: any public password form can be found and attacked; a command on the VM needs VM access first.

## Consequences

- A User's platform record is created at their first VIVES login; nobody creates Users by hand any more, and Temporary passwords, the CSV import and password resets disappear.
- Changing someone's Role or Programme happens in Authentik and takes effect at their next login (refused while the old Role still has links).
- If Authentik is unreachable nobody can log in, except through the Break-glass link.
