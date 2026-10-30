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

The repo includes `scripts\serve.ps1`, the Windows equivalent of the
Linux `make serve`: it detects your Tailscale URL, starts the app with
the right environment (`MAKEROS_BASE_URL`, secure cookies), waits for
it to come up, and publishes it with `tailscale serve --bg`.

```powershell
.\scripts\serve.ps1                # start (binds 127.0.0.1:8000)
.\scripts\serve.ps1 -Action stop   # stop
.\scripts\serve.ps1 -Action status # what is running
.\scripts\serve.ps1 -Bind 8001     # different local port
.\scripts\serve.ps1 -Lan           # also reachable on the LAN IP (plain HTTP)
```

PowerShell may block scripts: if you get an execution-policy error,
run once as admin:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
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

Stop the server (Ctrl+C won't work — it runs hidden; use the script),
then:

```powershell
.\scripts\serve.ps1 -Action stop
git pull
.venv\Scripts\pip install -e .
.\scripts\serve.ps1
```

Content, database and uploaded images live in `content\`, `data\` and
`private\` inside the folder — updates never touch them.

## 6. Run it always with Servy (recommended for the final server)

`scripts\serve.ps1` dies when you log out. To keep MakerOS running as a
real Windows service (starts on boot, restarts on crash), use
**Servy** — https://servy-win.github.io/ (GitHub: `aelassas/servy`).
It wraps any executable as a native Windows service and has both a GUI
and a CLI.

### Install Servy

Any of these, in an Administrator PowerShell:

```powershell
winget install Servy            # or: choco install servy  /  scoop install servy
```

or download the installer from the
[releases page](https://github.com/aelassas/servy/releases). After
install, `servy-cli` is on the PATH.

### Configure MakerOS as a service

1. Edit `scripts\run-service.bat` and set your real Tailscale URL in
   `MAKEROS_BASE_URL` (`tailscale status` shows it as `DNSName`).
2. Keep the project in a path **without spaces** (e.g. `C:\MakerOS`).
3. Install the service:

```powershell
servy-cli install --name="MakerOS" --displayName="MakerOS" `
  --path="%SystemRoot%\System32\cmd.exe" `
  --params="/c C:\MakerOS\scripts\run-service.bat" `
  --startupDir="C:\MakerOS" `
  --startupType=Automatic `
  --recoveryAction=RestartService `
  --stdout="C:\MakerOS\data\service-stdout.log" `
  --stderr="C:\MakerOS\data\service-stderr.log"
servy-cli start --name="MakerOS"
```

4. Publish it through Tailscale once (this mapping persists across
   reboots, no service needed for it):

```powershell
tailscale serve --bg 127.0.0.1:8000
```

Now the app survives reboots and restarts on crashes. Manage it from
the Servy GUI (`services.msc` also shows it) or the CLI:

```powershell
servy-cli status --name="MakerOS"
servy-cli restart --name="MakerOS"
servy-cli stop --name="MakerOS"
servy-cli uninstall --name="MakerOS"
```

### Updating then becomes

```powershell
git pull
.venv\Scripts\pip install -e .
servy-cli restart --name="MakerOS"
```

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
- **Port already in use** — something else is on 8000: change the port
  in `scripts\serve.ps1 -Bind 8001` (or in `scripts\run-service.bat` for
  the service) and in `tailscale serve --bg 127.0.0.1:8001`.
- **Check what's running** — `.\scripts\serve.ps1 -Action status` (or
  `servy-cli status --name="MakerOS"` on the service) plus
  `tailscale serve status` for the public mapping.
- **After a Tailscale rename** the URL changes — update
  `MAKEROS_BASE_URL` and the Google redirect URI to match.
