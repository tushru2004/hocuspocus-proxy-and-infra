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
ENTRYPOINT ["mitmdump", \
    "--set", "confdir=/home/mitmproxy/.mitmproxy", \
    "--mode", "transparent", \
    "-s", "/app/proxy_handler.py", \
    "--ignore-hosts", "^(.+\\.)?icloud\\.com:443$", \
    "--ignore-hosts", "^(.+\\.)?apple\\.com:443$", \
    "--ignore-hosts", "^(.+\\.)?mzstatic\\.com:443$", \
    "--ignore-hosts", "^(.+\\.)?googleapis\\.com:443$", \
    "--ignore-hosts", "^(.+\\.)?anthropic\\.com:443$", \
    "--ignore-hosts", "^(.+\\.)?claude\\.ai:443$", \
    "--ignore-hosts", "^(.+\\.)?statsig\\.com:443$", \
    "--ignore-hosts", "^(.+\\.)?sentry\\.io:443$", \
    "--ignore-hosts", "^(.+\\.)?github\\.com:443$", \
    "--ignore-hosts", "^(.+\\.)?githubusercontent\\.com:443$", \
    "--ignore-hosts", "^(.+\\.)?githubassets\\.com:443$", \
    "--ignore-hosts", "^(.+\\.)?npmjs\\.org:443$", \
    "--ignore-hosts", "^(.+\\.)?npmjs\\.com:443$", \
    "--ignore-hosts", "^(.+\\.)?pypi\\.org:443$", \
    "--ignore-hosts", "^(.+\\.)?pythonhosted\\.org:443$", \
    "--ignore-hosts", "^(.+\\.)?docker\\.io:443$", \
    "--ignore-hosts", "^(.+\\.)?docker\\.com:443$", \
    "--ignore-hosts", "^(.+\\.)?simplemdm\\.com:443$", \
    "--ignore-hosts", "^(.+\\.)?microsoft\\.com:443$", \
    "--ignore-hosts", "^(.+\\.)?microsoftonline\\.com:443$", \
    "--ignore-hosts", "^(.+\\.)?azure\\.com:443$", \
    "--ignore-hosts", "^(.+\\.)?windows\\.net:443$", \
    "--ignore-hosts", "^(.+\\.)?vscode-cdn\\.net:443$", \
    "--ignore-hosts", "^(.+\\.)?lastpass\\.com:443$", \
    "--ignore-hosts", "^(.+\\.)?lastpass\\.eu:443$", \
    "--ignore-hosts", "^.*:6443$", \
    "--ignore-hosts", "^34\\.79\\.45\\.66:443$", \
    "--ignore-hosts", "^35\\.240\\.10\\.96:443$", \
    "--set", "stream_large_bodies=1m", \
    "--set", "ssl_insecure=true", \
    "--listen-host", "0.0.0.0", \
    "--listen-port", "8080"]
