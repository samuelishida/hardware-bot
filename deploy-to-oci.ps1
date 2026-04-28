# Deploy PreçoBot to OCI VM
# Usage: .\deploy-to-oci.ps1

$VM_IP = "137.131.245.64"
$SSH_KEY = "$env:USERPROFILE\.ssh\oci_yvy"
$REMOTE_DIR = "/home/ubuntu/precosbot"

Write-Host "=== Deploying PreçoBot to OCI VM ($VM_IP) ===" -ForegroundColor Cyan

# Create deployment package (exclude tests, cache, db)
Write-Host "`n1. Creating deployment package..." -ForegroundColor Yellow
$EXCLUDE = @("*.pyc", "__pycache__", ".pytest_cache", "*.db", "test_*.py", "TEST_*.md", "FIXES_*.md")
$FILES = Get-ChildItem -Path "." -Exclude $EXCLUDE | Where-Object { $_.Name -notmatch "^test_" -and $_.Name -notmatch "^\." }

# Create temp directory
$TEMP_DIR = ".\deploy_tmp"
if (Test-Path $TEMP_DIR) { Remove-Item $TEMP_DIR -Recurse -Force }
New-Item -ItemType Directory -Path $TEMP_DIR | Out-Null

# Copy files
$FILES | Copy-Item -Destination $TEMP_DIR -Recurse
Write-Host "   Copied $($FILES.Count) files to $TEMP_DIR"

# Create zip
$ZIP_FILE = ".\precosbot_deploy.zip"
Compress-Archive -Path "$TEMP_DIR\*" -DestinationPath $ZIP_FILE -Force
Write-Host "   Created $ZIP_FILE"

# Upload to VM
Write-Host "`n2. Uploading to VM..." -ForegroundColor Yellow
scp -i $SSH_KEY -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null `
    $ZIP_FILE "ubuntu@$($VM_IP):/tmp/"

if ($LASTEXITCODE -ne 0) {
    Write-Host "   ❌ SCP failed!" -ForegroundColor Red
    exit 1
}
Write-Host "   ✅ Upload complete"

# Deploy on VM
Write-Host "`n3. Deploying on VM..." -ForegroundColor Yellow
$SSH_CMDS = @'
set -e
echo "   Creating directory..."
mkdir -p /home/ubuntu/precosbot
echo "   Extracting..."
unzip -o /tmp/precosbot_deploy.zip -d /home/ubuntu/precosbot
echo "   Cleaning up..."
rm /tmp/precosbot_deploy.zip
cd /home/ubuntu/precosbot
echo "   Creating venv..."
python3 -m venv venv || true
echo "   Activating venv..."
source venv/bin/activate
echo "   Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt
echo "   ✅ Deployment complete!"
'@

ssh -i $SSH_KEY -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null `
    "ubuntu@$($VM_IP)" $SSH_CMDS

if ($LASTEXITCODE -ne 0) {
    Write-Host "   ❌ SSH deployment failed!" -ForegroundColor Red
    exit 1
}

# Cleanup
Write-Host "`n4. Cleaning up..." -ForegroundColor Yellow
Remove-Item $TEMP_DIR -Recurse -Force
Remove-Item $ZIP_FILE -Force
Write-Host "   ✅ Cleanup complete"

Write-Host "`n=== Deployment Complete! ===" -ForegroundColor Green
Write-Host "Next steps:"
Write-Host "1. SSH into VM: ssh -i $SSH_KEY ubuntu@$VM_IP"
Write-Host "2. Copy .env file: Create .env based on .env.example"
Write-Host "3. Start bot: cd /home/ubuntu/precosbot && source venv/bin/activate && python main.py"
