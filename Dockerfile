# Official Playwright image: ships Chromium + system libs (the Python package is installed below).
# Multi-arch, so the same file builds on x86 (laptop) and arm64 (Orange Pi etc.).
FROM mcr.microsoft.com/playwright/python:v1.49.1-noble

ENV DEBIAN_FRONTEND=noninteractive \
    DISPLAY=:99 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        xvfb x11vnc novnc websockify fluxbox \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir --ignore-installed typing_extensions playwright==1.49.1 fastapi "uvicorn[standard]"

WORKDIR /app
COPY app.py entrypoint.sh /app/
RUN chmod +x /app/entrypoint.sh

EXPOSE 8001 6080
ENTRYPOINT ["/app/entrypoint.sh"]