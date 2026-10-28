# Serve MakerOS over the Tailscale URL (HTTPS) — Windows equivalent of
# `make serve` / `make serve-stop` / `make serve-status`.
#
#   .\scripts\serve.ps1                start + tailscale serve --bg
#   .\scripts\serve.ps1 -Action stop   stop the server + clear serve
#   .\scripts\serve.ps1 -Action status what is running
#   .\scripts\serve.ps1 -Lan           also bind 0.0.0.0 (university LAN IP)
#   .\scripts\serve.ps1 -Bind 8001     local uvicorn port (default 8000)

param(
  [ValidateSet("serve", "stop", "status")]
  [string]$Action = "serve",
  [int]$Bind = 8000,
  [switch]$Lan
)

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
$uvicorn = Join-Path $root ".venv\Scripts\uvicorn.exe"
$pidFile = Join-Path $root ".makeros.pid"
$logFile = Join-Path $root ".makeros.log"

function Get-TsUrl {
  $status = tailscale status --json | ConvertFrom-Json
  $dns = $status.Self.DNSName
  if (-not $dns) {
    Write-Host "tailscale no está conectado (prueba: tailscale up)"; exit 1
  }
  return "https://" + $dns.TrimEnd(".")
}

function Read-Pid {
  if (-not (Test-Path $pidFile)) { return $null }
  try { return [int](Get-Content $pidFile) } catch { return $null }
}

switch ($Action) {
  "status" {
    $proc = Get-CimInstance Win32_Process -Filter "Name = 'uvicorn.exe'"
    if ($proc) { $proc | Format-Table ProcessId, CommandLine -AutoSize }
    else { Write-Host "uvicorn no está corriendo" }
    Write-Host "== tailscale serve =="
    try { tailscale serve status } catch { }
    return
  }
  "stop" {
    try { tailscale serve reset } catch { }
    $old = Read-Pid
    if ($old) {
      try { Stop-Process -Id $old -Force -ErrorAction Stop; Write-Host "Parado ($old)." }
      catch { Write-Host "El proceso $old ya no está." }
      Remove-Item $pidFile
    } else {
      Write-Host "No hay archivo .makeros.pid; revisa con -Action status."
    }
    return
  }
  "serve" {
    if (-not (Get-Command tailscale -ErrorAction SilentlyContinue)) {
      Write-Host "tailscale no está instalado: https://tailscale.com/download"; exit 1
    }
    $old = Read-Pid
    if ($old) {
      try {
        Get-Process -Id $old -ErrorAction Stop | Out-Null
        Write-Host "Ya hay un servidor (.\scripts\serve.ps1 -Action stop primero)."; exit 1
      } catch { Remove-Item $pidFile }
    }
    $url = Get-TsUrl
    $bindHost = if ($Lan) { "0.0.0.0" } else { "127.0.0.1" }
    Write-Host "Iniciando MakerOS en $url ..."
    $env:MAKEROS_BASE_URL = $url
    $env:MAKEROS_COOKIE_SECURE = "1"
    $proc = Start-Process -FilePath $uvicorn `
      -ArgumentList "makeros.main:app --host $bindHost --port $Bind" `
      -RedirectStandardOutput $logFile -RedirectStandardError ".makeros.err.log" `
      -WindowStyle Hidden -PassThru
    $proc.Id | Set-Content $pidFile
    for ($i = 0; $i -lt 40; $i++) {
      try {
        Invoke-WebRequest -Uri "http://127.0.0.1:$Bind/login" -UseBasicParsing `
          -TimeoutSec 2 | Out-Null
        break
      } catch { Start-Sleep -Milliseconds 250 }
    }
    tailscale serve --bg "$bindHost`:$Bind"
    Write-Host ""
    Write-Host "  MakerOS:  $url"
    Write-Host "  Log:      .makeros.log   (.\scripts\serve.ps1 -Action stop para parar)"
  }
}
