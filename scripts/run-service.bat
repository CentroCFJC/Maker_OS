@echo off
rem MakerOS Windows service entry point (used by Servy, see docs\DEPLOY.md).
rem Fill in your own Tailscale URL below (tailscale status -> DNSName).
set "MAKEROS_BASE_URL=https://<machine>.<tailnet>.ts.net"
set "MAKEROS_COOKIE_SECURE=1"
cd /d "%~dp0.."
"%~dp0..\.venv\Scripts\uvicorn.exe" makeros.main:app --host 127.0.0.1 --port 8000
