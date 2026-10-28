# Google Calendar two-way sync — setup guide

Goal: ONE shared Google Calendar ("MakerOS") connected to this server,
with two-way sync, for all users. Server has a static private IP (not
public) and Tailscale. This works — here is why and how.

## Why it works without a public IP

Two separate things people confuse:

1. **"Subscribe by URL" (ICS)**: Google's own computers connect TO
   your server to read the feed. They cannot reach a private IP.
   That is why the calendar page offers the ICS token only to
   tailnet clients (Thunderbird, Apple Calendar). Dead end for Google.
2. **Two-way sync (Google Calendar API + OAuth)**: YOUR server opens
   an outbound HTTPS connection to Google (events up, events down).
   Google never connects to you. Outbound works from behind any NAT.

The only inbound hop is the OAuth consent: YOUR BROWSER shows a
Google login page, then Google sends the browser back to your server
with a code. That redirect needs an HTTPS address the browser can
reach — which is exactly what Tailscale gives you.

## Step 0 — give the server its HTTPS address (Tailscale)

On the lab server (one time): `make serve` — it starts MakerOS and
`tailscale serve` together and prints the URL (see `docs/DEPLOY.md`).

Check in a browser (from any tailnet device):

```
https://<machine>.<tailnet>.ts.net
```

You now have a real domain with a valid certificate. Write this URL
down; Google will demand it.

## Step 1 — Google Cloud Console (one time, ~10 minutes)

1. Go to https://console.cloud.google.com (log in with the lab's
   Google account, the one that owns the shared calendar).
2. Top bar: project picker → "New project" → name it `makeros` →
   Create.
3. Menu → "APIs & Services" → "Library" → search **Google Calendar
   API** → Enable.
4. Menu → "APIs & Services" → "OAuth consent screen":
   - User type: **Internal** if this is a Workspace account (best),
     otherwise External.
   - App name `MakerOS`. Add the scopes:
     `.../auth/calendar.events` and `.../auth/calendar.readonly`
     (Calendar API scope picker). No sensitive extras.
5. Menu → "APIs & Services" → "Credentials" → "Create credentials" →
   **OAuth client ID**:
   - Type: **Web application**.
   - Authorized redirect URIs — add exactly:
     ```
     https://<machine>.<tailnet>.ts.net/google/callback
     ```
   - Create, then download the JSON (client secret). Keep it out of
     git; it belongs in the server's environment/vault.

Google accepts `.ts.net` because it is a real domain with a valid
certificate. It rejects bare IPs; `localhost` only for "Desktop app"
clients (dev only).

## Step 2 — make the shared calendar

In Google Calendar (same lab account): create a calendar named
"MakerOS", or pick the existing lab calendar you want to share.
Nothing else needed — MakerOS will list calendars and let you pick
during connect.

## Step 3 — connect MakerOS

The flow (implemented; `makeros/web/gcal.py`):

0. Open **Administración → Integraciones → Google Calendar** and paste
   the ID de cliente and Secreto de cliente from the downloaded JSON
   (fields `client_id` / `client_secret`), then Guardar credenciales.
   No `.env` editing needed; env `GOOGLE_CLIENT_ID/SECRET` still work
   as a fallback for scripted setups. Keep `MAKEROS_BASE_URL=https://
   fedora.tail120260.ts.net` so the redirect URI is
   `https://fedora.tail120260.ts.net/google/callback`.

1. Restart MakerOS, then as admin open **Administración →
   Integraciones → Google Calendar → Conectar con Google**.
2. Google asks you to log in and consent (the browser is on your
   tailnet, so the redirect works).
3. Paste the shared calendar's **ID** (Google Calendar → ajustes del
   calendario → «ID del calendario», e.g.
   `c-abc123@group.calendar.google.com`) and hit Guardar. That one
   calendar is used from then on; no dropdown, no manual sync.
4. Sync is fully automatic:
   - entering `/calendario` pulls changes in the background
     (incremental via Google's sync tokens);
   - creating an event pushes it immediately;
   - a background loop syncs every 5 minutes while anyone browses.
   Pulled Google events become Markdown under `content/calendario/`
   with a `gcal_id` stamp; events created in MakerOS are pushed to
   Google and stamped back; events deleted in Google delete their
   local file. The refresh token lives in SQLite (`ui_settings`),
   never in Markdown; errors show in the admin panel and clear on
   the next successful sync.

Task due-date push (opt-in per project) is the same pipe.

## FAQ

- **Do other lab members need to do this too?** No. One connection,
  one shared calendar. Members see the events because they can read
  the calendar in Google and in MakerOS.
- **Server rebooted / IP changed?** Irrelevant — the connection is
  outbound and the domain stays the same.
- **Is the server reachable from the internet?** No, and it does not
  need to be. Only tailnet members reach `https://<machine>...`.
- **Can Google fetch our ICS feed?** No — see the note above; that
  is a different mechanism, not needed for this.
