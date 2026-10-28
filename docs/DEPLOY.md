# MakerOS — Deployment on Windows (Tailscale URL)

Simple path: the app runs from a Python venv, Tailscale gives you a
real HTTPS URL (`https://<machine>.<tailnet>.ts.net`) with a valid
certificate. No public domain, no Docker, no reverse proxy needed.

## 1. Install once

1. **Python 3.12+** — https://www.python.org/downloads/ (check
   "Add python.exe to PATH" in the installer).
2. **Git** — https://git-scm.com/download/win.
3. **Tailscale** — https://tailscale.com/download, log in, and leave
   it running (icon in the system tray).

Open **PowerShell** and check all three:

```powershell
python --version
git --version
tailscale status
```

## 2. Get the code and set it up

```powershell
cd C:\
git clone <repo-url> MakerOS
cd MakerOS

python -m venv .venv
.venv\Scripts\pip install -e .
```

## 3. Create the admin user

```powershell
.venv\Scripts\python -m makeros.cli adduser jacob --role admin
```

(Prompts for the password. Repeat with other names/roles for more
users — `--role member` or `--role viewer`.)

## 4. Serve through Tailscale

The app must run with the Tailscale URL as its base URL so generated
links (ICS feed, Google OAuth callback) are correct, and with secure
cookies since HTTPS is on:

```powershell
$env:MAKEROS_BASE_URL = "https://<machine>.<tailnet>.ts.net"
$env:MAKEROS_COOKIE_SECURE = "1"
.venv\Scripts\uvicorn makeros.main:app --host 127.0.0.1 --port 8000
```

In a **second** PowerShell window, publish it:

```powershell
tailscale serve --bg 127.0.0.1:8000
```

Done. Open `https://<machine>.<tailnet>.ts.net` from any device on
the tailnet (including the lab's own machines and your laptop over
Tailscale).

Don't know your URL? `tailscale status` shows it in the `DNSName`
field of your own machine (`https://fedora.tail120260.ts.net` in this
lab). You can change the machine part with
`tailscale set --hostname=makeros`; the tailnet part is fixed by your
Tailscale account.

Only tailnet devices can reach it. `tailscale funnel` would expose it
to the public internet — don't use it unless the lab decides so.

## 5. Update the app

Stop the server (Ctrl+C in the first window), then:

```powershell
git pull
.venv\Scripts\pip install -e .
```

Start it again (step 4). Content, database and uploaded images live in
`content\`, `data\` and `private\` inside the folder — updates never
touch them.

## 6. Run it always (optional, recommended for the final server)

Step 4's server dies when you close PowerShell or log out. To keep it
running as a background service, use **NSSM** (the Non-Sucking Service
Manager):

1. Download nssm from https://nssm.cc, put `nssm.exe` somewhere in PATH.
2. In an **Administrator** PowerShell:

```powershell
nssm install MakerOS "C:\MakerOS\.venv\Scripts\uvicorn.exe" "makeros.main:app --host 127.0.0.1 --port 8000"
nssm set MakerOS AppDirectory C:\MakerOS
nssm set MakerOS AppEnvironmentExtra MAKEROS_BASE_URL=https://<machine>.<tailnet>.ts.net MAKEROS_COOKIE_SECURE=1
nssm start MakerOS
```

Now the app survives reboots and restarts on crashes. Updating becomes:
`nssm restart MakerOS` after `git pull`.

To remove it later: `nssm remove MakerOS confirm`.

## 7. Google Calendar sync

With the Tailscale URL serving HTTPS, Google OAuth works:

1. Admin panel → Integraciones → paste Client ID and Client secret
   from Google Cloud Console (see `docs/GCALENDAR.md`).
2. Redirect URI registered in Google Cloud Console must be exactly:
   `https://<machine>.<tailnet>.ts.net/google/callback`
3. Click "Conectar" and authorize with the Google account that owns
   the calendar.

Bare-IP HTTP (no Tailscale) can never do this: Google rejects plain
IP redirect URIs.

## Troubleshooting

- **"tailscale: command not found"** — reinstall Tailscale or open a
  new PowerShell window after installing.
- **Login loops back to the login page** — you forgot
  `MAKEROS_COOKIE_SECURE=1` while serving over `tailscale serve`
  (or set it while serving plain HTTP; Secure cookies only work on
  HTTPS).
- **Port already in use** — something else is on 8000: change the
  port in both windows (`--port 8001` and
  `tailscale serve --bg 127.0.0.1:8001`).
- **Check what's running** — `tailscale serve status` shows the
  active proxy; the uvicorn window shows requests as they come.
- **After a Tailscale rename** the URL changes — update
  `MAKEROS_BASE_URL` and the Google redirect URI to match.
