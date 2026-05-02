# deploy-hermes-oci.ps1 — Install and configure hermes-agent on OCI VM alongside precosbot
# Usage: .\deploy-hermes-oci.ps1

$VM_IP = "137.131.159.91"
$SSH_KEY = "$env:USERPROFILE\.ssh\oci_yvy"
$SSH_OPTS = "-i $SSH_KEY -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"

function ssh_run {
    param([string]$cmd)
    ssh $SSH_OPTS.Split(" ") "ubuntu@$VM_IP" $cmd
    return $LASTEXITCODE
}

Write-Host "=== Deploying hermes-agent to OCI VM ($VM_IP) ===" -ForegroundColor Cyan

# ── Step 1: Test SSH connectivity ─────────────────────────────────────────────
Write-Host "`n1. Testing SSH connection..." -ForegroundColor Yellow
$result = ssh_run "echo OK"
if ($LASTEXITCODE -ne 0) {
    Write-Host "   SSH failed. Check SSH key at: $SSH_KEY" -ForegroundColor Red
    Write-Host "   See DEPLOYMENT.md for SSH setup instructions." -ForegroundColor Red
    exit 1
}
Write-Host "   SSH OK" -ForegroundColor Green

# ── Step 2: Check if hermes is already installed ──────────────────────────────
Write-Host "`n2. Checking hermes installation..." -ForegroundColor Yellow
$hermesCheck = ssh_run "which hermes 2>/dev/null && echo INSTALLED || echo MISSING"
Write-Host "   hermes: $hermesCheck"

# ── Step 3: Install hermes if needed ─────────────────────────────────────────
Write-Host "`n3. Installing hermes-agent..." -ForegroundColor Yellow
$INSTALL_CMDS = @'
set -e

# Install hermes via official installer
if ! command -v hermes &>/dev/null; then
    echo "   Installing hermes-agent..."
    curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash
    source ~/.bashrc 2>/dev/null || true
    source ~/.profile 2>/dev/null || true
else
    echo "   hermes already installed, updating..."
    hermes update --yes 2>/dev/null || pip install --upgrade hermes-agent 2>/dev/null || true
fi

hermes --version || echo "hermes installed (no --version flag)"
echo "hermes_install_done"
'@

ssh $SSH_OPTS.Split(" ") "ubuntu@$VM_IP" $INSTALL_CMDS
if ($LASTEXITCODE -ne 0) {
    Write-Host "   Install step failed." -ForegroundColor Red
    exit 1
}

# ── Step 4: Upload agent_api.py (if not already there from precosbot deploy) ──
Write-Host "`n4. Uploading agent_api.py..." -ForegroundColor Yellow
scp $SSH_OPTS.Split(" ") ".\agent_api.py" "ubuntu@$($VM_IP):/home/ubuntu/precosbot/agent_api.py"
if ($LASTEXITCODE -ne 0) {
    Write-Host "   SCP failed. Make sure precosbot is deployed first." -ForegroundColor Red
    exit 1
}
Write-Host "   agent_api.py uploaded" -ForegroundColor Green

# ── Step 5: Configure hermes ──────────────────────────────────────────────────
Write-Host "`n5. Configuring hermes for precosbot..." -ForegroundColor Yellow
$CONFIG_CMDS = @'
set -e

# Ensure ~/.hermes exists
mkdir -p ~/.hermes

# Set precosbot path in hermes config
PRECOSBOT_PATH="/home/ubuntu/precosbot"
CONFIG="$HOME/.hermes/config.yaml"

# Create or update config.yaml
if [ ! -f "$CONFIG" ]; then
    touch "$CONFIG"
fi

# Use Python to safely update YAML config
python3 - <<'PYEOF'
import yaml, os, sys
from pathlib import Path

config_path = Path.home() / ".hermes" / "config.yaml"
config = {}

if config_path.exists():
    try:
        content = config_path.read_text()
        config = yaml.safe_load(content) or {}
    except Exception:
        config = {}

# Set skills.config.precosbot.path
config.setdefault("skills", {})
config["skills"].setdefault("config", {})
config["skills"]["config"].setdefault("precosbot", {})
config["skills"]["config"]["precosbot"]["path"] = "/home/ubuntu/precosbot"

config_path.write_text(yaml.dump(config, default_flow_style=False, allow_unicode=True))
print("Config updated: skills.config.precosbot.path = /home/ubuntu/precosbot")
PYEOF

echo "hermes_config_done"
'@

ssh $SSH_OPTS.Split(" ") "ubuntu@$VM_IP" $CONFIG_CMDS
if ($LASTEXITCODE -ne 0) {
    Write-Host "   Config step failed." -ForegroundColor Red
    exit 1
}

# ── Step 6: Install precosbot skill in hermes ─────────────────────────────────
Write-Host "`n6. Installing precosbot skill in hermes..." -ForegroundColor Yellow
$SKILL_CMDS = @'
set -e

mkdir -p ~/.hermes/skills/shopping/precosbot

cat > ~/.hermes/skills/shopping/precosbot/SKILL.md << 'SKILLEOF'
---
name: precosbot
description: "Check and track product prices across Brazilian e-commerce stores (Amazon BR, KaBuM, Pichau, Mercado Livre, Terabyte Shop)."
version: 1.0.0
metadata:
  hermes:
    tags: [prices, shopping, brazil, e-commerce, amazon, mercadolivre, kabum, pichau]
    category: shopping
    config:
      - key: precosbot.path
        description: Path to the precosbot repository on this machine
        default: "/home/ubuntu/precosbot"
        prompt: "PreçoBot repository path"
---

# PreçoBot — Brazilian Price Tracker

You have access to precosbot tools for checking prices across Brazilian e-commerce stores.

## Tools

| Tool | Speed | Use When |
|------|-------|----------|
| `precosbot_check` | 30-120s | User wants current live prices |
| `precosbot_latest` | instant | User wants last cached scan |
| `precosbot_history` | instant | User asks about price trends |
| `precosbot_list_tracked` | instant | User asks what is monitored |
| `precosbot_db_stats` | instant | User asks about data coverage |

## Workflow

1. For "price of X?" — call `precosbot_latest` first (instant). If stale or missing, warn user then call `precosbot_check` (slow).
2. Sort results cheapest first. Flag unavailable stores.
3. Format prices in BRL: R$ 1.299,00

## Stores

Amazon BR, KaBuM!, Pichau, Terabyte Shop, Mercado Livre (new + used)

Note: Mercado Livre may be blocked from OCI IPs. Other stores are reliable.

## Language

Match user language. Price format always BRL.
SKILLEOF

echo "Skill installed at ~/.hermes/skills/shopping/precosbot/SKILL.md"
'@

ssh $SSH_OPTS.Split(" ") "ubuntu@$VM_IP" $SKILL_CMDS
if ($LASTEXITCODE -ne 0) {
    Write-Host "   Skill install step failed." -ForegroundColor Red
    exit 1
}

# ── Step 7: Install hermes precosbot tool in the hermes-agent install ─────────
Write-Host "`n7. Installing precosbot tool in hermes-agent..." -ForegroundColor Yellow
$TOOL_CMDS = @'
set -e

# Find hermes-agent installation directory
HERMES_INSTALL=$(python3 -c "import hermes_agent; import os; print(os.path.dirname(hermes_agent.__file__))" 2>/dev/null || \
    pip show hermes-agent 2>/dev/null | grep Location | awk '{print $2"/hermes_agent"}' || \
    find ~/.hermes -name "run_agent.py" -maxdepth 4 | head -1 | xargs dirname 2>/dev/null || \
    echo "")

# Try alternate: find via which hermes
if [ -z "$HERMES_INSTALL" ]; then
    HERMES_BIN=$(which hermes 2>/dev/null || echo "")
    if [ -n "$HERMES_BIN" ]; then
        HERMES_INSTALL=$(dirname "$HERMES_BIN")/../lib/python*/site-packages/hermes_agent 2>/dev/null | head -1
    fi
fi

# Try: find in common locations
if [ -z "$HERMES_INSTALL" ] || [ ! -d "$HERMES_INSTALL" ]; then
    for candidate in \
        "$HOME/.hermes/hermes-agent" \
        "$HOME/.local/lib/python3.*/site-packages/hermes_agent" \
        "/usr/local/lib/python3.*/site-packages/hermes_agent"; do
        if ls -d $candidate 2>/dev/null | head -1 | xargs test -d 2>/dev/null; then
            HERMES_INSTALL=$(ls -d $candidate 2>/dev/null | head -1)
            break
        fi
    done
fi

if [ -z "$HERMES_INSTALL" ] || [ ! -d "$HERMES_INSTALL" ]; then
    echo "WARNING: Could not locate hermes-agent installation directory."
    echo "Please manually copy the precosbot.py tool:"
    echo "  Find hermes tools dir: python3 -c \"import model_tools; import os; print(os.path.dirname(model_tools.__file__))\""
    echo "  Then: cp /home/ubuntu/precosbot/hermes_tool_precosbot.py <tools_dir>/precosbot.py"
    exit 0
fi

TOOLS_DIR="$HERMES_INSTALL/tools"
if [ ! -d "$TOOLS_DIR" ]; then
    echo "WARNING: tools/ directory not found at $HERMES_INSTALL"
    exit 0
fi

echo "Found hermes tools at: $TOOLS_DIR"
cp /home/ubuntu/precosbot/hermes_tool_precosbot.py "$TOOLS_DIR/precosbot.py"
echo "Tool installed: $TOOLS_DIR/precosbot.py"

# Also patch toolsets.py
TOOLSETS="$HERMES_INSTALL/../toolsets.py"
if [ ! -f "$TOOLSETS" ]; then
    TOOLSETS=$(find "$HERMES_INSTALL" -name "toolsets.py" | head -1)
fi
if [ -f "$TOOLSETS" ]; then
    if ! grep -q "precosbot_check" "$TOOLSETS"; then
        python3 - "$TOOLSETS" <<'PYEOF'
import sys
path = sys.argv[1]
content = open(path).read()
marker = '"kanban_show", "kanban_complete"'
insert = '    # PreçoBot — Brazilian e-commerce price tracking (gated via check_fn)\n    "precosbot_check", "precosbot_latest", "precosbot_history",\n    "precosbot_list_tracked", "precosbot_db_stats",\n'
if marker in content and "precosbot_check" not in content:
    content = content.replace(marker, insert + "    " + marker)
    open(path, "w").write(content)
    print(f"Patched {path}")
else:
    print(f"Skipped patching {path} (already patched or marker not found)")
PYEOF
    else
        echo "toolsets.py already has precosbot tools"
    fi
fi
'@

# First, upload the tool file with a temp name
scp $SSH_OPTS.Split(" ") "E:\Code\hermes-agent\tools\precosbot.py" "ubuntu@$($VM_IP):/home/ubuntu/precosbot/hermes_tool_precosbot.py"

ssh $SSH_OPTS.Split(" ") "ubuntu@$VM_IP" $TOOL_CMDS

# ── Step 8: Test the setup ────────────────────────────────────────────────────
Write-Host "`n8. Testing precosbot integration..." -ForegroundColor Yellow
$TEST_CMDS = @'
set -e
cd /home/ubuntu/precosbot
source venv/bin/activate

echo "Testing agent_api.py..."
python agent_api.py db-stats && echo "db-stats: OK" || echo "db-stats: FAILED (DB may be empty)"

echo ""
echo "Testing list-tracked..."
python agent_api.py list-tracked && echo "list-tracked: OK" || echo "list-tracked: FAILED"

echo ""
echo "Testing hermes skill presence..."
ls ~/.hermes/skills/shopping/precosbot/SKILL.md && echo "Skill: OK" || echo "Skill: MISSING"

echo ""
echo "All tests complete."
'@

ssh $SSH_OPTS.Split(" ") "ubuntu@$VM_IP" $TEST_CMDS

Write-Host "`n=== Hermes Deployment Complete! ===" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "1. SSH to VM:  ssh -i $SSH_KEY ubuntu@$VM_IP"
Write-Host "2. Set API key: nano ~/.hermes/.env  (add ANTHROPIC_API_KEY=...)"
Write-Host "3. Run hermes: hermes"
Write-Host "4. Test skill: /precosbot"
Write-Host "5. Try:        'qual o preco do RTX 4070?'"
Write-Host ""
Write-Host "For Telegram gateway:"
Write-Host "  hermes gateway setup  (follow prompts)"
Write-Host "  hermes gateway start"
