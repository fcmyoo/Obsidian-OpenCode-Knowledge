---
title: AI Knowledge Base Deployment Guide
date: 2026-04-13
tags:
  - deployment
  - guide
  - knowledge-base
---

# AI Knowledge Base Deployment Guide

> For non-technical users. Follow the steps in order; it takes about 20 minutes.

---

## What this setup includes

A **local AI knowledge base** with three components:

| Component | What it is | What you need to do |
|---|---|---|
| **Obsidian** | Note-taking app | Download and install |
| **OpenCode** | AI assistant (runs in terminal) | Run the setup script |
| **Knowledge rules** | Tell AI how to manage notes | Configured automatically by the script |

**After installation you can:**
- Say "organize this article" to AI, and it will save into your knowledge base automatically
- Ask "have I written about XX before", and AI will search for you
- Drop PDFs, web pages, and screenshots to AI, and it will digest them into structured notes

---

## Prerequisites

Before starting, make sure you have:

| Requirement | Description | How to check |
|---|---|---|
| A Mac computer | macOS 12 or later | Click the Apple menu  → "About This Mac" |
| Internet access | Needed to download software and connect to AI | Open any website |
| 10 minutes | One-time setup | — |

---

## Installation steps

### Step 1: Install Obsidian

1. Open your browser and go to [obsidian.md](https://obsidian.md)
2. Click **"Download"** (choose the macOS version)
3. After downloading, drag Obsidian into the "Applications" folder
4. Open Obsidian and wait for the welcome screen (**do not create a vault yet**)

> If you already have Obsidian installed, skip this step.

---

### Step 2: Get an AI API key

The knowledge base needs an AI brain. The script supports these AI services (choose one):

| Service | Sign-up page | Notes |
|---|---|---|
| **Zhipu GLM** ⭐ | [open.bigmodel.cn](https://open.bigmodel.cn) | China-based service, good Chinese support, recommended for CN users |
| Anthropic | [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys) | Claude models |
| OpenAI | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) | GPT models |
| Google Gemini | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) | Gemini models |
| OpenRouter | [openrouter.ai/settings/keys](https://openrouter.ai/settings/keys) | Multi-model gateway |
| DeepSeek | [platform.deepseek.com/api_keys](https://platform.deepseek.com/api_keys) | China-based service, cost-effective |

Using Zhipu GLM as an example:

1. Open your browser and go to [open.bigmodel.cn](https://open.bigmodel.cn)
2. Click **"Sign up"** and register with your phone number
3. After logging in, click **"API Keys"** on the left
4. Click **"Create API Key"**
5. **Copy the generated key** (format looks like `xxxxx.xxxxx`) and save it in Notes

> ⚠️ This key is shown only once. Keep it safe.

---

### Step 3: Run the setup script

1. Open **Terminal** (find it in "Launchpad" → "Other", or press `⌘ Space` and search "Terminal")

2. Clone or unzip this repository, then enter the repo root before running setup:

```bash
git clone https://github.com/fcmyoo/Obsidian-OpenCode-Knowledge.git
cd Obsidian-OpenCode-Knowledge
bash setup.sh
```

3. Follow the script prompts:
   - **Choose vault location**: press Enter to use Desktop
   - **Install Node.js**: if missing, choose option 1 to install automatically
   - **Install OpenCode**: proceed automatically
   - **Choose AI provider**: enter the number for your AI provider (1-6), then paste the API Key

5. When you see **🎉 Deployment complete!**, the setup succeeded

---

### Step 4: Open the knowledge base in Obsidian

1. Open Obsidian
2. Click **"Open folder as vault"**
3. Select the folder created by the script (default is "我的知识库" on Desktop)
4. Click "Open"

---

### Step 5: Install the OpenCode plugin

This is the bridge that lets AI work inside Obsidian.

#### Install via BRAT

1. In Obsidian, go to Settings → Community plugins → Browse, search for **"BRAT"**, install and enable it
2. Press `⌘ P` to open the command palette, then run **"BRAT: Add a plugin"**
3. Paste the repository address: `mtymek/opencode-obsidian`
4. Install and enable it

---

### Step 6: Start using it

1. In Obsidian, find the **OpenCode icon** in the left sidebar (a terminal icon)
2. Click to open the OpenCode panel
3. Wait for AI to connect (may take 30 seconds the first time)
4. Try saying your first command to AI:

```
Create a note in Obsidian titled 《My First AI Note》
```

---

## Plugin checklist and troubleshooting

If you want to double-check the `opencode-obsidian` plugin configuration, or if the panel shows `Error` / `Connection failed`, see this guide first:

- [`opencode-obsidian-setup-troubleshooting.md`](opencode-obsidian-setup-troubleshooting.md)

The repo also includes a quick diagnostic script:

```bash
bash scripts/opencode-obsidian-doctor.sh --vault "$HOME/Desktop/我的知识库"
```

It will check:

- Whether `node` and `opencode` are installed correctly
- Whether port `14096` is occupied by an old process
- Whether `http://127.0.0.1:14096/global/health` is responding
- Whether the plugin `data.json` exists
- Whether recent `opencode` logs show obvious errors

---

## Daily usage

### Ingest

```
Add this to the wiki:

[paste article content / paste a link / describe what you want to save]
```

AI will automatically:
- save raw素材 to `raw/`
- digest into structured notes in `wiki/`
- update the index and log

### Query

```
What do I have in my wiki about XX?
```

```
Based on my notes, summarize my thoughts on XX
```

### Lint

Once a week:

```
lint wiki
```

AI will check index consistency, link validity, orphaned pages, and so on.

---

## FAQ

### Q1: OpenCode panel shows "Connection failed"

1. Make sure your Mac is online
2. Make sure your API Key is configured correctly (check `~/.config/opencode/opencode.json`)
3. Test manually in Terminal: run `opencode` and see if it starts normally

### Q2: AI replies are slow

- It may be a network issue; wait a moment
- Zhipu GLM's `glm-4.5-air` model is faster (but slightly lower quality); you can switch in config

### Q3: I want to switch AI providers

Edit the config file:

```bash
open ~/.config/opencode/opencode.json
```

Follow the [OpenCode docs](https://opencode.ai) to update the `provider` section.

### Q4: Is my data safe?

- **All data stays on your computer** and is not uploaded unless you configured sync yourself
- Files in `raw/` will **never be modified by AI**
- Obsidian notes are plain Markdown files; you can copy and back them up anytime

### Q5: The script fails during setup

Take a screenshot of the Terminal error and send it to the person who helped you deploy.

### Q6: OpenCode panel shows `Error` or `Process exited unexpectedly (exit code 1)`

Troubleshoot in this order:

1. Run:

```bash
bash scripts/opencode-obsidian-doctor.sh --vault "$HOME/Desktop/我的知识库"
```

2. If you see a port-conflict message, run:

```bash
bash scripts/opencode-obsidian-doctor.sh --vault "$HOME/Desktop/我的知识库" --kill-port
```

3. If you want to manually verify the service can start, run:

```bash
bash scripts/opencode-obsidian-doctor.sh --vault "$HOME/Desktop/我的知识库" --start-test
```

4. If it still doesn't work, continue with:
- [`opencode-obsidian-setup-troubleshooting.md`](opencode-obsidian-setup-troubleshooting.md)

---

## File overview

After deployment, your knowledge base will look like this:

```
我的知识库/
├── AGENTS.md               # AI rules (do not edit manually)
├── AI_CONFIG.md            # ⚙️ AI config (customizable, auto-applies)
├── raw/                   # Raw素材 (what you drop in)
├── wiki/                  # AI-organized notes
│   ├── index.md           # Global index (maintained by AI)
│   ├── log.md             # Operation log (maintained by AI)
│   └── 使用指南.md         # Usage guide
├── assets/                # Images and media
└── .opencode/
    └── skill/             # AI skills (9 core skills preinstalled)
        ├── obsidian-cli/  # Obsidian operations
        ├── obsidian-markdown/  # Markdown generation
        ├── defuddle/      # Web content extraction
        ├── opencli-usage/ # OpenCLI command reference (87+ adapters)
        ├── smart-search/  # Smart search routing
        ├── opencli-browser/  # Browser automation
        ├── opencli-autofix/  # Adapter auto-repair
        ├── opencli-explorer/ # Adapter development guide
        └── opencli-oneshot/  # Quick CLI generation
```

For optional workflow and quality improvements after deployment, see:
[`docs/knowledge-workflow.md`](docs/knowledge-workflow.md),
[`docs/knowledge-maintenance.md`](docs/knowledge-maintenance.md),
[`docs/quality-metrics.md`](docs/quality-metrics.md),
[`docs/git-policy.md`](docs/git-policy.md),
[`docs/plugin-recommendations.md`](docs/plugin-recommendations.md),
[`docs/privacy-and-security.md`](docs/privacy-and-security.md).

---

## Advanced: optional enhancements

The base setup is already usable. Add these if you want more power:

| Feature | How to add | Description |
|---|---|---|
| PDF export | Tell OpenCode: "install minimax-pdf skill" | Export notes as polished PDFs |
| Word export | Tell OpenCode: "install minimax-docx skill" | Generate Word documents |
| Excel reading | Tell OpenCode: "install minimax-xlsx skill" | Read Excel data |
| PPT generation | Tell OpenCode: "install pptx-generator skill" | Turn notes into presentations |
| Image analysis | Tell OpenCode: "install vision-analysis skill" | Analyze screenshots and images |

---

## Acknowledgments

This knowledge-base architecture was inspired by [helloianneo/obsidian-ai-second-brain](https://github.com/helloianneo/obsidian-ai-second-brain) (Ian's Obsidian + Claude AI personal knowledge base guide, based on the [Karpathy LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) methodology). We replaced the AI runtime with [OpenCode](https://opencode.ai), and simplified plus localized the deployment flow.

---

*Last updated: 2026-04-14*
