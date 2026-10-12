import asyncio
import os
import time

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from playwright.async_api import async_playwright

PROFILE = "/data/profile"
TIMEOUT = int(os.getenv("ASK_TIMEOUT", "40"))
# Shorter answers = faster generation. Tune this for your assistant.
PROMPT_PREFIX = os.getenv(
    "PROMPT_PREFIX", "Search the web and answer in one or two short sentences: "
)
# How long the answer text must stay unchanged before we call it finished.
# Lower = faster, but risks cutting off if Gemini pauses mid-answer.
STABLE_SECS = float(os.getenv("STABLE_SECS", "1.2"))
# Skip images/fonts/media: Gemini works fine without them and loads faster.
BLOCK_ASSETS = os.getenv("BLOCK_ASSETS", "1") == "1"

# Selectors are the fragile part: Google changes them.
INPUT_SEL = 'rich-textarea div[contenteditable="true"]'
RESPONSE_SEL = "message-content"
GEMINI_URL = "https://gemini.google.com/app"

app = FastAPI()
lock = asyncio.Lock()  # one question at a time: there is one browser tab
state = {"fresh": False}


async def block_heavy(route):
    if route.request.resource_type in ("image", "media", "font"):
        await route.abort()
    else:
        await route.continue_()


async def load_fresh_chat():
    """Open a new empty chat and wait until the input box is ready."""
    page = state["page"]
    await page.goto(GEMINI_URL, wait_until="domcontentloaded")
    await page.locator(INPUT_SEL).first.wait_for(timeout=15000)
    state["fresh"] = True


async def prewarm():
    """After answering, get the next chat ready in the background."""
    async with lock:
        if state["fresh"]:
            return
        try:
            await load_fresh_chat()
        except Exception:
            state["fresh"] = False


@app.on_event("startup")
async def startup():
    state["pw"] = await async_playwright().start()
    state["ctx"] = await state["pw"].chromium.launch_persistent_context(
        PROFILE,
        headless=False,  # runs on the virtual display from entrypoint.sh
        no_viewport=True,
        args=[
            "--password-store=basic",  # must match login mode so cookies decrypt
            "--disable-blink-features=AutomationControlled",
            "--window-size=1280,900",
        ],
        ignore_default_args=["--enable-automation"],
    )
    ctx = state["ctx"]
    if BLOCK_ASSETS:
        await ctx.route("**/*", block_heavy)
    state["page"] = ctx.pages[0] if ctx.pages else await ctx.new_page()
    try:
        await load_fresh_chat()
    except Exception:
        state["fresh"] = False


@app.on_event("shutdown")
async def shutdown():
    await state["ctx"].close()
    await state["pw"].stop()


async def ask_gemini(question: str) -> dict:
    page = state["page"]
    t0 = time.time()
    ms = lambda: int((time.time() - t0) * 1000)
    timings = {}

    if not state["fresh"]:
        try:
            await load_fresh_chat()
        except Exception:
            raise HTTPException(
                503, "Input box not found: not logged in, or Google changed the UI"
            )
    state["fresh"] = False  # this chat is about to be used
    timings["page_ready"] = ms()

    box = page.locator(INPUT_SEL).first
    await box.click()
    await box.fill(PROMPT_PREFIX + question)
    await page.keyboard.press("Enter")
    timings["submitted"] = ms()

    resp = page.locator(RESPONSE_SEL).last
    try:
        await resp.wait_for(timeout=TIMEOUT * 1000)
    except Exception:
        raise HTTPException(504, "No response in time")
    timings["first_text"] = ms()

    # The answer streams in: wait until the text stops changing
    last, stable_since, deadline = "", time.time(), time.time() + TIMEOUT
    while time.time() < deadline:
        txt = (await resp.inner_text()).strip()
        if txt != last:
            last, stable_since = txt, time.time()
        elif txt and time.time() - stable_since > STABLE_SECS:
            break
        await asyncio.sleep(0.15)
    timings["done"] = ms()
    return {"answer": last, "timings_ms": timings}


@app.get("/search")
async def search(q: str):
    async with lock:
        result = await ask_gemini(q)
    asyncio.create_task(prewarm())  # get the next chat ready while the caller speaks
    return {"query": q, **result}


@app.get("/health")
async def health():
    return {"ok": True, "url": state["page"].url, "fresh": state["fresh"]}


@app.get("/debug.png")
async def debug():
    png = await state["page"].screenshot()
    return Response(content=png, media_type="image/png")