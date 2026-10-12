import asyncio
import os
import time

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from playwright.async_api import async_playwright

PROFILE = "/data/profile"
TIMEOUT = int(os.getenv("ASK_TIMEOUT", "40"))
PROMPT_PREFIX = os.getenv(
    "PROMPT_PREFIX", "Search the web and answer in 2 short sentences: "
)

# Selectors are the fragile part: Google changes them. If asking fails,
# open /debug.png, then inspect the page in noVNC and adjust these.
INPUT_SEL = 'rich-textarea div[contenteditable="true"]'
RESPONSE_SEL = "message-content"

app = FastAPI()
lock = asyncio.Lock()  # one question at a time: there is one browser tab
state = {}


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
    state["page"] = ctx.pages[0] if ctx.pages else await ctx.new_page()
    await state["page"].goto("https://gemini.google.com/app")


@app.on_event("shutdown")
async def shutdown():
    await state["ctx"].close()
    await state["pw"].stop()


async def ask_gemini(question: str) -> str:
    page = state["page"]
    await page.goto("https://gemini.google.com/app")  # fresh chat every time
    box = page.locator(INPUT_SEL).first
    try:
        await box.wait_for(timeout=15000)
    except Exception:
        raise HTTPException(503, "Input box not found: not logged in, or Google changed the UI")
    await box.click()
    await box.fill(PROMPT_PREFIX + question)
    await page.keyboard.press("Enter")

    resp = page.locator(RESPONSE_SEL).last
    try:
        await resp.wait_for(timeout=TIMEOUT * 1000)
    except Exception:
        raise HTTPException(504, "No response in time")

    # The answer streams in: wait until the text stops changing
    last, stable_since, deadline = "", time.time(), time.time() + TIMEOUT
    while time.time() < deadline:
        txt = (await resp.inner_text()).strip()
        if txt != last:
            last, stable_since = txt, time.time()
        elif txt and time.time() - stable_since > 2:
            return txt
        await asyncio.sleep(0.3)
    return last


@app.get("/search")
async def search(q: str):
    async with lock:
        return {"query": q, "answer": await ask_gemini(q)}


@app.get("/health")
async def health():
    return {"ok": True, "url": state["page"].url}


@app.get("/debug.png")
async def debug():
    png = await state["page"].screenshot()
    return Response(content=png, media_type="image/png")