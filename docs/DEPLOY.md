# MakerOS — Deployment on the lab server (IP / Tailscale)

The app is reachable by bare IP on the university network and via
Tailscale from outside. No public domain is required for normal use.

## 1. Basic: bare IP over HTTP

```bash
make setup
cp .env.example .env        # set MAKEROS_SECRET_KEY
make run                    # binds 0.0.0.0:8000
```

Notes:

- Uvicorn already binds `0.0.0.0`, so the app is reachable from other
  machines. Open the firewall port if needed.
- Do NOT set `MAKEROS_COOKIE_SECURE` — the Secure flag kills session
  cookies on plain HTTP.
- Set `MAKEROS_BASE_URL=http://<server-ip>:8000` so the calendar ICS
  feed URL shows the external address.
- For Docker Compose (app + Caddy on :8080), see `docker-compose.yml`
  and the `Caddyfile`. Same rule: keep `MAKEROS_COOKIE_SECURE` off
  while the edge speaks plain HTTP.

## 2. HTTPS via Tailscale (recommended)

Tailscale gives every machine a free real domain with valid certs
(MagicDNS + Let's Encrypt provisioned by Tailscale). This unlocks the
Secure cookie flag and the only supported path to Google OAuth.

The Makefile does everything for you:

```bash
make serve            # boots uvicorn + `tailscale serve --bg`,
                     # sets MAKEROS_BASE_URL and MAKEROS_COOKIE_SECURE=1,
                     # prints the URL
make serve-stop      # tailscale serve reset + stops uvicorn
```

Details:

- The URL is auto-detected from `tailscale status` (your
  `https://<machine>.<tailnet>.ts.net`).
- uvicorn binds `127.0.0.1`, so the app is ONLY reachable through the
  tailnet. Use `make serve SERVE_BIND=0.0.0.0` to also serve the
  university LAN over plain HTTP on the machine's IP.
- Logs land in `.makeros.log`; the PID in `.makeros.pid`.
- `make serve-stop` runs `tailscale serve reset`, which clears ALL
  serve configs on that machine — if the box serves other things
  through tailscale, stop those with `tailscale serve` interactive
  commands instead.

### Customizing the tailnet URL

The name is `<machine>.<tailnet>.ts.net`:

- **Machine part**: rename it with `tailscale set --hostname=makeros`
  (then `make serve` serves at `makeros.<tailnet>.ts.net`). Verify
  with `tailscale status`. The tailnet picks the change up on
  reconnect (`tailscale down && tailscale up`).
- **Tailnet part**: fixed by your Tailscale account — `ts.net` names
  cannot be arbitrary domains. For a true custom domain you would need
  public DNS + your own reverse proxy (Caddy) and a certificate, which
  a private/tailnet server cannot get through ACME; keep ts.net.
- **Public internet?** `tailscale funnel` can publish the URL outside
  the tailnet — don't, unless the lab decides the app should be
  world-visible.

Manual equivalent of `make serve`:

```bash
tailscale up
MAKEROS_BASE_URL=https://<machine>.<tailnet>.ts.net MAKEROS_COOKIE_SECURE=1 \
  .venv/bin/uvicorn makeros.main:app --host 127.0.0.1 --port 8000
tailscale serve --bg 127.0.0.1:8000
```

## 3. Google Calendar

Two separate things, often confused:

- **ICS subscribe («Desde la URL» in Google Calendar): does NOT work
  from a private server.** Google's own servers fetch the feed from
  the internet; they cannot reach a lab IP or a tailnet address.
  Subscribe only from tailnet-local clients (Thunderbird, Apple
  Calendar, GNOME Calendar) using the tokenized feed URL shown on the
  calendar page. The token grants read-only event access; admins can
  revoke it from the same panel.
- **Google Calendar two-way sync (OAuth, planned):** needs an HTTPS
  redirect URI. `https://<machine>.<tailnet>.ts.net/...` is accepted
  by Google Cloud Console because ts.net is a real domain with a valid
  certificate. Bare IPs are never accepted as redirect URIs;
  `http://localhost` is only accepted for "Desktop app" type OAuth
  clients, which is a dev-only workaround.

## 4. Reverse proxy details

If you put Caddy or `tailscale serve` in front, forward these headers
so the app sees the real client address and scheme:

- `X-Forwarded-For` (client IP)
- `X-Forwarded-Proto` (https when TLS terminates at the proxy)

Uvicorn reads them with `--proxy-headers`. When running via
`make run`, add the flag manually; in Docker the compose file should
include it on the uvicorn command.

`MAKEROS_BASE_URL` (step 2) makes generated absolute links correct
regardless of proxy headers.
