"""
E.V. — Browser Tools
Web search via DuckDuckGo Lite, page visits via Playwright, URL opening.
"""

import re
import webbrowser
from urllib.parse import quote, unquote, parse_qs, urlparse
import httpx
from playwright.async_api import async_playwright

_browser = None
_context = None


async def _get_browser():
    global _browser, _context
    if _browser is None:
        pw = await async_playwright().start()
        # Headless: web search / page reads happen in the background, invisible to
        # the user. Opening pages for the user to *see* uses their default browser
        # (webbrowser.open) instead.
        _browser = await pw.chromium.launch(headless=True)
        _context = await _browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        )
    return _context


async def search_and_read(query: str) -> dict:
    """Search DuckDuckGo (headless), click the first result, read the page."""
    ctx = await _get_browser()
    page = await ctx.new_page()
    try:
        # DuckDuckGo search (no cookie banner, no reCAPTCHA). Encode the query so
        # spaces / & / # / Turkish characters don't corrupt the URL.
        search_url = f"https://duckduckgo.com/?q={quote(query)}"
        await page.goto(search_url, timeout=15000)
        await page.wait_for_timeout(1500)

        # Click first organic result
        first_link = page.locator('[data-testid="result-title-a"]').first
        if await first_link.count() > 0:
            await first_link.click()
            await page.wait_for_timeout(3000)

            # Read page content
            title = await page.title()
            url = page.url
            text = await page.evaluate("""
                () => {
                    const selectors = ['main', 'article', '[role="main"]', '.content', '#content', 'body'];
                    for (const sel of selectors) {
                        const el = document.querySelector(sel);
                        if (el && el.innerText.trim().length > 100) {
                            return el.innerText.trim();
                        }
                    }
                    return document.body?.innerText?.trim() || '';
                }
            """)
            return {"title": title, "url": url, "content": text[:3000]}
        else:
            return {"title": "No results", "url": search_url, "content": "No results found."}
    except Exception as e:
        return {"error": str(e), "url": query}
    finally:
        await page.close()


async def visit(url: str, max_chars: int = 5000) -> dict:
    """Visit a URL and extract main text content."""
    ctx = await _get_browser()
    page = await ctx.new_page()
    try:
        await page.goto(url, timeout=15000, wait_until="domcontentloaded")
        text = await page.evaluate("""
            () => {
                const selectors = ['main', 'article', '[role="main"]', '.content', '#content', 'body'];
                for (const sel of selectors) {
                    const el = document.querySelector(sel);
                    if (el && el.innerText.trim().length > 100) {
                        return el.innerText.trim();
                    }
                }
                return document.body?.innerText?.trim() || '';
            }
        """)
        title = await page.title()
        return {"title": title, "url": url, "content": text[:max_chars]}
    except Exception as e:
        return {"error": str(e), "url": url}
    finally:
        await page.close()


async def fetch_news() -> str:
    """Fetch current world news from worldmonitor.app (headless)."""
    ctx = await _get_browser()
    page = await ctx.new_page()
    try:
        await page.goto("https://www.worldmonitor.app/", timeout=20000)
        await page.wait_for_timeout(6000)  # Wait for JS to render
        text = await page.evaluate("() => document.body.innerText")
        # Extract the news sections
        content = text[:4000]
        return f"World Monitor news:\n{content}"
    except Exception as e:
        return f"Couldn't load the news: {e}"
    finally:
        await page.close()


async def youtube_open(query: str) -> dict:
    """Open the first YouTube video for `query` directly in the default browser.

    Fetches the results HTML and pulls the first videoId (no browser automation,
    fast + reliable), then opens the watch URL so it actually plays. Falls back
    to the search page if parsing fails.
    """
    from urllib.parse import quote
    q = (query or "").strip()
    if not q:
        return {"error": "empty query"}
    search_url = f"https://www.youtube.com/results?search_query={quote(q)}"
    try:
        async with httpx.AsyncClient(timeout=10, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Accept-Language": "tr,en;q=0.8",
        }) as c:
            r = await c.get(search_url)
        m = re.search(r'"videoId":"([\w-]{11})"', r.text)
        target = f"https://www.youtube.com/watch?v={m.group(1)}" if m else search_url
    except Exception:
        target = search_url
    webbrowser.open(target)
    return {"query": q, "url": target, "played": target != search_url}


async def open_url(url: str):
    """Open URL in user's default browser (non-blocking)."""
    import asyncio
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, webbrowser.open, url)
    return {"success": True, "url": url}


async def close():
    global _browser, _context
    if _browser:
        await _browser.close()
        _browser = None
        _context = None
