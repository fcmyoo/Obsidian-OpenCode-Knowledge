# ============================================================
# Knowledge Base Installer (Windows)
# Supports non-interactive automation and custom vault paths.
# ============================================================
param(
    [Parameter(Mandatory=$true)]
    [string]$Vault,
    [ValidateSet("zhipuglm","anthropic","openai","google","openrouter","deepseek","")]
    [string]$Provider = "",
    [string]$ApiKey = "",
    [switch]$SkipPlugin,
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

function Write-Info { param($msg) Write-Host "[installer] $msg" }
function Write-Warn { param($msg) Write-Host "[installer][warn] $msg" -ForegroundColor Yellow }

function Invoke-Run {
    param([string]$Command)
    if ($DryRun) {
        Write-Info "(dry-run) $Command"
    } else {
        Write-Info $Command
        Invoke-Expression $Command
    }
}

$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$REPO_ROOT = Split-Path -Parent $SCRIPT_DIR
if (-not (Test-Path (Join-Path $REPO_ROOT "vault-template"))) {
    $REPO_ROOT = Split-Path -Parent $REPO_ROOT
}
$TEMPLATE_DIR = Join-Path $REPO_ROOT "vault-template"
if ($env:APPDATA) {
    $OPENCODE_CONFIG_DIR = Join-Path $env:APPDATA "opencode"
} else {
    $OPENCODE_CONFIG_DIR = Join-Path $env:USERPROFILE ".config\opencode"
}
$CONFIG_FILE = Join-Path $OPENCODE_CONFIG_DIR "opencode.json"

# 1. Vault
$vaultParent = Split-Path -Parent $Vault
if ($vaultParent) { Invoke-Run -Command "New-Item -ItemType Directory -Path '$vaultParent' -Force | Out-Null" }
if (Test-Path $Vault) { Invoke-Run -Command "Remove-Item -Recurse -Force '$Vault'" }
Invoke-Run -Command "Copy-Item -Recurse -Path '$TEMPLATE_DIR' -Destination '$Vault'"
Invoke-Run -Command "Get-ChildItem -Path '$Vault' -Recurse -Filter '.gitkeep' | Remove-Item -Force"
Write-Info "Created vault at $Vault"

# 2. OpenCode
$opencodeCmd = Get-Command opencode -ErrorAction SilentlyContinue
if (-not $opencodeCmd) {
    Invoke-Run -Command "npm install -g opencode-ai"
}
Write-Info "OpenCode: $((Get-Command opencode -ErrorAction SilentlyContinue).Source)"

# 3. OpenCLI
$opencliCmd = Get-Command opencli -ErrorAction SilentlyContinue
if (-not $opencliCmd) {
    Invoke-Run -Command "npm install -g @jackwener/opencli" | Out-Null
}
Write-Info "OpenCLI: $((Get-Command opencli -ErrorAction SilentlyContinue).Source)"

# 4. Provider config
$modelId = ""
$providerBlock = ""

switch ($Provider) {
    "zhipuglm" {
        $modelId = "zhipuglm/glm-4.5"
        $providerBlock = @"
"zhipuglm": {
      "name": "智谱 GLM",
      "npm": "@ai-sdk/openai-compatible",
      "models": { "glm-4.5": { "name": "GLM-4.5" }, "glm-4.5-air": { "name": "GLM-4.5-Air" } },
      "options": { "apiKey": "$ApiKey", "baseURL": "https://open.bigmodel.cn/api/coding/paas/v4" }
    }
"@
    }
    "anthropic" {
        $modelId = "anthropic/claude-sonnet-4-20250514"
        $providerBlock = @"
"anthropic": {
      "models": { "claude-sonnet-4-20250514": { "name": "Claude Sonnet 4" }, "claude-haiku-35-20241022": { "name": "Claude 3.5 Haiku" } },
      "options": { "apiKey": "$ApiKey" }
    }
"@
    }
    "openai" {
        $modelId = "openai/gpt-4.1"
        $providerBlock = @"
"openai": {
      "models": { "gpt-4.1": { "name": "GPT-4.1" }, "gpt-4.1-mini": { "name": "GPT-4.1 Mini" } },
      "options": { "apiKey": "$ApiKey" }
    }
"@
    }
    "google" {
        $modelId = "google/gemini-2.5-pro"
        $providerBlock = @"
"google": {
      "models": { "gemini-2.5-pro": { "name": "Gemini 2.5 Pro" }, "gemini-2.5-flash": { "name": "Gemini 2.5 Flash" } },
      "options": { "apiKey": "$ApiKey" }
    }
"@
    }
    "openrouter" {
        $modelId = "openrouter/anthropic/claude-sonnet-4-20250514"
        $providerBlock = @"
"openrouter": {
      "models": { "anthropic/claude-sonnet-4-20250514": { "name": "Claude Sonnet 4" }, "openai/gpt-4.1": { "name": "GPT-4.1" } },
      "options": { "apiKey": "$ApiKey" }
    }
"@
    }
    "deepseek" {
        $modelId = "deepseek/deepseek-chat"
        $providerBlock = @"
"deepseek": {
      "name": "DeepSeek",
      "npm": "@ai-sdk/openai-compatible",
      "models": { "deepseek-chat": { "name": "DeepSeek V3" }, "deepseek-reasoner": { "name": "DeepSeek R1" } },
      "options": { "apiKey": "$ApiKey", "baseURL": "https://api.deepseek.com/v1" }
    }
"@
    }
}

if ($providerBlock) {
    Invoke-Run -Command "New-Item -ItemType Directory -Path '$OPENCODE_CONFIG_DIR' -Force | Out-Null"
    if (-not $DryRun) {
        $config = @"
{
  "model": "$modelId",
  "provider": {
    $providerBlock
  }
}
"@
        $config | Out-File -FilePath $CONFIG_FILE -Encoding utf8
    } else {
        Write-Info "(dry-run) Would write $CONFIG_FILE"
    }
} else {
    Write-Warn "No provider specified; skipping OpenCode config."
}

# 5. Plugin config
if (-not $SkipPlugin) {
    $opencodePath = (Get-Command opencode -ErrorAction SilentlyContinue).Source
    $nodePath = (Get-Command node -ErrorAction SilentlyContinue).Source
    if ($opencodePath -and $nodePath) {
        $pluginDir = Join-Path $Vault ".obsidian\plugins\opencode-obsidian"
        Invoke-Run -Command "New-Item -ItemType Directory -Path '$pluginDir' -Force | Out-Null"
        if (-not $DryRun) {
            $pluginConfig = @"
{
  "port": 14096,
  "hostname": "127.0.0.1",
  "autoStart": true,
  "opencodePath": "$opencodePath",
  "startupTimeout": 45000,
  "defaultViewLocation": "sidebar",
  "injectWorkspaceContext": false,
  "maxNotesInContext": 20,
  "maxSelectionLength": 2000,
  "customCommand": "$nodePath $opencodePath serve --port 14096 --hostname 127.0.0.1 --cors app://obsidian.md",
  "useCustomCommand": true
}
"@
            $pluginConfig | Out-File -FilePath (Join-Path $pluginDir "data.json") -Encoding utf8
        } else {
            Write-Info "(dry-run) Would write $(Join-Path $pluginDir 'data.json')"
        }
    } else {
        Write-Warn "Skipping plugin config: opencode or node not found."
    }
}

Write-Info "Done."
