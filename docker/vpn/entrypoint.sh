#!/bin/bash
set -e

echo "Starting StrongSwan VPN setup..."

# Create certificate directories if they don't exist (when using PVC mount)
mkdir -p /etc/ipsec.d/cacerts /etc/ipsec.d/certs /etc/ipsec.d/private
chmod 700 /etc/ipsec.d/private

# GCS bucket for certificate persistence
GCS_BUCKET="${GCS_CERT_BUCKET:-gs://hocuspocus-vpn-vpn-certs/vpn}"

# Device configuration for per-device certificates and fixed IPs
# Format: DEVICE_NAME:FIXED_IP
DEVICES="iphone:10.10.10.10 macbook-air:10.10.10.20"

# Function to download certs from GCS
download_certs_from_gcs() {
    echo "Downloading certificates from GCS..."
    gsutil -q cp "$GCS_BUCKET/cacerts/ca-cert.pem" /etc/ipsec.d/cacerts/ca-cert.pem 2>/dev/null && \
    gsutil -q cp "$GCS_BUCKET/private/ca-key.pem" /etc/ipsec.d/private/ca-key.pem 2>/dev/null && \
    gsutil -q cp "$GCS_BUCKET/certs/server-cert.pem" /etc/ipsec.d/certs/server-cert.pem 2>/dev/null && \
    gsutil -q cp "$GCS_BUCKET/private/server-key.pem" /etc/ipsec.d/private/server-key.pem 2>/dev/null && \
    gsutil -q cp "$GCS_BUCKET/certs/client-cert.pem" /etc/ipsec.d/certs/client-cert.pem 2>/dev/null && \
    gsutil -q cp "$GCS_BUCKET/private/client-key.pem" /etc/ipsec.d/private/client-key.pem 2>/dev/null && \
    gsutil -q cp "$GCS_BUCKET/client.p12" /etc/ipsec.d/client.p12 2>/dev/null
    # Also download per-device certs if they exist
    for device_config in $DEVICES; do
        device_name="${device_config%%:*}"
        gsutil -q cp "$GCS_BUCKET/certs/client-${device_name}-cert.pem" /etc/ipsec.d/certs/client-${device_name}-cert.pem 2>/dev/null || true
        gsutil -q cp "$GCS_BUCKET/private/client-${device_name}-key.pem" /etc/ipsec.d/private/client-${device_name}-key.pem 2>/dev/null || true
        gsutil -q cp "$GCS_BUCKET/client-${device_name}.p12" /etc/ipsec.d/client-${device_name}.p12 2>/dev/null || true
    done
    return $?
}

# Function to upload certs to GCS
upload_certs_to_gcs() {
    echo "Uploading certificates to GCS for persistence..."
    gsutil -q cp /etc/ipsec.d/cacerts/ca-cert.pem "$GCS_BUCKET/cacerts/ca-cert.pem"
    gsutil -q cp /etc/ipsec.d/private/ca-key.pem "$GCS_BUCKET/private/ca-key.pem"
    gsutil -q cp /etc/ipsec.d/certs/server-cert.pem "$GCS_BUCKET/certs/server-cert.pem"
    gsutil -q cp /etc/ipsec.d/private/server-key.pem "$GCS_BUCKET/private/server-key.pem"
    # Legacy shared client cert (for backwards compatibility)
    gsutil -q cp /etc/ipsec.d/certs/client-cert.pem "$GCS_BUCKET/certs/client-cert.pem" 2>/dev/null || true
    gsutil -q cp /etc/ipsec.d/private/client-key.pem "$GCS_BUCKET/private/client-key.pem" 2>/dev/null || true
    gsutil -q cp /etc/ipsec.d/client.p12 "$GCS_BUCKET/client.p12" 2>/dev/null || true
    # Per-device certificates
    for device_config in $DEVICES; do
        device_name="${device_config%%:*}"
        gsutil -q cp /etc/ipsec.d/certs/client-${device_name}-cert.pem "$GCS_BUCKET/certs/client-${device_name}-cert.pem" 2>/dev/null || true
        gsutil -q cp /etc/ipsec.d/private/client-${device_name}-key.pem "$GCS_BUCKET/private/client-${device_name}-key.pem" 2>/dev/null || true
        gsutil -q cp /etc/ipsec.d/client-${device_name}.p12 "$GCS_BUCKET/client-${device_name}.p12" 2>/dev/null || true
    done
    echo "Certificates uploaded to GCS successfully"
}

# Function to generate a client certificate for a specific device
generate_device_cert() {
    local device_name="$1"
    echo "Generating client certificate for device: $device_name"

    ipsec pki --gen --type rsa --size 4096 --outform pem > /etc/ipsec.d/private/client-${device_name}-key.pem
    ipsec pki --pub --in /etc/ipsec.d/private/client-${device_name}-key.pem --type rsa | \
        ipsec pki --issue --lifetime 1825 --cacert /etc/ipsec.d/cacerts/ca-cert.pem \
        --cakey /etc/ipsec.d/private/ca-key.pem --dn "CN=${device_name}" \
        --san "${device_name}" --flag clientAuth \
        --outform pem > /etc/ipsec.d/certs/client-${device_name}-cert.pem

    openssl pkcs12 -export -inkey /etc/ipsec.d/private/client-${device_name}-key.pem \
        -in /etc/ipsec.d/certs/client-${device_name}-cert.pem \
        -certfile /etc/ipsec.d/cacerts/ca-cert.pem \
        -name "Hocuspocus VPN Client (${device_name})" \
        -out /etc/ipsec.d/client-${device_name}.p12 \
        -passout pass:hocuspocus

    echo "Certificate generated for $device_name"
}

# Get server IP from environment or metadata
SERVER_IP="${VPN_SERVER_IP:-}"
if [ -z "$SERVER_IP" ]; then
    echo "VPN_SERVER_IP not set, attempting to detect..."
    # Try OCI metadata (for OKE)
    SERVER_IP=$(curl -sf -H "Authorization: Bearer Oracle" http://169.254.169.254/opc/v2/vnics/ 2>/dev/null | jq -r '.[0].publicIp // empty' || true)
    # Fallback to external IP detection
    if [ -z "$SERVER_IP" ]; then
        SERVER_IP=$(curl -sf https://api.ipify.org 2>/dev/null || echo "")
    fi
fi

if [ -z "$SERVER_IP" ]; then
    echo "ERROR: Could not determine server public IP"
    exit 1
fi

echo "Server IP: $SERVER_IP"

# Check if certificates already exist locally (mounted from PVC)
if [ -f /etc/ipsec.d/private/server-key.pem ]; then
    echo "Using existing certificates from mounted volume"

    # Generate per-device certs if they don't exist (upgrade from shared cert)
    GENERATED_NEW_CERTS=false
    for device_config in $DEVICES; do
        device_name="${device_config%%:*}"
        if [ ! -f /etc/ipsec.d/private/client-${device_name}-key.pem ]; then
            echo "Generating certificate for device: $device_name (upgrade)"
            generate_device_cert "$device_name"
            GENERATED_NEW_CERTS=true
        fi
    done
    if [ "$GENERATED_NEW_CERTS" = true ]; then
        upload_certs_to_gcs || echo "Warning: Failed to upload to GCS (non-fatal)"
    fi

# Try to download from GCS first
elif download_certs_from_gcs; then
    echo "Successfully restored certificates from GCS"
    chmod 600 /etc/ipsec.d/private/*.pem

    # Generate per-device certs if they don't exist
    GENERATED_NEW_CERTS=false
    for device_config in $DEVICES; do
        device_name="${device_config%%:*}"
        if [ ! -f /etc/ipsec.d/private/client-${device_name}-key.pem ]; then
            echo "Generating certificate for device: $device_name"
            generate_device_cert "$device_name"
            GENERATED_NEW_CERTS=true
        fi
    done
    if [ "$GENERATED_NEW_CERTS" = true ]; then
        upload_certs_to_gcs || echo "Warning: Failed to upload to GCS (non-fatal)"
    fi

else
    # Generate new certificates
    echo "Generating new certificates..."

    # Generate CA certificate
    ipsec pki --gen --type rsa --size 4096 --outform pem > /etc/ipsec.d/private/ca-key.pem
    ipsec pki --self --ca --lifetime 3650 --in /etc/ipsec.d/private/ca-key.pem \
        --type rsa --dn "CN=Hocuspocus VPN CA" --outform pem > /etc/ipsec.d/cacerts/ca-cert.pem

    # Generate server certificate
    ipsec pki --gen --type rsa --size 4096 --outform pem > /etc/ipsec.d/private/server-key.pem
    ipsec pki --pub --in /etc/ipsec.d/private/server-key.pem --type rsa | \
        ipsec pki --issue --lifetime 1825 --cacert /etc/ipsec.d/cacerts/ca-cert.pem \
        --cakey /etc/ipsec.d/private/ca-key.pem --dn "CN=$SERVER_IP" --san="$SERVER_IP" \
        --flag serverAuth --flag ikeIntermediate --outform pem > /etc/ipsec.d/certs/server-cert.pem

    # Generate per-device client certificates
    echo "Generating per-device client certificates..."
    for device_config in $DEVICES; do
        device_name="${device_config%%:*}"
        generate_device_cert "$device_name"
    done

    # Also generate legacy shared cert for backwards compatibility
    echo "Generating legacy shared client certificate..."
    ipsec pki --gen --type rsa --size 4096 --outform pem > /etc/ipsec.d/private/client-key.pem
    ipsec pki --pub --in /etc/ipsec.d/private/client-key.pem --type rsa | \
        ipsec pki --issue --lifetime 1825 --cacert /etc/ipsec.d/cacerts/ca-cert.pem \
        --cakey /etc/ipsec.d/private/ca-key.pem --dn "CN=vpnclient" \
        --san "vpnclient" --flag clientAuth \
        --outform pem > /etc/ipsec.d/certs/client-cert.pem

    openssl pkcs12 -export -inkey /etc/ipsec.d/private/client-key.pem \
        -in /etc/ipsec.d/certs/client-cert.pem \
        -certfile /etc/ipsec.d/cacerts/ca-cert.pem \
        -name "Hocuspocus VPN Client" \
        -out /etc/ipsec.d/client.p12 \
        -passout pass:hocuspocus

    echo "Certificates generated successfully"

    # Upload to GCS for persistence
    upload_certs_to_gcs
fi

# Configure IPsec with certificate-based authentication and per-device fixed IPs
cat > /etc/ipsec.conf <<EOF
config setup
    charondebug="ike 4, knl 1, cfg 2, net 1, enc 1, lib 1"
    uniqueids=no

# Default connection for unknown clients (fallback)
conn ikev2-vpn
    auto=add
    compress=no
    type=tunnel
    keyexchange=ikev2
    fragmentation=yes
    forceencaps=yes
    dpdaction=clear
    dpddelay=300s
    rekey=no
    left=%any
    leftid=$SERVER_IP
    leftauth=pubkey
    leftcert=server-cert.pem
    leftsendcert=always
    leftsubnet=0.0.0.0/0
    right=%any
    rightid=%any
    rightauth=pubkey
    rightca="CN=Hocuspocus VPN CA"
    rightsourceip=10.10.10.0/24
    rightdns=8.8.8.8,8.8.4.4
    ike=aes256-sha256-modp2048,aes256-sha1-modp2048,3des-sha1-modp2048!
    esp=aes256-sha256,aes256-sha1,3des-sha1!
EOF

# Add per-device connections with fixed IPs
for device_config in $DEVICES; do
    device_name="${device_config%%:*}"
    device_ip="${device_config##*:}"
    echo "Adding connection for device: $device_name with fixed IP: $device_ip"

    cat >> /etc/ipsec.conf <<EOF

# Connection for $device_name - fixed IP $device_ip
conn ikev2-$device_name
    auto=add
    compress=no
    type=tunnel
    keyexchange=ikev2
    fragmentation=yes
    forceencaps=yes
    dpdaction=clear
    dpddelay=300s
    rekey=no
    left=%any
    leftid=$SERVER_IP
    leftauth=pubkey
    leftcert=server-cert.pem
    leftsendcert=always
    leftsubnet=0.0.0.0/0
    right=%any
    rightid=$device_name
    rightauth=pubkey
    rightca="CN=Hocuspocus VPN CA"
    rightsourceip=$device_ip
    rightdns=8.8.8.8,8.8.4.4
    ike=aes256-sha256-modp2048,aes256-sha1-modp2048,3des-sha1-modp2048!
    esp=aes256-sha256,aes256-sha1,3des-sha1!
EOF
done

echo "IPsec configuration generated with per-device connections"

# Configure secrets for certificate auth
cat > /etc/ipsec.secrets <<EOF
: RSA "server-key.pem"
EOF

chmod 600 /etc/ipsec.secrets

# Setup iptables for NAT (if running with NET_ADMIN capability)
if [ "$SETUP_IPTABLES" = "true" ]; then
    echo "Setting up iptables rules..."

    # Enable IP forwarding
    echo 1 > /proc/sys/net/ipv4/ip_forward

    # Get default interface
    IFACE=$(ip route get 8.8.8.8 | grep -oP 'dev \K\S+')

    # NAT rules
    iptables -t nat -A POSTROUTING -s 10.10.10.0/24 -o $IFACE -j MASQUERADE
    iptables -A FORWARD -m state --state RELATED,ESTABLISHED -j ACCEPT
    iptables -A FORWARD -s 10.10.10.0/24 -j ACCEPT

    # Redirect HTTP/HTTPS to mitmproxy (if MITMPROXY_HOST is set)
    if [ -n "$MITMPROXY_HOST" ]; then
        MITMPROXY_PORT="${MITMPROXY_PORT:-8080}"
        echo "Redirecting traffic to mitmproxy at $MITMPROXY_HOST:$MITMPROXY_PORT"
        iptables -t nat -A PREROUTING -s 10.10.10.0/24 -p tcp --dport 80 -j DNAT --to-destination $MITMPROXY_HOST:$MITMPROXY_PORT
        iptables -t nat -A PREROUTING -s 10.10.10.0/24 -p tcp --dport 443 -j DNAT --to-destination $MITMPROXY_HOST:$MITMPROXY_PORT
        # Block QUIC to force HTTPS
        iptables -I FORWARD -p udp --dport 443 -s 10.10.10.0/24 -j REJECT
    fi
fi

echo "Starting StrongSwan..."
exec ipsec start --nofork
