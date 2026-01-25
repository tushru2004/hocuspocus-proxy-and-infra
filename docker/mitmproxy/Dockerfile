# Mitmproxy transparent proxy container
FROM mitmproxy/mitmproxy:12.2.1

WORKDIR /app

# Copy requirements and install dependencies
COPY docker-requirements.txt /app/
RUN pip install --no-cache-dir -r docker-requirements.txt

# Copy application source code
COPY ./src /app

# Expose mitmproxy port
EXPOSE 8080

ENV PYTHONUNBUFFERED=1
ENV MITMPROXY_CONFDIR=/home/mitmproxy/.mitmproxy

# Default entrypoint - can be overridden in K8s
# SSL passthrough: Only Apple domains (for device functionality) and GKE IPs (for kubectl)
ENTRYPOINT ["mitmdump", \
    "--set", "confdir=/home/mitmproxy/.mitmproxy", \
    "--mode", "transparent", \
    "-s", "/app/proxy_handler.py", \
    "--ignore-hosts", "^(.+\\.)?icloud\\.com(:|$)", \
    "--ignore-hosts", "^(.+\\.)?apple\\.com(:|$)", \
    "--ignore-hosts", "^(.+\\.)?mzstatic\\.com(:|$)", \
    "--ignore-hosts", "^17\\.", \
    "--ignore-hosts", "^.*:6443$", \
    "--ignore-hosts", "^34\\.79\\.45\\.66:443$", \
    "--ignore-hosts", "^35\\.240\\.10\\.96:443$", \
    "--set", "stream_large_bodies=1m", \
    "--set", "ssl_insecure=true", \
    "--listen-host", "0.0.0.0", \
    "--listen-port", "8080"]
