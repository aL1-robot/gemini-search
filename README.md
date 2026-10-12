# Self-hosted AI Search Engine

This project turns Gemini into a simple self-hosted AI search endpoint.

It runs a FastAPI service that opens a real Chromium browser, signs in to Google Gemini, submits a search-style question, and returns the generated answer as an HTTP response. The goal is to provide a lightweight, locally hosted search layer for AI models without needing a separate paid API or a complex backend.

This is useful when you want:

- a private, self-hosted AI search endpoint
- a browser-backed Gemini workflow in Docker
- a simple API that can be called from other tools or apps
- a local search service that keeps a persistent browser session and login state

## How it works

- The app starts a persistent Chromium profile
- It logs into Gemini once and reuses the same session
- Each request goes to `/search?q=...`
- The app fills the Gemini prompt box, submits the query, waits for a stable response, and returns the final text
- The service is intentionally small and easy to self-host

## Prerequisites

- Docker and Docker Compose
- Python 3.11+ if you want to run it locally
- A Google account with access to Gemini

## Quick start with Docker

1. Build and run the service:

   ```bash
   docker compose up --build -d
   ```

2. Perform the one-time Google login flow:

   ```bash
   docker compose run --rm -e MODE=login gemini-search
   ```

   This opens a browser in a virtual display. In your browser, visit:

   - http://127.0.0.1:6080/vnc.html

   Sign in to Google and open https://gemini.google.com/app to confirm the session is working. Then close the browser.

   The Chromium profile is stored in a Docker volume, so the login is reused next time.

3. Start the app normally:

   ```bash
   docker compose up -d
   ```

4. Query the service:

   - http://127.0.0.1:8001/search?q=your+question
   - http://127.0.0.1:8001/health

## Local development

If you want to run it directly on your workstation instead of Docker:

```bash
uv venv
source .venv/bin/activate
uv pip install playwright fastapi "uvicorn[standard]"
playwright install --with-deps chromium
```

Then start the server:

```bash
Xvfb :99 -screen 0 1280x900x24 -nolisten tcp &
uvicorn app:app --host 0.0.0.0 --port 8001
```

In a local environment, the app expects a display and a persistent profile directory. By default it uses `/data/profile`, so make sure that path exists and Chromium has permission to launch with a saved browser state.

## Using the API

### Search endpoint

```bash
curl "http://127.0.0.1:8001/search?q=What%20is%20the%20capital%20of%20France%3F"
```

### Example response

```json
{
  "query": "What is the capital of France?",
  "answer": "Paris.",
  "timings_ms": {
    "page_ready": 123,
    "submitted": 456,
    "first_text": 2000,
    "done": 2600
  }
}
```

### Health check

```bash
curl http://127.0.0.1:8001/health
```

## Environment variables

You can tune the behavior of the AI search service with these variables:

- `ASK_TIMEOUT` — maximum wait for a response from Gemini (default: `40` seconds)
- `PROMPT_PREFIX` — text added before each question (default: `Search the web and answer in one or two short sentences: `)
- `STABLE_SECS` — how long the answer must stay unchanged before it is treated as stable (default: `1.2`)
- `BLOCK_ASSETS` — blocks image, font, and media requests to speed up the page (default: `1`)

## Self-hosting notes

- This project is a self-hosted AI search wrapper, not a fully general web search crawler.
- It relies on the Gemini web UI and a real browser session.
- If Google changes the page layout or selectors, the scraper may need updates in `app.py`.
- The app enforces single-request access at a time using an async lock, which helps avoid browser race conditions.
- This is best for simple local deployments, internal tools, and lightweight AI-assisted search workflows.
