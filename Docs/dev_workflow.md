# Dev Workflow (WSL2 Ubuntu)

This project uses WSL2 Ubuntu as the authoritative local development environment.
Host Windows Python is not authoritative.

## 1) Windows Prerequisites (PowerShell as Administrator)

```powershell
# Enable required Windows features (safe to re-run).
dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart
dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart

# Ensure WSL2 is default.
wsl --set-default-version 2

# Install Ubuntu (safe if already installed).
wsl --install -d Ubuntu

# Verify.
wsl --status
wsl -l -v
```

Optional WSL resource tuning (`%UserProfile%\.wslconfig`):
```ini
[wsl2]
memory=8GB
processors=4
swap=4GB
localhostForwarding=true
```
Then run:
```powershell
wsl --shutdown
```

## 2) Ubuntu Base Setup

Open Ubuntu and run:
```bash
set -euo pipefail
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg lsb-release software-properties-common git
```

Python 3.12 setup:
```bash
set -euo pipefail
if ! command -v python3.12 >/dev/null 2>&1; then
  sudo add-apt-repository -y ppa:deadsnakes/ppa
  sudo apt-get update
  sudo apt-get install -y python3.12 python3.12-venv python3.12-dev
else
  sudo apt-get install -y python3.12-venv python3.12-dev
fi
python3.12 --version
```

Virtual environment + pip/PyPI connectivity:
```bash
set -euo pipefail
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip --version
python - <<'PY'
import requests
r = requests.get("https://pypi.org/simple", timeout=10)
print("PyPI status:", r.status_code)
assert r.status_code < 400
PY
```

## 3) Docker Engine Inside WSL2 Ubuntu (No Docker Desktop Required)

```bash
set -euo pipefail

# Remove conflicting Docker packages if present.
for pkg in docker.io docker-doc docker-compose podman-docker containerd runc; do
  sudo apt-get remove -y "$pkg" || true
done

# Add official Docker repository.
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Enable/start Docker daemon in WSL (requires systemd-enabled WSL image).
sudo systemctl enable docker
sudo systemctl start docker

# Allow non-root Docker usage.
sudo groupadd docker || true
sudo usermod -aG docker "$USER"
newgrp docker <<'EOF'
docker --version
docker info
docker run --rm hello-world
EOF
```

If `systemctl` is unavailable, enable systemd in `/etc/wsl.conf`:
```ini
[boot]
systemd=true
```
Then from Windows:
```powershell
wsl --shutdown
```

## 4) Project Bootstrap in WSL2

```bash
set -euo pipefail

# Clone if needed.
if [ ! -d "$HOME/seo-accelerator-tool/.git" ]; then
  git clone <YOUR_REPO_URL> "$HOME/seo-accelerator-tool"
fi
cd "$HOME/seo-accelerator-tool"

# Python env.
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r backend/requirements-dev.txt

# Validation gates.
python -m ruff check backend
python -m pytest -q
python backend/scripts/validate_production_config.py
```

## 5) Containerized Validation (Optional but Recommended)

```bash
set -euo pipefail
docker compose build
docker compose run --rm test-runner
docker compose run --rm api ruff check backend
docker compose run --rm api python backend/scripts/validate_production_config.py
```

## 6) Required Before Pushing to Main

1. `python -m ruff check backend`
2. `python -m pytest -q`
3. `python backend/scripts/validate_production_config.py`
4. `docker compose run --rm test-runner`
