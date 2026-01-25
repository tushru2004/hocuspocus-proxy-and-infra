#!/bin/bash
# Push VPN profile to device via SimpleMDM (silent install)
# Supports device-specific profiles for fixed IP assignment
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# SimpleMDM API key (store in environment variable for security)
API_KEY="${SIMPLEMDM_API_KEY:-2IkV3x1TEpS9r6AGtmeyvLlBMvwHzCeJgQY4O8VyTtoss2KR6qVpEZcQqPlmLrLV}"

# Parse arguments
DEVICE_NAME="${1:-}"
if [ -z "$DEVICE_NAME" ]; then
    echo "Usage: $0 <device-name>"
    echo "  device-name: 'iphone' or 'macbook-air'"
    echo ""
    echo "Examples:"
    echo "  $0 iphone         # Push profile for iPhone (IP: 10.10.10.10)"
    echo "  $0 macbook-air    # Push profile for MacBook Air (IP: 10.10.10.20)"
    exit 1
fi

# Device name to SimpleMDM ID and IP mapping
case "$DEVICE_NAME" in
    iphone)
        DEVICE_ID="2154382"
        DEVICE_IP="10.10.10.10"
        ;;
    macbook-air)
        DEVICE_ID="2162127"
        DEVICE_IP="10.10.10.20"
        ;;
    *)
        echo "ERROR: Unknown device '$DEVICE_NAME'. Known devices: iphone, macbook-air"
        exit 1
        ;;
esac

PROFILE_PATH="${SCRIPT_DIR}/../vpn-profiles/hocuspocus-vpn-${DEVICE_NAME}.mobileconfig"
PROFILE_NAME="Hocuspocus VPN (${DEVICE_NAME})"

# Generate fresh profile first
echo "Generating VPN profile for device: $DEVICE_NAME..."
"${SCRIPT_DIR}/generate-vpn-profile.sh" "$DEVICE_NAME"

# Check for existing profile with same name
echo "Checking for existing profile..."
EXISTING_PROFILE=$(curl -s -u "${API_KEY}:" \
  "https://a.simplemdm.com/api/v1/custom_configuration_profiles" | \
  python3 -c "import sys, json; data=json.load(sys.stdin)['data']; profiles=[p for p in data if p['attributes']['name']=='${PROFILE_NAME}']; print(profiles[0]['id'] if profiles else '')" 2>/dev/null)

if [ -n "$EXISTING_PROFILE" ]; then
    echo "Deleting existing profile (ID: $EXISTING_PROFILE)..."
    curl -s -X DELETE -u "${API_KEY}:" \
      "https://a.simplemdm.com/api/v1/custom_configuration_profiles/${EXISTING_PROFILE}" > /dev/null
    sleep 2
fi

# Upload new profile
echo "Uploading VPN profile to SimpleMDM..."
PROFILE_ID=$(curl -s -X POST \
  -u "${API_KEY}:" \
  -F "name=${PROFILE_NAME}" \
  -F "mobileconfig=@${PROFILE_PATH}" \
  "https://a.simplemdm.com/api/v1/custom_configuration_profiles" | \
  python3 -c "import sys, json; print(json.load(sys.stdin)['data']['id'])")

echo "Profile uploaded (ID: $PROFILE_ID)"

# Get device name from SimpleMDM for display
SIMPLEMDM_DEVICE_NAME=$(curl -s -u "${API_KEY}:" \
  "https://a.simplemdm.com/api/v1/devices/${DEVICE_ID}" | \
  python3 -c "import sys, json; print(json.load(sys.stdin)['data']['attributes']['device_name'])" 2>/dev/null)

# Push to specific device
echo "Pushing profile to: $SIMPLEMDM_DEVICE_NAME (ID: $DEVICE_ID)..."
curl -s -X POST -u "${API_KEY}:" \
  "https://a.simplemdm.com/api/v1/custom_configuration_profiles/${PROFILE_ID}/devices/${DEVICE_ID}" > /dev/null

echo ""
echo "==========================================="
echo "VPN profile pushed to $SIMPLEMDM_DEVICE_NAME!"
echo "==========================================="
echo ""
echo "Device: $DEVICE_NAME"
echo "Fixed IP: $DEVICE_IP"
echo ""
echo "The profile installs automatically on supervised devices."
