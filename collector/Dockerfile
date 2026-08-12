# Runs the collector's browser headed (no --headless flag) against a
# virtual X display (Xvfb), not truly headless. Confirmed 2026-08-11 that
# Cloudflare's bot check specifically detects Chrome's --headless flag, not
# "no physical monitor attached" - Xvfb gives Chrome a real X server to talk
# to, so it never sets that flag. Same category of trick as the Windows
# virtual-desktop approach in README.md, just the Linux/container version.
#
# Build from the REPO ROOT (needs both collector/ and data/ in context):
#   docker build -f collector/Dockerfile -t modeldrift-collector .
# Not from collector/ itself - see docker-compose.yml for the normal path in.
FROM python:3.11-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
        xvfb wget gnupg ca-certificates \
    && wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" \
        > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update && apt-get install -y --no-install-recommends google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY collector/requirements.txt collector/requirements.txt
RUN pip install --no-cache-dir -r collector/requirements.txt

# CHROME_EXECUTABLE_PATH (read by collect_v0.py) pins the real Google Chrome
# just installed above, matching what browser_use auto-detects on Windows -
# explicit here instead of relying on the same auto-detection working
# identically on a minimal Linux image with no Playwright bundled browser.
ENV CHROME_EXECUTABLE_PATH=/usr/bin/google-chrome-stable

COPY collector/ collector/
COPY data/ data/
RUN chmod +x collector/docker-entrypoint.sh

WORKDIR /app/collector
ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["python", "collect_v0.py", "--dry-run", "--max-calls", "1"]
