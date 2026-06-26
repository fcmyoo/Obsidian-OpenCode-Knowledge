#!/usr/bin/env bash
# ============================================================
# Knowledge Base Installer
# Supports non-interactive automation and custom vault paths.
# ============================================================
set -euo pipefail

VAULT_PATH=""
PROVIDER=""
API_KEY=""
SKIP_PLUGIN=false
DRY_RUN=false

usage() {
  cat <<EOF
Usage: $(basename "$0") [options]

Options:
  --vault <path>        Vault destination path
  --provider <name>     Provider: zhipuglm|anthropic|openai|google|openrouter|deepseek
  --api-key <key>       API key for the selected provider
  --skip-plugin         Skip plugin config generation
  --dry-run             Print actions without changing files
  -h, --help            Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --vault)
      VAULT_PATH="$2"; shift 2 ;;
    --provider)
      PROVIDER="$2"; shift 2 ;;
    --api-key)
      API_KEY="$2"; shift 2 ;;
    --skip-plugin)
      SKIP_PLUGIN=true; shift ;;
    --dry-run)
      DRY_RUN=true; shift ;;
    -h|--help)
      usage; exit 0 ;;
    *)
      echo "Unknown option: $1" >&2; usage; exit 1 ;;
  esac
done

if [[ -z "${VAULT_PATH:-}" ]]; then
  echo "Error: --vault is required" >&2
  usage
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TEMPLATE_DIR="$REPO_ROOT/vault-template"
OPENCODE_CONFIG_DIR="${OPENCODE_CONFIG_DIR:-$HOME/.config/opencode}"
CONFIG_FILE="$OPENCODE_CONFIG_DIR/opencode.json"

info() { echo "[installer] $*"; }
warn() { echo "[installer][warn] $*" >&2; }

run() {
  if [[ "$DRY_RUN" == true ]]; then
    info "(dry-run) $*"
  else
    info "$*"
    eval "$@"
  fi
}

# 1. Create vault
run mkdir -p "$(dirname "$VAULT_PATH")"
if [[ -d "$VAULT_PATH" ]]; then
  run rm -rf "$VAULT_PATH"
fi
run cp -R "$TEMPLATE_DIR" "$VAULT_PATH"
run find "$VAULT_PATH" -name ".gitkeep" -delete
info "Created vault at $VAULT_PATH"

# 2. Install OpenCode if missing
if ! command -v opencode >/dev/null 2>&1; then
  run npm install -g opencode-ai
fi
info "OpenCode: $(command -v opencode || echo missing)"

# 3. Install OpenCLI if missing
if ! command -v opencli >/dev/null 2>&1; then
  run npm install -g @jackwener/opencli || true
fi
info "OpenCLI: $(command -v opencli || echo missing)"

# 4. Provider config
MODEL_ID=""
PROVIDER_BLOCK=""

case "$PROVIDER" in
  zhipuglm)
    MODEL_ID="zhipuglm/glm-4.5"
    PROVIDER_BLOCK="\"zhipuglm\": {\n      \"name\": \"智谱 GLM\",\n      \"npm\": \"@ai-sdk/openai-compatible\",\n      \"models\": { \"glm-4.5\": { \"name\": \"GLM-4.5\" }, \"glm-4.5-air\": { \"name\": \"GLM-4.5-Air\" } },\n      \"options\": { \"apiKey\": \"${API_KEY}\", \"baseURL\": \"https://open.bigmodel.cn/api/coding/paas/v4\" }\n    }"
    ;;
  anthropic)
    MODEL_ID="anthropic/claude-sonnet-4-20250514"
    PROVIDER_BLOCK="\"anthropic\": {\n      \"models\": { \"claude-sonnet-4-20250514\": { \"name\": \"Claude Sonnet 4\" }, \"claude-haiku-35-20241022\": { \"name\": \"Claude 3.5 Haiku\" } },\n      \"options\": { \"apiKey\": \"${API_KEY}\" }\n    }"
    ;;
  openai)
    MODEL_ID="openai/gpt-4.1"
    PROVIDER_BLOCK="\"openai\": {\n      \"models\": { \"gpt-4.1\": { \"name\": \"GPT-4.1\" }, \"gpt-4.1-mini\": { \"name\": \"GPT-4.1 Mini\" } },\n      \"options\": { \"apiKey\": \"${API_KEY}\" }\n    }"
    ;;
  google)
    MODEL_ID="google/gemini-2.5-pro"
    PROVIDER_BLOCK="\"google\": {\n      \"models\": { \"gemini-2.5-pro\": { \"name\": \"Gemini 2.5 Pro\" }, \"gemini-2.5-flash\": { \"name\": \"Gemini 2.5 Flash\" } },\n      \"options\": { \"apiKey\": \"${API_KEY}\" }\n    }"
    ;;
  openrouter)
    MODEL_ID="openrouter/anthropic/claude-sonnet-4-20250514"
    PROVIDER_BLOCK="\"openrouter\": {\n      \"models\": { \"anthropic/claude-sonnet-4-20250514\": { \"name\": \"Claude Sonnet 4\" }, \"openai/gpt-4.1\": { \"name\": \"GPT-4.1\" } },\n      \"options\": { \"apiKey\": \"${API_KEY}\" }\n    }"
    ;;
  deepseek)
    MODEL_ID="deepseek/deepseek-chat"
    PROVIDER_BLOCK="\"deepseek\": {\n      \"name\": \"DeepSeek\",\n      \"npm\": \"@ai-sdk/openai-compatible\",\n      \"models\": { \"deepseek-chat\": { \"name\": \"DeepSeek V3\" }, \"deepseek-reasoner\": { \"name\": \"DeepSeek R1\" } },\n      \"options\": { \"apiKey\": \"${API_KEY}\", \"baseURL\": \"https://api.deepseek.com/v1\" }\n    }"
    ;;
  "")
    warn "No provider specified; skipping OpenCode config."
    ;;
  *)
    warn "Unknown provider: $PROVIDER";;
esac

if [[ -n "$PROVIDER_BLOCK" ]]; then
  run mkdir -p "$OPENCODE_CONFIG_DIR"
  if [[ "$DRY_RUN" != true ]]; then
    cat > "$CONFIG_FILE" <<EOF
{
  "model": "$MODEL_ID",
  "provider": {
    $PROVIDER_BLOCK
  }
}
EOF
  else
    info "(dry-run) Would write $CONFIG_FILE"
  fi
fi

# 5. Plugin config
if [[ "$SKIP_PLUGIN" != true ]]; then
  OPENCODE_PATH="$(command -v opencode || true)"
  NODE_PATH="$(command -v node || true)"
  if [[ -n "$OPENCODE_PATH" && -n "$NODE_PATH" ]]; then
    PLUGIN_DIR="$VAULT_PATH/.obsidian/plugins/opencode-obsidian"
    run mkdir -p "$PLUGIN_DIR"
    if [[ "$DRY_RUN" != true ]]; then
      cat > "$PLUGIN_DIR/data.json" <<EOF
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
EOF
    else
      info "(dry-run) Would write $PLUGIN_DIR/data.json"
    fi
  else
    warn "Skipping plugin config: opencode or node not found."
  fi
fi

info "Done."
