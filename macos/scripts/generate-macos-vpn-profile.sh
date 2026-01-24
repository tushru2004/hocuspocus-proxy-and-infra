#!/bin/bash
#
# Generate macOS VPN Profile (.mobileconfig)
#
# This creates an IKEv2 VPN profile for macOS with:
# - Certificate-based authentication
# - VPN On-Demand (auto-connect for all traffic)
# - Similar to iOS setup but macOS-specific
#
# Usage: ./generate-macos-vpn-profile.sh
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MACOS_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_DIR="$(dirname "$MACOS_DIR")"
OUTPUT_DIR="$MACOS_DIR/profiles"

# Ensure output directory exists
mkdir -p "$OUTPUT_DIR"

echo "=== Generating macOS VPN Profile ==="
echo ""

# Get VPN server IP
VPN_IP=$(kubectl get svc vpn-service -n hocuspocus -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null)
if [ -z "$VPN_IP" ]; then
    echo "Error: Could not get VPN service IP. Is the cluster running?"
    exit 1
fi
echo "VPN Server IP: $VPN_IP"

# Get certificates from VPN pod
echo "Fetching certificates from VPN server..."
VPN_POD=$(kubectl get pods -n hocuspocus -l app=vpn-server -o jsonpath='{.items[0].metadata.name}')

if [ -z "$VPN_POD" ]; then
    echo "Error: VPN pod not found"
    exit 1
fi

# Create temp directory for certs
TEMP_DIR=$(mktemp -d)
trap "rm -rf $TEMP_DIR" EXIT

# Extract certificates using kubectl exec (more reliable than cp)
echo "Extracting VPN CA..."
kubectl exec -n hocuspocus "$VPN_POD" -c strongswan -- cat /etc/ipsec.d/cacerts/ca-cert.pem > "$TEMP_DIR/vpn-ca.pem" 2>/dev/null
echo "Extracting client certificate..."
kubectl exec -n hocuspocus "$VPN_POD" -c strongswan -- cat /etc/ipsec.d/certs/client-cert.pem > "$TEMP_DIR/client.pem" 2>/dev/null
echo "Extracting client key..."
kubectl exec -n hocuspocus "$VPN_POD" -c strongswan -- cat /etc/ipsec.d/private/client-key.pem > "$TEMP_DIR/client.key" 2>/dev/null

# Verify certificates were extracted
if [ ! -s "$TEMP_DIR/vpn-ca.pem" ] || [ ! -s "$TEMP_DIR/client.pem" ] || [ ! -s "$TEMP_DIR/client.key" ]; then
    echo "Error: Could not extract VPN certificates. The VPN may need to be restarted."
    echo "Run: kubectl rollout restart deployment/vpn-server -n hocuspocus"
    exit 1
fi

# Get mitmproxy CA
echo "Extracting mitmproxy CA..."
MITMPROXY_POD=$(kubectl get pods -n hocuspocus -l app=mitmproxy -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n hocuspocus "$MITMPROXY_POD" -- cat /home/mitmproxy/.mitmproxy/mitmproxy-ca-cert.pem > "$TEMP_DIR/mitmproxy-ca.pem" 2>/dev/null || true

if [ ! -s "$TEMP_DIR/mitmproxy-ca.pem" ]; then
    echo "Warning: Could not extract mitmproxy CA. HTTPS filtering may not work."
fi

# Convert certificates to base64
VPN_CA_BASE64=$(base64 -i "$TEMP_DIR/vpn-ca.pem" | tr -d '\n')
MITMPROXY_CA_BASE64=$(base64 -i "$TEMP_DIR/mitmproxy-ca.pem" | tr -d '\n')

# Create PKCS12 for client certificate (legacy format required for macOS compatibility)
# OpenSSL 3.x uses modern encryption by default, but macOS requires legacy SHA1/RC2
PKCS12_PASSWORD="hocuspocus"
openssl pkcs12 -export -legacy \
    -out "$TEMP_DIR/client.p12" \
    -inkey "$TEMP_DIR/client.key" \
    -in "$TEMP_DIR/client.pem" \
    -certfile "$TEMP_DIR/vpn-ca.pem" \
    -passout pass:$PKCS12_PASSWORD 2>/dev/null

CLIENT_P12_BASE64=$(base64 -i "$TEMP_DIR/client.p12" | tr -d '\n')

# Generate UUIDs for profile
PROFILE_UUID=$(uuidgen)
VPN_UUID=$(uuidgen)
VPN_CA_UUID=$(uuidgen)
CLIENT_CERT_UUID=$(uuidgen)
MITMPROXY_CA_UUID=$(uuidgen)

# Profile output path
PROFILE_PATH="$OUTPUT_DIR/hocuspocus-vpn-macos.mobileconfig"

echo "Generating profile..."

cat > "$PROFILE_PATH" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>PayloadContent</key>
    <array>
        <!-- VPN CA Certificate -->
        <dict>
            <key>PayloadCertificateFileName</key>
            <string>vpn-ca.pem</string>
            <key>PayloadContent</key>
            <data>$VPN_CA_BASE64</data>
            <key>PayloadDescription</key>
            <string>VPN Certificate Authority</string>
            <key>PayloadDisplayName</key>
            <string>Hocuspocus VPN CA</string>
            <key>PayloadIdentifier</key>
            <string>com.hocuspocus.vpn.macos.ca</string>
            <key>PayloadType</key>
            <string>com.apple.security.root</string>
            <key>PayloadUUID</key>
            <string>$VPN_CA_UUID</string>
            <key>PayloadVersion</key>
            <integer>1</integer>
        </dict>

        <!-- Client Certificate (PKCS12) -->
        <dict>
            <key>PayloadCertificateFileName</key>
            <string>client.p12</string>
            <key>PayloadContent</key>
            <data>$CLIENT_P12_BASE64</data>
            <key>PayloadDescription</key>
            <string>VPN Client Certificate</string>
            <key>PayloadDisplayName</key>
            <string>Hocuspocus VPN Client</string>
            <key>PayloadIdentifier</key>
            <string>com.hocuspocus.vpn.macos.client</string>
            <key>PayloadType</key>
            <string>com.apple.security.pkcs12</string>
            <key>PayloadUUID</key>
            <string>$CLIENT_CERT_UUID</string>
            <key>PayloadVersion</key>
            <integer>1</integer>
            <key>Password</key>
            <string>$PKCS12_PASSWORD</string>
        </dict>

        <!-- Mitmproxy CA Certificate -->
        <dict>
            <key>PayloadCertificateFileName</key>
            <string>mitmproxy-ca.pem</string>
            <key>PayloadContent</key>
            <data>$MITMPROXY_CA_BASE64</data>
            <key>PayloadDescription</key>
            <string>Mitmproxy Certificate Authority for HTTPS filtering</string>
            <key>PayloadDisplayName</key>
            <string>Hocuspocus Mitmproxy CA</string>
            <key>PayloadIdentifier</key>
            <string>com.hocuspocus.vpn.macos.mitmproxy</string>
            <key>PayloadType</key>
            <string>com.apple.security.root</string>
            <key>PayloadUUID</key>
            <string>$MITMPROXY_CA_UUID</string>
            <key>PayloadVersion</key>
            <integer>1</integer>
        </dict>

        <!-- IKEv2 VPN Configuration -->
        <dict>
            <key>PayloadDisplayName</key>
            <string>Hocuspocus VPN</string>
            <key>PayloadIdentifier</key>
            <string>com.hocuspocus.vpn.macos.ikev2</string>
            <key>PayloadType</key>
            <string>com.apple.vpn.managed</string>
            <key>PayloadUUID</key>
            <string>$VPN_UUID</string>
            <key>PayloadVersion</key>
            <integer>1</integer>
            <key>UserDefinedName</key>
            <string>Hocuspocus VPN</string>
            <key>VPNType</key>
            <string>IKEv2</string>
            <key>IKEv2</key>
            <dict>
                <key>RemoteAddress</key>
                <string>$VPN_IP</string>
                <key>RemoteIdentifier</key>
                <string>$VPN_IP</string>
                <key>LocalIdentifier</key>
                <string>vpnclient</string>
                <key>AuthenticationMethod</key>
                <string>Certificate</string>
                <key>PayloadCertificateUUID</key>
                <string>$CLIENT_CERT_UUID</string>
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
            <!-- VPN On-Demand: Auto-connect for all traffic -->
            <key>OnDemandEnabled</key>
            <integer>1</integer>
            <key>OnDemandRules</key>
            <array>
                <!-- Always connect -->
                <dict>
                    <key>Action</key>
                    <string>Connect</string>
                </dict>
            </array>
        </dict>
    </array>

    <key>PayloadDescription</key>
    <string>Hocuspocus VPN configuration for macOS with content filtering</string>
    <key>PayloadDisplayName</key>
    <string>Hocuspocus VPN (macOS)</string>
    <key>PayloadIdentifier</key>
    <string>com.hocuspocus.vpn.macos</string>
    <key>PayloadOrganization</key>
    <string>Hocuspocus</string>
    <key>PayloadRemovalDisallowed</key>
    <false/>
    <key>PayloadType</key>
    <string>Configuration</string>
    <key>PayloadUUID</key>
    <string>$PROFILE_UUID</string>
    <key>PayloadVersion</key>
    <integer>1</integer>
</dict>
</plist>
EOF

echo ""
echo "=== macOS VPN Profile Generated ==="
echo "Profile: $PROFILE_PATH"
echo ""
echo "To install:"
echo "  1. Double-click the .mobileconfig file"
echo "  2. Open System Settings > Privacy & Security > Profiles"
echo "  3. Click Install on 'Hocuspocus VPN (macOS)'"
echo "  4. Trust the Mitmproxy CA in Keychain Access:"
echo "     - Open Keychain Access"
echo "     - Find 'mitmproxy' certificate"
echo "     - Double-click > Trust > Always Trust"
echo ""
echo "Or deploy via SimpleMDM:"
echo "  make macos-vpn-profile-mdm"
echo ""
