# StrongSwan IKEv2 VPN container
# Based on Alpine for minimal footprint
FROM alpine:3.19

RUN apk add --no-cache \
    strongswan \
    iptables \
    ip6tables \
    bash \
    curl \
    jq \
    openssl

# Create directories for certificates
RUN mkdir -p /etc/ipsec.d/cacerts \
             /etc/ipsec.d/certs \
             /etc/ipsec.d/private \
    && chmod 700 /etc/ipsec.d/private

# Copy entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Expose IKEv2 ports
EXPOSE 500/udp 4500/udp

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD ipsec status || exit 1

ENTRYPOINT ["/entrypoint.sh"]
