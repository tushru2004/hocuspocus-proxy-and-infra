#!/bin/bash
# Generate .mobileconfig profile for iPhone/Mac VPN with certificate auth
# Supports device-specific certificates for fixed IP assignment
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OUTPUT_DIR="${SCRIPT_DIR}/../vpn-profiles"
mkdir -p "$OUTPUT_DIR"

# Parse arguments
DEVICE_NAME="${1:-}"  # e.g., "iphone" or "macbook-air"
if [ -z "$DEVICE_NAME" ]; then
    echo "Usage: $0 <device-name>"
    echo "  device-name: 'iphone' or 'macbook-air'"
    echo ""
    echo "Examples:"
    echo "  $0 iphone         # Generate profile for iPhone (IP: 10.10.10.10)"
    echo "  $0 macbook-air    # Generate profile for MacBook Air (IP: 10.10.10.20)"
    exit 1
fi

# Device name is used as LocalIdentifier in VPN config
# This must match the rightid in ipsec.conf for fixed IP assignment
LOCAL_IDENTIFIER="$DEVICE_NAME"

echo "Generating VPN profile for device: $DEVICE_NAME"
echo "LocalIdentifier: $LOCAL_IDENTIFIER"
echo "Fetching certificates from VPN pod..."

# Get the VPN pod name
VPN_POD=$(kubectl get pods -n hocuspocus -l app=vpn-server -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
if [ -z "$VPN_POD" ]; then
    echo "ERROR: VPN pod not found. Is the VPN running?"
    exit 1
fi

# Get the VPN server IP
SERVER_IP=$(kubectl get svc vpn-service -n hocuspocus -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
if [ -z "$SERVER_IP" ]; then
    echo "ERROR: Could not get VPN server IP"
    exit 1
fi

echo "VPN Server: $SERVER_IP"
echo "VPN Pod: $VPN_POD"

# Fetch certificates from the pod (device-specific certs)
echo "Extracting certificates for device: $DEVICE_NAME..."
CA_CERT=$(kubectl exec -n hocuspocus "$VPN_POD" -c strongswan -- cat /etc/ipsec.d/cacerts/ca-cert.pem 2>/dev/null)
CLIENT_CERT=$(kubectl exec -n hocuspocus "$VPN_POD" -c strongswan -- cat /etc/ipsec.d/certs/client-${DEVICE_NAME}-cert.pem 2>/dev/null)
CLIENT_KEY=$(kubectl exec -n hocuspocus "$VPN_POD" -c strongswan -- cat /etc/ipsec.d/private/client-${DEVICE_NAME}-key.pem 2>/dev/null)

if [ -z "$CA_CERT" ] || [ -z "$CLIENT_CERT" ] || [ -z "$CLIENT_KEY" ]; then
    echo "ERROR: Could not fetch certificates. The VPN may need to be restarted to generate client certs."
    echo "Run: kubectl rollout restart daemonset/vpn-server -n hocuspocus"
    exit 1
fi

# Get mitmproxy CA certificate for HTTPS interception
echo "Fetching mitmproxy CA certificate..."
MITMPROXY_POD=$(kubectl get pods -n hocuspocus -l app=mitmproxy -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
MITMPROXY_CA=""
if [ -n "$MITMPROXY_POD" ]; then
    MITMPROXY_CA=$(kubectl exec -n hocuspocus "$MITMPROXY_POD" -- cat /home/mitmproxy/.mitmproxy/mitmproxy-ca-cert.pem 2>/dev/null || true)
fi
if [ -z "$MITMPROXY_CA" ]; then
    echo "WARNING: Could not fetch mitmproxy CA. HTTPS interception may not work."
fi

# Create PKCS12 bundle
echo "Creating PKCS12 bundle..."
TEMP_DIR=$(mktemp -d)
echo "$CA_CERT" > "$TEMP_DIR/ca.pem"
echo "$CLIENT_CERT" > "$TEMP_DIR/client.pem"
echo "$CLIENT_KEY" > "$TEMP_DIR/client-key.pem"

openssl pkcs12 -export \
    -inkey "$TEMP_DIR/client-key.pem" \
    -in "$TEMP_DIR/client.pem" \
    -certfile "$TEMP_DIR/ca.pem" \
    -name "Hocuspocus VPN" \
    -out "$TEMP_DIR/client.p12" \
    -passout pass:hocuspocus

# Base64 encode certificates for mobileconfig
CA_CERT_B64=$(base64 < "$TEMP_DIR/ca.pem" | tr -d '\n')
P12_B64=$(base64 < "$TEMP_DIR/client.p12" | tr -d '\n')

# Base64 encode mitmproxy CA if available
MITMPROXY_CA_B64=""
if [ -n "$MITMPROXY_CA" ]; then
    echo "$MITMPROXY_CA" > "$TEMP_DIR/mitmproxy-ca.pem"
    MITMPROXY_CA_B64=$(base64 < "$TEMP_DIR/mitmproxy-ca.pem" | tr -d '\n')
fi

# Generate UUIDs for the profile
UUID1=$(uuidgen)
UUID2=$(uuidgen)
UUID3=$(uuidgen)
UUID4=$(uuidgen)
UUID5=$(uuidgen)

# Create mobileconfig with device-specific filename
OUTPUT_FILE="$OUTPUT_DIR/hocuspocus-vpn-${DEVICE_NAME}.mobileconfig"

cat > "$OUTPUT_FILE" << MOBILECONFIG
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>PayloadContent</key>
    <array>
        <!-- CA Certificate -->
        <dict>
            <key>PayloadCertificateFileName</key>
            <string>ca.cer</string>
            <key>PayloadContent</key>
            <data>$CA_CERT_B64</data>
            <key>PayloadDescription</key>
            <string>Adds a CA root certificate</string>
            <key>PayloadDisplayName</key>
            <string>Hocuspocus VPN CA</string>
            <key>PayloadIdentifier</key>
            <string>com.hocuspocus.vpn.ca</string>
            <key>PayloadType</key>
            <string>com.apple.security.root</string>
            <key>PayloadUUID</key>
            <string>$UUID1</string>
            <key>PayloadVersion</key>
            <integer>1</integer>
        </dict>
MOBILECONFIG

# Add mitmproxy CA if available
if [ -n "$MITMPROXY_CA_B64" ]; then
cat >> "$OUTPUT_FILE" << MOBILECONFIG
        <!-- Mitmproxy CA Certificate for HTTPS interception -->
        <dict>
            <key>PayloadCertificateFileName</key>
            <string>mitmproxy-ca.cer</string>
            <key>PayloadContent</key>
            <data>$MITMPROXY_CA_B64</data>
            <key>PayloadDescription</key>
            <string>Adds mitmproxy CA for HTTPS filtering</string>
            <key>PayloadDisplayName</key>
            <string>Hocuspocus Proxy CA</string>
            <key>PayloadIdentifier</key>
            <string>com.hocuspocus.proxy.ca</string>
            <key>PayloadType</key>
            <string>com.apple.security.root</string>
            <key>PayloadUUID</key>
            <string>$UUID5</string>
            <key>PayloadVersion</key>
            <integer>1</integer>
        </dict>
MOBILECONFIG
fi

cat >> "$OUTPUT_FILE" << MOBILECONFIG
        <!-- Client Certificate (PKCS12) -->
        <dict>
            <key>PayloadCertificateFileName</key>
            <string>client.p12</string>
            <key>PayloadContent</key>
            <data>$P12_B64</data>
            <key>PayloadDescription</key>
            <string>Adds a PKCS#12-formatted certificate</string>
            <key>PayloadDisplayName</key>
            <string>Hocuspocus VPN Client</string>
            <key>PayloadIdentifier</key>
            <string>com.hocuspocus.vpn.client</string>
            <key>PayloadType</key>
            <string>com.apple.security.pkcs12</string>
            <key>PayloadUUID</key>
            <string>$UUID2</string>
            <key>PayloadVersion</key>
            <integer>1</integer>
            <key>Password</key>
            <string>hocuspocus</string>
        </dict>
        <!-- VPN Configuration (AlwaysOn) -->
        <dict>
            <key>PayloadDescription</key>
            <string>Configures AlwaysOn VPN settings</string>
            <key>PayloadDisplayName</key>
            <string>Hocuspocus VPN</string>
            <key>PayloadIdentifier</key>
            <string>com.hocuspocus.vpn.config</string>
            <key>PayloadType</key>
            <string>com.apple.vpn.managed</string>
            <key>PayloadUUID</key>
            <string>$UUID3</string>
            <key>PayloadVersion</key>
            <integer>1</integer>
            <key>UserDefinedName</key>
            <string>Hocuspocus VPN</string>
            <key>VPNType</key>
            <string>AlwaysOn</string>
            <key>AlwaysOn</key>
            <dict>
                <key>UIToggleEnabled</key>
                <integer>0</integer>
                <key>AllowCaptiveWebSheet</key>
                <true/>
                <!-- ServiceExceptions: Allow DeviceCommunication for Xcode/CoreDevice (iOS 17.4+) -->
                <key>ServiceExceptions</key>
                <array>
                    <dict>
                        <key>ServiceName</key>
                        <string>DeviceCommunication</string>
                        <key>Action</key>
                        <string>Allow</string>
                    </dict>
                </array>
                <key>TunnelConfigurations</key>
                <array>
                    <dict>
                        <key>ProtocolType</key>
                        <string>IKEv2</string>
                        <key>Interfaces</key>
                        <array>
                            <string>Cellular</string>
                            <string>WiFi</string>
                        </array>
                        <key>RemoteAddress</key>
                        <string>$SERVER_IP</string>
                        <key>RemoteIdentifier</key>
                        <string>$SERVER_IP</string>
                        <key>LocalIdentifier</key>
                        <string>$LOCAL_IDENTIFIER</string>
                        <key>AuthenticationMethod</key>
                        <string>Certificate</string>
                        <key>PayloadCertificateUUID</key>
                        <string>$UUID2</string>
                        <key>CertificateType</key>
                        <string>RSA</string>
                        <key>ServerCertificateIssuerCommonName</key>
                        <string>Hocuspocus VPN CA</string>
                        <key>EnablePFS</key>
                        <true/>
                        <key>IKESecurityAssociationParameters</key>
                        <dict>
                            <key>EncryptionAlgorithm</key>
                            <string>AES-256</string>
                            <key>IntegrityAlgorithm</key>
                            <string>SHA2-256</string>
                            <key>DiffieHellmanGroup</key>
                            <integer>14</integer>
                        </dict>
                        <key>ChildSecurityAssociationParameters</key>
                        <dict>
                            <key>EncryptionAlgorithm</key>
                            <string>AES-256</string>
                            <key>IntegrityAlgorithm</key>
                            <string>SHA2-256</string>
                            <key>DiffieHellmanGroup</key>
                            <integer>14</integer>
                        </dict>
                    </dict>
                </array>
            </dict>
        </dict>
    </array>
    <key>PayloadDisplayName</key>
    <string>Hocuspocus VPN ($DEVICE_NAME)</string>
    <key>PayloadIdentifier</key>
    <string>com.hocuspocus.vpn.$DEVICE_NAME</string>
    <key>PayloadRemovalDisallowed</key>
    <false/>
    <key>PayloadType</key>
    <string>Configuration</string>
    <key>PayloadUUID</key>
    <string>$UUID4</string>
    <key>PayloadVersion</key>
    <integer>1</integer>
</dict>
</plist>
MOBILECONFIG

# Cleanup
rm -rf "$TEMP_DIR"

echo ""
echo "=========================================="
echo "VPN Profile generated: $OUTPUT_FILE"
echo "=========================================="
echo ""
echo "To install on iPhone:"
echo "1. Transfer the file to your iPhone (AirDrop, email, or web)"
echo "2. Open Settings > General > VPN & Device Management"
echo "3. Tap the profile to install"
echo "4. When prompted for password, enter: hocuspocus"
echo ""
echo "Or serve it via HTTP:"
echo "  cd $OUTPUT_DIR && python3 -m http.server 8000"
echo "  Then open http://$(ipconfig getifaddr en0):8000/hocuspocus-vpn.mobileconfig on iPhone"
