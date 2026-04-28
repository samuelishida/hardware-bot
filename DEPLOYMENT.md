# PreçoBot Deployment Guide - OCI VM

## VM Information
- **Public IP**: 137.131.245.64
- **Instance OCID**: `ocid1.instance.oc1.sa-saopaulo-1.antxeljrmpaenmacocvwieehfnr6r33qqzkops6voubp7zspjzydec3x7mga`
- **Shape**: VM.Standard.E2.1.Micro
- **OS**: Ubuntu (with Docker pre-installed via cloud-init)

## SSH Key Issue

**Problem**: The VM has an ED25519 SSH key (`yvy-oci-deploy`) authorized, but the matching private key is not available locally.

**Available local keys**:
- `oci_yvy` (RSA 4096-bit) - fingerprint: `SHA256:UXgmMLtpNeMr4OLfKQ3pim/NHV8t15YYU6pzO5Kh2rk` ❌
- `id_rsa` (RSA) - fingerprint: `SHA256:sWYm3X3NTOBQ9he3V6Jpgx3AKdqIclVSlNTMcsSTcfs` ❌

**VM authorized key**: ED25519 - fingerprint: `SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU`

## Solution Options

### Option 1: Add SSH Key via OCI Console (Recommended)

1. **Generate new SSH key pair**:
   ```powershell
   ssh-keygen -t ed25519 -f C:\temp\precosbot_deploy -N "" -C "precosbot@oci"
   ```

2. **Add key to VM via OCI Console**:
   - Go to: OCI Console → Compute → Instances → yvy-server (137.131.245.64)
   - Click on the instance
   - Under "Resources" → "SSH Keys"
   - Click "Add SSH Key"
   - Paste contents of `C:\temp\precosbot_deploy.pub`
   - Save

3. **Deploy using the script**:
   ```powershell
   cd E:\Code\Scripts\precosbot
   .\deploy-to-oci.ps1
   ```

### Option 2: Manual Deployment via Cloud-Init Script

Use OCI Console's "Cloud-init" feature to add SSH key on next boot:

1. **Create cloud-init user_data** (Base64 encoded):
   ```yaml
   #cloud-config
   ssh_authorized_keys:
     - ssh-ed25519 AAAA...<your_public_key>...precosbot@oci
   ```

2. **Stop and start instance** (cloud-init runs on first boot only, so use "Stop" then "Start", NOT "Reset")

3. **Deploy files**:
   ```powershell
   ssh -i C:\temp\precosbot ubuntu@137.131.245.64
   ```

### Option 3: Use OCI Instance Console Connection (Advanced)

Connect via serial console to add SSH key manually:
1. OCI Console → Instance → Console Connection → Create
2. Connect via serial console
3. Edit `/home/ubuntu/.ssh/authorized_keys`
4. Add your public key

## Manual Deployment Steps (once SSH access is available)

### 1. Upload files
```powershell
scp -i C:\temp\precosbot E:\Code\Scripts\precosbot\precosbot_deploy.zip ubuntu@137.131.245.64:/tmp/
```

### 2. SSH into VM
```powershell
ssh -i C:\temp\precosbot ubuntu@137.131.245.64
```

### 3. Setup on VM
```bash
# Extract
mkdir -p /home/ubuntu/precosbot
unzip /tmp/precosbot_deploy.zip -d /home/ubuntu/precosbot
cd /home/ubuntu/precosbot

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Create .env file
cp .env.example .env
nano .env  # Edit with Discord credentials
```

### 4. Create .env file
```env
DISCORD_TOKEN=your_bot_token_here
DISCORD_GUILD_ID=your_guild_id
ALERT_CHANNEL_ID=your_channel_id
SCRAPE_INTERVAL_MINUTES=15
PRICE_DROP_THRESHOLD_PCT=5
```

### 5. Test and run
```bash
# Test imports
python -c "from config import DISCORD_TOKEN; print('OK')"

# Run bot
python main.py
```

### 6. Setup as systemd service (optional)
```bash
sudo nano /etc/systemd/system/precosbot.service
```

```ini
[Unit]
Description=PreçoBot Discord Price Tracker
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/precosbot
Environment=PATH=/home/ubuntu/precosbot/venv/bin
ExecStart=/home/ubuntu/precosbot/venv/bin/python main.py
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable precosbot
sudo systemctl start precosbot
sudo systemctl status precosbot
```

## Verification

After deployment, verify the bot is running:

```powershell
# Check process
ssh ubuntu@137.131.245.64 "ps aux | grep python"

# Check logs (if systemd)
ssh ubuntu@137.131.245.64 "journalctl -u precosbot -f"

# Test in Discord
# Run /status command - should respond with bot status
```

## Troubleshooting

### Bot not responding in Discord
1. Check if process is running: `ps aux | grep python`
2. Check logs: `journalctl -u precosbot -n 50`
3. Verify `.env` file has correct Discord token
4. Check Discord bot permissions in server

### SSH connection refused
- Verify VM is running: `oci compute instance get --instance-id <OCID>`
- Check security list allows port 22
- Try restarting VM from OCI Console

### Memory issues (E2.1.Micro has 1GB RAM)
- Monitor: `free -h`
- If OOM, consider upgrading shape or adding swap:
  ```bash
  sudo fallocate -l 2G /swapfile
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile
  sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
  ```

## Rollback

To remove the bot:
```bash
sudo systemctl stop precosbot
sudo systemctl disable precosbot
sudo rm /etc/systemd/system/precosbot.service
rm -rf /home/ubuntu/precosbot
```
