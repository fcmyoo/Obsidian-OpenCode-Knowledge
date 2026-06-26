# ============================================================
# OpenCode + Obsidian 诊断脚本
# 适用于 Windows
# ============================================================
param(
    [string]$VaultPath = "$env:USERPROFILE\Desktop\我的知识库",
    [int]$Port = 14096,
    [string]$Host = "127.0.0.1",
    [switch]$KillPort,
    [switch]$StartTest
)

$ErrorActionPreference = "Continue"

function Write-OK { param($msg) Write-Host "[OK] $msg" -ForegroundColor Green }
function Write-WARN { param($msg) Write-Host "[WARN] $msg" -ForegroundColor Yellow }
function Write-ERR { param($msg) Write-Host "[ERR] $msg" -ForegroundColor Red }
function Write-Section { param($msg) Write-Host ""; Write-Host "== $msg ==" -ForegroundColor Cyan }

$PLUGIN_DIR = Join-Path $VaultPath ".obsidian\plugins\opencode-obsidian"
$PLUGIN_DATA = Join-Path $PLUGIN_DIR "data.json"
$PLUGIN_MAIN = Join-Path $PLUGIN_DIR "main.js"
$LOG_DIR = Join-Path $env:LOCALAPPDATA "opencode\logs"
$HEALTH_URL = "http://$Host`:$Port/global/health"

$NODE_BIN = Get-Command node -ErrorAction SilentlyContinue
$OPENCODE_BIN = Get-Command opencode -ErrorAction SilentlyContinue

Write-Section "Environment"
Write-Host "Vault: $VaultPath"
Write-Host "Host:  $Host"
Write-Host "Port:  $Port"
Write-Host "Node:  $($NODE_BIN.Source ?? '<not found>')"
Write-Host "OpenCode: $($OPENCODE_BIN.Source ?? '<not found>')"

Write-Section "Binary Checks"
if ($NODE_BIN) {
    Write-OK "node found"
    try {
        node --version
    } catch {
        Write-WARN "Failed to run node --version"
    }
} else {
    Write-ERR "node not found in PATH"
}

if ($OPENCODE_BIN) {
    Write-OK "opencode found"
    try {
        opencode --version
    } catch {
        Write-WARN "Failed to run opencode --version"
    }
} else {
    Write-ERR "opencode not found in PATH"
}

Write-Section "Vault Checks"
if (Test-Path $VaultPath) {
    Write-OK "Vault directory exists"
} else {
    Write-ERR "Vault directory does not exist"
}

if (Test-Path $PLUGIN_DIR) {
    Write-OK "Plugin directory exists: $PLUGIN_DIR"
} else {
    Write-WARN "Plugin directory not found: $PLUGIN_DIR"
}

Write-Section "Port Check"
$portProcess = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue |
    Where-Object { $_.State -eq 'Listen' }
if ($portProcess) {
    Write-WARN "Port $Port is in use"
    $portProcess | Format-Table -AutoSize
} else {
    Write-OK "Port $Port is free"
}

if ($KillPort) {
    Write-Section "Kill Port"
    if (-not $portProcess) {
        Write-WARN "Nothing is listening on port $Port"
    } else {
        $pids = $portProcess | Select-Object -ExpandProperty OwningProcess -Unique
        Write-Host "Trying to stop PIDs: $pids"
        foreach ($pid in $pids) {
            try {
                Stop-Process -Id $pid -Force -ErrorAction Stop
                Write-OK "Stopped process $pid"
            } catch {
                Write-ERR "Failed to stop process $pid"
            }
        }
        Start-Sleep 1
        $remaining = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue |
            Where-Object { $_.State -eq 'Listen' }
        if ($remaining) {
            Write-ERR "Port $Port is still occupied"
        } else {
            Write-OK "Port $Port has been released"
        }
    }
}

Write-Section "Health Check"
try {
    $healthBody = Invoke-WebRequest -Uri $HEALTH_URL -TimeoutSec 3 -ErrorAction Stop
    Write-OK "Health endpoint reachable: $HEALTH_URL"
    Write-Host $healthBody.Content
} catch {
    Write-WARN "Health endpoint is not reachable: $HEALTH_URL"
}

Write-Section "Plugin Config"
if (Test-Path $PLUGIN_DATA) {
    Write-OK "Found plugin data.json"
    Get-Content $PLUGIN_DATA | Select-Object -First 20
} else {
    Write-WARN "Plugin data.json not found"
}

if (Test-Path $PLUGIN_MAIN) {
    $mainContent = Get-Content $PLUGIN_MAIN -Raw
    if ($mainContent -match 'fetch\(`.http://\$\{this\.settings\.hostname\}:\$\{this\.settings\.port\}/global/health`') {
        Write-OK "Plugin uses direct /global/health check"
    } elseif ($mainContent -match 'getUrl\(\)\}/global/health') {
        Write-WARN "Plugin appears to use the older project-scoped health check"
    } else {
        Write-WARN "Could not identify plugin health check implementation"
    }
} else {
    Write-WARN "Plugin main.js not found"
}

Write-Section "Recommended Command"
if ($NODE_BIN -and $OPENCODE_BIN) {
    Write-Host "$($NODE_BIN.Source) $($OPENCODE_BIN.Source) serve --port $Port --hostname $Host --cors app://obsidian.md"
} else {
    Write-WARN "Cannot build the recommended command because node/opencode is missing"
}

Write-Section "Recent Logs"
if (Test-Path $LOG_DIR) {
    $latestLog = Get-ChildItem -Path $LOG_DIR -File -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if ($latestLog) {
        Write-OK "Latest log: $($latestLog.FullName)"
        Get-Content $latestLog.FullName | Select-Object -First 40
    } else {
        Write-WARN "No log files found"
    }
} else {
    Write-WARN "Log directory not found: $LOG_DIR"
}

if ($StartTest) {
    Write-Section "Start Test"
    if (-not $NODE_BIN -or -not $OPENCODE_BIN) {
        Write-ERR "node or opencode is missing"
        exit 1
    }
    & $NODE_BIN.Source $OPENCODE_BIN.Source serve --port $Port --hostname $Host --cors "app://obsidian.md"
}

Write-Section "Done"
Write-Host "If the health endpoint is healthy but Obsidian still shows Error,"
Write-Host "reload the plugin or restart Obsidian, then re-check the plugin main.js health check."
