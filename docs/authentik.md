# VIVES login: connecting the platform to Authentik

For **VIVES' Superuser**, who sets this up in the Authentik admin panel and on the platform. No changes to the code or the server are needed. It takes about 30 minutes.

When it's done, everyone logs in with **Log in with VIVES**. People exist only in Authentik:

- Their platform account appears at their first login.
- Their Role comes from an Authentik group.
- A Student's Programme and Year come from two attributes.

Once you **switch it on**, the site has no password login and no Test login any more (ADR 0011). The way in when Authentik fails is a one-time link made on the server (step 6).

## What you need

- Admin rights in VIVES' Authentik.
- A **Superuser** login on the platform (today the team's; after the switch, your own through VIVES login).
- SSH access to the VM, for step 6 only.
- The platform's address. Today that's `https://10.20.10.33`. With a hostname, use that address everywhere below.

## 1. Provider (Authentik admin panel)

**Applications → Providers → Create → OAuth2/OpenID Provider**:

| Field | Value |
|---|---|
| Name | `Project Management Platform` |
| Authorization flow | your usual one (e.g. `default-provider-authorization-implicit-consent`) |
| Client type | **Confidential** |
| Client ID / Client Secret | keep the generated values; you paste them on the platform in step 4 |
| Redirect URIs | **Strict**: the redirect URI shown on the platform's **VIVES login** screen, today `https://10.20.10.33/auth/callback` |
| Signing Key | a certificate, e.g. `authentik Self-signed Certificate`. Without one the tokens can't be checked |
| Advanced → Scopes | `openid`, `email`, `profile` (the default *authentik default OAuth Mapping* ones), plus the mapping from step 2 |
| Advanced → Subject mode | the default is fine |
| Advanced → Include claims in id_token | **on** |

The `profile` scope already puts the user's **groups** in the token.

## 2. Programme and Year (property mapping)

Students need their Programme and Year on the platform: the Top 3, the Members overview and "Made by" use them.

1. **Customization → Property Mappings → Create → Scope Mapping**:
   - Name: `PMP: programme and year`
   - Scope name: `profile`
   - Expression:

     ```python
     return {
         "programme": request.user.attributes.get("programme", ""),
         "year": str(request.user.attributes.get("year", "")),
     }
     ```
2. Add this mapping to the provider's scopes from step 1.
3. Give every **student** these attributes: **Directory → Users → (student) → Edit → Attributes**:

   ```yaml
   programme: Electronics-ICT
   year: "2"
   ```

   - **Year** is `1`, `2`, `3` or `International`.
   - **Programme** is the study programme's name. A name the platform doesn't know yet is added to its Programme list automatically.

The attribute names can be changed on the platform's VIVES login screen if VIVES already uses others.

## 3. Application and groups

1. **Applications → Applications → Create**:
   - Name: `Project Management Platform`
   - Slug: `pmp`
   - Provider: the one from step 1
   - Launch URL: `https://10.20.10.33/`

   Its **Issuer URL** is `https://<your-authentik>/application/o/pmp/`. The provider's page shows it as *OpenID Configuration Issuer*.
2. **Directory → Groups**: create the four **Role groups** and put every person in **exactly one**:

   | Group | Role on the platform |
   |---|---|
   | `pmp-superusers` | Superuser (manages the platform; put yourself here) |
   | `pmp-teachers` | Teacher (coaches, Product Owners) |
   | `pmp-students` | Student |
   | `pmp-clients` | Client (people outside VIVES who follow a Project) |

   - No group, or two of them, means the login is refused, with a message saying so.
   - Moving someone to another group changes their Role at their next login. It's refused while their old Role still has links on the platform (a Member of a Project, a Product Owner, a Client following Projects), until those are removed there.
   - You may use other names: set them on the VIVES login screen.
3. Optional: bind the four groups to the application (**Policy / Group / User Bindings**), so nobody else even reaches the platform's login.
4. **Clients** (outside VIVES): give them an Authentik account the way VIVES does for external people (an account or an invitation), and put them in `pmp-clients`. On the platform their Organisation is set by the Superuser on the Users screen.

## 4. The platform's VIVES login screen

Log in on the platform as a Superuser and open **VIVES login** in the menu:

1. Check that the **redirect URI** shown is the one you entered in step 1.
2. Fill in the **Issuer URL**, **Client ID** and **Client secret**. The secret is stored and never shown again; leave it empty later to keep it.
3. Check the four group names and the two attribute names.
4. **Save**, then **Check the connection**. It should say "Connected to … : 1 signing key(s)". If it can't be reached:
   - the server can't reach Authentik: outgoing 443 from the VM;
   - Authentik's certificate isn't trusted by the server: ask VIVES IT;
   - or the Issuer URL is wrong: it ends with `/application/o/<slug>/`.

(VIVES IT can also put `AUTHENTIK_ISSUER_URL`, `AUTHENTIK_CLIENT_ID` and `AUTHENTIK_CLIENT_SECRET` in `/opt/pmp/.env` instead; the screen then shows them as set on the server.)

## 5. Setup test and Switch on

1. Click **Test login**, log in with **your own** VIVES account and come back. The screen shows what Authentik sent (email, name, groups, programme, year) and the **Role** that gives. Nobody is created.
2. It must say **superuser**. If it doesn't:
   - put yourself in `pmp-superusers`;
   - check that the *Include claims in id_token* setting is on;
   - check that the groups appear.

   Then test again. Any change to the settings needs a new test.
3. Optional: ask a student to try nothing yet. Their login only works once it's switched on.
4. Click **Switch on** and confirm.

From now on:

- the login page shows only **Log in with VIVES**;
- password logins, the Test login, creating or importing Users and resetting passwords are gone;
- name, email, Role, Programme and Year follow Authentik at every login.

## 6. The way in when Authentik fails (server)

On the VM (SSH), as root:

```sh
docker exec pmp-backend-1 pmp-break-glass                    # the only Superuser
docker exec pmp-backend-1 pmp-break-glass you@vives.be       # when there are several
```

- It prints a **one-time login link**: valid 15 minutes, usable once, logged.
- Open it in a browser to get in as that Superuser.
- Try it once now, so you know it works, and keep this page.

To switch VIVES login **off** (back to password login as before):

```sh
docker exec pmp-backend-1 pmp-vives-login-off
```

## 7. Clean up the test accounts

The student team's test Users (`…@pmp.local`, the dummy `vivesbruggepx6+…` addresses) aren't in Authentik, so they can't log in any more. Remove them and their test data with the steps in [`handover.md`](handover.md) section 10. Also remove `DEV_LOGIN` from `/opt/pmp/.env`; it's already ignored while VIVES login is on.

## If the address changes

When VIVES IT gives the site a hostname (`SITE_URL`), the redirect URI changes to `https://<hostname>/auth/callback`:

1. Update it in the provider (step 1).
2. Do a Setup test again: switch off on the server, test, switch on.
