#!/bin/bash
set -e

echo "Starting StrongSwan VPN setup..."

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

# Check if certificates already exist (mounted from PVC)
if [ ! -f /etc/ipsec.d/private/server-key.pem ]; then
    echo "Generating certificates..."

    # Generate CA certificate
    ipsec pki --gen --type rsa --size 4096 --outform pem > /etc/ipsec.d/private/ca-key.pem
    ipsec pki --self --ca --lifetime 3650 --in /etc/ipsec.d/private/ca-key.pem \
        --type rsa --dn "CN=VPN CA" --outform pem > /etc/ipsec.d/cacerts/ca-cert.pem

    # Generate server certificate
    ipsec pki --gen --type rsa --size 4096 --outform pem > /etc/ipsec.d/private/server-key.pem
    ipsec pki --pub --in /etc/ipsec.d/private/server-key.pem --type rsa | \
        ipsec pki --issue --lifetime 1825 --cacert /etc/ipsec.d/cacerts/ca-cert.pem \
        --cakey /etc/ipsec.d/private/ca-key.pem --dn "CN=$SERVER_IP" --san="$SERVER_IP" \
        --flag serverAuth --flag ikeIntermediate --outform pem > /etc/ipsec.d/certs/server-cert.pem

    echo "Certificates generated successfully"
else
    echo "Using existing certificates from mounted volume"
fi

# Configure IPsec
cat > /etc/ipsec.conf <<EOF
config setup
    charondebug="ike 1, knl 1, cfg 0"
    uniqueids=no

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
    leftcert=server-cert.pem
    leftsendcert=always
    leftsubnet=0.0.0.0/0
    right=%any
    rightid=%any
    rightauth=eap-mschapv2
    rightsourceip=10.10.10.0/24
    rightdns=8.8.8.8,8.8.4.4
    rightsendcert=never
    eap_identity=%identity
    ike=aes256-sha256-modp2048,aes256-sha1-modp2048,3des-sha1-modp2048!
    esp=aes256-sha256,aes256-sha1,3des-sha1!
EOF

# Configure VPN credentials from environment
VPN_USER="${VPN_USERNAME:-vpnuser}"
VPN_PASS="${VPN_PASSWORD:-changeme}"

cat > /etc/ipsec.secrets <<EOF
: RSA "server-key.pem"
$VPN_USER : EAP "$VPN_PASS"
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
