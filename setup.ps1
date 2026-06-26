# ============================================================
# AI 知识库一键部署脚本
# 适用于 Windows | 面向非技术用户
# ============================================================
$ErrorActionPreference = "Stop"

# 颜色定义 (使用 Write-Host 的 -ForegroundColor)
function Write-Red { param($msg) Write-Host $msg -ForegroundColor Red }
function Write-Green { param($msg) Write-Host $msg -ForegroundColor Green }
function Write-Yellow { param($msg) Write-Host $msg -ForegroundColor Yellow }
function Write-Blue { param($msg) Write-Host $msg -ForegroundColor Blue }
function Write-Cyan { param($msg) Write-Host $msg -ForegroundColor Cyan }

# 获取脚本所在目录
$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $SCRIPT_DIR) {
    $SCRIPT_DIR = $PSScriptRoot
}
$TEMPLATE_DIR = Join-Path $SCRIPT_DIR "vault-template"

Write-Host ""
Write-Cyan "╔══════════════════════════════════════════╗"
Write-Cyan "║    AI 知识库 · 一键部署                   ║"
Write-Cyan "║    Obsidian + OpenCode + 知识库规则        ║"
Write-Cyan "╚══════════════════════════════════════════╝"
Write-Host ""

# ----------------------------------------------------------
# 第 1 步：确认目标路径
# ----------------------------------------------------------
Write-Yellow "【第 1 步 / 共 6 步】选择知识库存放位置"
Write-Host ""
Write-Host "你的知识库（Vault）要放在哪里？"
Write-Host "直接回车 = 桌面上的「我的知识库」文件夹"
$VAULT_PATH = Read-Host "> 请输入路径（或直接回车）"

if ([string]::IsNullOrWhiteSpace($VAULT_PATH)) {
    $VAULT_PATH = Join-Path $env:USERPROFILE "Desktop\我的知识库"
}

if (Test-Path $VAULT_PATH) {
    Write-Red "⚠ 目录已存在：$VAULT_PATH"
    $OVERWRITE = Read-Host "  要覆盖吗？(y/N)"
    if ($OVERWRITE -ne "y" -and $OVERWRITE -ne "Y") {
        Write-Host "已取消。"
        exit 0
    }
    Remove-Item -Recurse -Force $VAULT_PATH
}

Write-Green "✓ 知识库将创建在：$VAULT_PATH"
Write-Host ""

# ----------------------------------------------------------
# 第 2 步：检查 Node.js
# ----------------------------------------------------------
Write-Yellow "【第 2 步 / 共 6 步】检查 Node.js"

$nodeCmd = Get-Command node -ErrorAction SilentlyContinue
if ($nodeCmd) {
    $NODE_VERSION = node --version
    Write-Green "✓ 已安装 Node.js $NODE_VERSION"
} else {
    Write-Red "✗ 未检测到 Node.js"
    Write-Host ""
    Write-Host "Node.js 是 OpenCode 运行的基础，需要先安装。"
    Write-Host ""
    Write-Host "请选择安装方式："
    Write-Host "  1) 自动安装（使用 Chocolatey，推荐）"
    Write-Host "  2) 手动下载（打开 Node.js 官网下载页）"
    Write-Host "  3) 跳过（我稍后自己装）"
    $NODE_CHOICE = Read-Host "> 请选择 (1/2/3)"

    switch ($NODE_CHOICE) {
        "1" {
            # 检查 Chocolatey
            $chocoCmd = Get-Command choco -ErrorAction SilentlyContinue
            if (-not $chocoCmd) {
                Write-Host "正在安装 Chocolatey..."
                Set-ExecutionPolicy Bypass -Scope Process -Force
                [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
                Invoke-Expression ((New-Object System.Net.WebClient).DownloadString('https://chocolatey.org/install.ps1'))
            }
            Write-Host "正在通过 Chocolatey 安装 Node.js..."
            choco install nodejs -y
            # 刷新环境变量
            $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
            Write-Green "✓ Node.js 安装完成"
        }
        "2" {
            Write-Host "正在打开 Node.js 下载页..."
            Start-Process "https://nodejs.org/zh-cn"
            Write-Host ""
            Write-Yellow "请下载并安装 Node.js（LTS 版本）后，重新运行此脚本。"
            exit 0
        }
        "3" {
            Write-Yellow "跳过。请稍后自行安装 Node.js，否则 OpenCode 无法运行。"
        }
        default {
            Write-Host "无效选择，退出。"
            exit 1
        }
    }
}
Write-Host ""

# 刷新环境变量确保 node 可用
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")

# ----------------------------------------------------------
# 第 3 步：安装 OpenCode
# ----------------------------------------------------------
Write-Yellow "【第 3 步 / 共 6 步】安装 OpenCode"

Write-Host "正在安装或更新 OpenCode..."
npm install -g opencode-ai 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "尝试使用管理员权限安装..."
    Start-Process powershell -Verb RunAs -ArgumentList "-Command", "npm install -g opencode-ai" -Wait
}

$opencodeCmd = Get-Command opencode -ErrorAction SilentlyContinue
if (-not $opencodeCmd) {
    Write-Red "✗ OpenCode 安装完成后仍未找到 opencode 命令"
    Write-Host "请确认 npm 全局 bin 已加入 PATH，然后重新运行脚本。"
    Write-Host "或手动运行：npm install -g opencode-ai"
    exit 1
}

$OPENCODE_VERSION = opencode --version 2>$null
Write-Green "✓ OpenCode 已就绪：$(($opencodeCmd).Source) $OPENCODE_VERSION"
Write-Host ""

# ----------------------------------------------------------
# 第 4 步：安装 OpenCLI
# ----------------------------------------------------------
Write-Yellow "【第 4 步 / 共 6 步】安装 OpenCLI"

Write-Host "正在安装 OpenCLI..."
npm install -g @jackwener/opencli 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "尝试使用管理员权限安装..."
    Start-Process powershell -Verb RunAs -ArgumentList "-Command", "npm install -g @jackwener/opencli" -Wait
}

$opencliCmd = Get-Command opencli -ErrorAction SilentlyContinue
if ($opencliCmd) {
    $OPENCLI_VERSION = opencli --version 2>$null
    Write-Green "✓ OpenCLI 已就绪：$(($opencliCmd).Source) $OPENCLI_VERSION"
} else {
    Write-Yellow "⚠ OpenCLI 安装未成功，社交媒体采集功能需要手动安装"
    Write-Host "  手动安装命令：npm install -g @jackwener/opencli"
}
Write-Host ""

# ----------------------------------------------------------
# 第 5 步：创建 Vault（从模板复制）
# ----------------------------------------------------------
Write-Yellow "【第 5 步 / 共 6 步】创建知识库"

# 复制模板
Write-Host "正在复制知识库模板..."
Copy-Item -Recurse -Path $TEMPLATE_DIR -Destination $VAULT_PATH

# 清理 .gitkeep
Get-ChildItem -Path $VAULT_PATH -Recurse -Filter ".gitkeep" | Remove-Item -Force

Write-Green "✓ 知识库已创建"
Write-Host ""

# ----------------------------------------------------------
# 第 6 步：配置 AI 服务
# ----------------------------------------------------------
Write-Yellow "【第 6 步 / 共 6 步】配置 AI 服务"
Write-Host ""
Write-Host "知识库需要一个 AI 大模型来驱动。请选择你的 AI 服务提供商："
Write-Host ""
Write-Host "  1) 智谱 GLM    — 国内服务，中文友好，注册简单（推荐国内用户）"
Write-Host "  2) Anthropic   — Claude 系列模型"
Write-Host "  3) OpenAI      — GPT 系列模型"
Write-Host "  4) Google      — Gemini 系列模型"
Write-Host "  5) OpenRouter  — 多模型网关，一个 Key 用多个模型"
Write-Host "  6) DeepSeek    — DeepSeek 模型（国内服务）"
Write-Host "  7) 跳过        — 稍后手动配置"
Write-Host ""
$PROVIDER_CHOICE = Read-Host "> 请选择 (1-7)"

# 创建 OpenCode 全局配置目录
$OPENCODE_CONFIG_DIR = Join-Path $env:APPDATA "opencode"
if (-not (Test-Path $OPENCODE_CONFIG_DIR)) {
    New-Item -ItemType Directory -Path $OPENCODE_CONFIG_DIR -Force | Out-Null
}

$CONFIG_FILE = Join-Path $OPENCODE_CONFIG_DIR "opencode.json"
$MODEL_ID = ""
$PROVIDER_BLOCK = ""

switch ($PROVIDER_CHOICE) {
    "1" {
        # 智谱 GLM
        Write-Host ""
        Write-Host "请先获取 API Key："
        Write-Host "  1. 访问 https://open.bigmodel.cn"
        Write-Host "  2. 注册账号 →「API Keys」→ 创建 Key"
        Write-Host ""
        $API_KEY = Read-Host "> 请粘贴你的 API Key"
        if ([string]::IsNullOrWhiteSpace($API_KEY)) {
            Write-Yellow "跳过。"
            $PROVIDER_CHOICE = "7"
        } else {
            $MODEL_ID = "zhipuglm/glm-4.5"
            $PROVIDER_BLOCK = @"
"zhipuglm": {
      "name": "智谱 GLM",
      "npm": "@ai-sdk/openai-compatible",
      "models": {
        "glm-4.5": { "name": "GLM-4.5" },
        "glm-4.5-air": { "name": "GLM-4.5-Air" }
      },
      "options": {
        "apiKey": "${API_KEY}",
        "baseURL": "https://open.bigmodel.cn/api/coding/paas/v4"
      }
    }
"@
        }
    }
    "2" {
        # Anthropic
        Write-Host ""
        Write-Host "请先获取 API Key：https://console.anthropic.com/settings/keys"
        Write-Host ""
        $API_KEY = Read-Host "> 请粘贴你的 API Key"
        if ([string]::IsNullOrWhiteSpace($API_KEY)) {
            Write-Yellow "跳过。"
            $PROVIDER_CHOICE = "7"
        } else {
            $MODEL_ID = "anthropic/claude-sonnet-4-20250514"
            $PROVIDER_BLOCK = @"
"anthropic": {
      "models": {
        "claude-sonnet-4-20250514": { "name": "Claude Sonnet 4" },
        "claude-haiku-35-20241022": { "name": "Claude 3.5 Haiku" }
      },
      "options": {
        "apiKey": "${API_KEY}"
      }
    }
"@
        }
    }
    "3" {
        # OpenAI
        Write-Host ""
        Write-Host "请先获取 API Key：https://platform.openai.com/api-keys"
        Write-Host ""
        $API_KEY = Read-Host "> 请粘贴你的 API Key"
        if ([string]::IsNullOrWhiteSpace($API_KEY)) {
            Write-Yellow "跳过。"
            $PROVIDER_CHOICE = "7"
        } else {
            $MODEL_ID = "openai/gpt-4.1"
            $PROVIDER_BLOCK = @"
"openai": {
      "models": {
        "gpt-4.1": { "name": "GPT-4.1" },
        "gpt-4.1-mini": { "name": "GPT-4.1 Mini" },
        "gpt-4.1-nano": { "name": "GPT-4.1 Nano" }
      },
      "options": {
        "apiKey": "${API_KEY}"
      }
    }
"@
        }
    }
    "4" {
        # Google Gemini
        Write-Host ""
        Write-Host "请先获取 API Key：https://aistudio.google.com/apikey"
        Write-Host ""
        $API_KEY = Read-Host "> 请粘贴你的 API Key"
        if ([string]::IsNullOrWhiteSpace($API_KEY)) {
            Write-Yellow "跳过。"
            $PROVIDER_CHOICE = "7"
        } else {
            $MODEL_ID = "google/gemini-2.5-pro"
            $PROVIDER_BLOCK = @"
"google": {
      "models": {
        "gemini-2.5-pro": { "name": "Gemini 2.5 Pro" },
        "gemini-2.5-flash": { "name": "Gemini 2.5 Flash" }
      },
      "options": {
        "apiKey": "${API_KEY}"
      }
    }
"@
        }
    }
    "5" {
        # OpenRouter
        Write-Host ""
        Write-Host "请先获取 API Key：https://openrouter.ai/settings/keys"
        Write-Host ""
        $API_KEY = Read-Host "> 请粘贴你的 API Key"
        if ([string]::IsNullOrWhiteSpace($API_KEY)) {
            Write-Yellow "跳过。"
            $PROVIDER_CHOICE = "7"
        } else {
            $MODEL_ID = "openrouter/anthropic/claude-sonnet-4-20250514"
            $PROVIDER_BLOCK = @"
"openrouter": {
      "models": {
        "anthropic/claude-sonnet-4-20250514": { "name": "Claude Sonnet 4" },
        "openai/gpt-4.1": { "name": "GPT-4.1" },
        "google/gemini-2.5-pro": { "name": "Gemini 2.5 Pro" }
      },
      "options": {
        "apiKey": "${API_KEY}"
      }
    }
"@
        }
    }
    "6" {
        # DeepSeek
        Write-Host ""
        Write-Host "请先获取 API Key：https://platform.deepseek.com/api_keys"
        Write-Host ""
        $API_KEY = Read-Host "> 请粘贴你的 API Key"
        if ([string]::IsNullOrWhiteSpace($API_KEY)) {
            Write-Yellow "跳过。"
            $PROVIDER_CHOICE = "7"
        } else {
            $MODEL_ID = "deepseek/deepseek-chat"
            $PROVIDER_BLOCK = @"
"deepseek": {
      "name": "DeepSeek",
      "npm": "@ai-sdk/openai-compatible",
      "models": {
        "deepseek-chat": { "name": "DeepSeek V3" },
        "deepseek-reasoner": { "name": "DeepSeek R1" }
      },
      "options": {
        "apiKey": "${API_KEY}",
        "baseURL": "https://api.deepseek.com/v1"
      }
    }
"@
        }
    }
    default {
        Write-Yellow "跳过 AI 服务配置。稍后请手动编辑 $OPENCODE_CONFIG_DIR\opencode.json"
        $PROVIDER_CHOICE = "7"
    }
}

# 写入配置文件
if ($PROVIDER_CHOICE -ne "7" -and -not [string]::IsNullOrWhiteSpace($PROVIDER_BLOCK)) {
    $CONFIG_CONTENT = @"
{
  "`$schema": "https://opencode.ai/config.json",
  "agent": {
    "build": { "options": { "store": false } },
    "plan": { "options": { "store": false } }
  },
  "model": "${MODEL_ID}",
  "provider": {
    ${PROVIDER_BLOCK}
  }
}
"@
    Set-Content -Path $CONFIG_FILE -Value $CONFIG_CONTENT -Encoding UTF8
    Write-Green "✓ AI 服务配置完成"
}
Write-Host ""

# ----------------------------------------------------------
# 配置 opencode-obsidian 插件
# ----------------------------------------------------------
if ($opencodeCmd) {
    # 确保 Obsidian 插件目录存在
    $PLUGIN_DIR = Join-Path $VAULT_PATH ".obsidian\plugins\opencode-obsidian"
    if (-not (Test-Path $PLUGIN_DIR)) {
        New-Item -ItemType Directory -Path $PLUGIN_DIR -Force | Out-Null
    }

    # 获取 node 和 opencode 路径
    $NODE_PATH = (Get-Command node).Source
    $OPENCODE_PATH = (Get-Command opencode).Source

    $DATA_JSON = @"
{
  "port": 14096,
  "hostname": "127.0.0.1",
  "autoStart": true,
  "opencodePath": "$OPENCODE_PATH",
  "startupTimeout": 45000,
  "defaultViewLocation": "sidebar",
  "injectWorkspaceContext": false,
  "maxNotesInContext": 20,
  "maxSelectionLength": 2000,
  "customCommand": "$NODE_PATH $OPENCODE_PATH serve --port 14096 --hostname 127.0.0.1 --cors app://obsidian.md",
  "useCustomCommand": true
}
"@
    Set-Content -Path (Join-Path $PLUGIN_DIR "data.json") -Value $DATA_JSON -Encoding UTF8

    Write-Green "✓ 插件配置已生成"
}

# ----------------------------------------------------------
# 完成
# ----------------------------------------------------------
Write-Host ""
Write-Green "╔══════════════════════════════════════════╗"
Write-Green "║          🎉 部署完成！                    ║"
Write-Green "╚══════════════════════════════════════════╝"
Write-Host ""
Write-Host "知识库位置：$VAULT_PATH"
Write-Host ""
Write-Yellow "接下来你需要做 3 件事："
Write-Host ""
Write-Host "  1. 打开 Obsidian → 「打开文件夹作为仓库」→ 选择："
Write-Host "     $VAULT_PATH"
Write-Host ""
Write-Host "  2. 安装 opencode-obsidian 插件："
Write-Host "     推荐方式：在 Obsidian 设置 → 第三方插件 → 浏览 → 搜索「BRAT」"
Write-Host "              → 安装并启用 BRAT → 打开 BRAT 设置 → Add Plugin → 输入：mtymek/opencode-obsidian"
Write-Host ""
Write-Host "  3. 启用插件后，侧边栏会出现 OpenCode 面板"
Write-Host "     点击开始对话，试试说：「帮我创建一篇笔记」"
Write-Host ""
Write-Blue "💡 自定义提示：编辑 $VAULT_PATH\AI_CONFIG.md 可以修改 AI 行为"
Write-Host "   例如：添加知识域、修改触发词、调整输出语言等"
Write-Host ""
Write-Host "详细说明请参考同目录下的 部署指南.md"
Write-Host ""

# 询问是否打开知识库位置
$OPEN_VAULT = Read-Host "是否立即打开知识库文件夹？(y/N)"
if ($OPEN_VAULT -eq "y" -or $OPEN_VAULT -eq "Y") {
    explorer.exe $VAULT_PATH
}
