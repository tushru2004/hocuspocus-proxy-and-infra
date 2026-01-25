#!/bin/bash
# Install macOS location sender daemon
# Sends device location to VPN proxy every 30 seconds

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Installing Hocuspocus Location Sender..."

# Check for Python 3
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 not found. Install it first."
    exit 1
fi

# Install pyobjc-framework-CoreLocation
echo "Installing Python dependencies..."
pip3 install --user pyobjc-framework-CoreLocation requests

# Copy script to /usr/local/bin
echo "Installing location sender script..."
sudo cp "$SCRIPT_DIR/location_sender.py" /usr/local/bin/hocuspocus-location-sender.py
sudo chmod +x /usr/local/bin/hocuspocus-location-sender.py

# Install LaunchAgent
echo "Installing LaunchAgent..."
mkdir -p ~/Library/LaunchAgents
cp "$SCRIPT_DIR/com.hocuspocus.location-sender.plist" ~/Library/LaunchAgents/

# Unload if already running, then load
launchctl unload ~/Library/LaunchAgents/com.hocuspocus.location-sender.plist 2>/dev/null || true
launchctl load ~/Library/LaunchAgents/com.hocuspocus.location-sender.plist

echo ""
echo "============================================"
echo "Location Sender installed successfully!"
echo "============================================"
echo ""
echo "The daemon will start automatically on login."
echo ""
echo "IMPORTANT: Grant location permissions:"
echo "  System Settings > Privacy & Security > Location Services"
echo "  Enable for 'Python' or 'Terminal' (depending on how it runs)"
echo ""
echo "Check status:"
echo "  launchctl list | grep hocuspocus"
echo ""
echo "View logs:"
echo "  tail -f /var/log/hocuspocus-location-sender.log"
echo ""
echo "Uninstall:"
echo "  launchctl unload ~/Library/LaunchAgents/com.hocuspocus.location-sender.plist"
echo "  rm ~/Library/LaunchAgents/com.hocuspocus.location-sender.plist"
echo "  sudo rm /usr/local/bin/hocuspocus-location-sender.py"
