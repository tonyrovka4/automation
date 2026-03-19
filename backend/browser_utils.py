import random
import asyncio
from typing import Optional
from backend.config import settings

# A list of modern user agents
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:130.0) Gecko/20100101 Firefox/130.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:130.0) Gecko/20100101 Firefox/130.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15"
]

def get_random_user_agent() -> str:
    return random.choice(USER_AGENTS)

def get_stealth_headers() -> dict:
    """Returns typical headers to mimic a real browser request."""
    return {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1"
    }

def get_random_proxy() -> Optional[dict]:
    """Returns a proxy dict for Playwright if configured, else None."""
    if not settings.PROXY_LIST:
        return None
    proxies = [p.strip() for p in settings.PROXY_LIST.split(",") if p.strip()]
    if not proxies:
        return None
    
    proxy_url = random.choice(proxies)
    return {"server": proxy_url}

async def human_delay(min_ms: int = 500, max_ms: int = 2500):
    """Sleep for a random amount of time between min_ms and max_ms."""
    delay = random.uniform(min_ms / 1000.0, max_ms / 1000.0)
    await asyncio.sleep(delay)

async def human_type(page, locator, text: str, delay_min: int = 30, delay_max: int = 150):
    """Types text character by character with random delays."""
    await locator.fill("") # Clear input first
    for char in text:
        await locator.type(char, delay=random.randint(delay_min, delay_max))

async def random_mouse_move(page):
    """Moves the mouse around randomly to look more human."""
    try:
        viewport = page.viewport_size
        if not viewport:
            viewport = {"width": 1280, "height": 720}
            
        x = random.randint(100, viewport["width"] - 100)
        y = random.randint(100, viewport["height"] - 100)
        steps = random.randint(5, 15)
        
        await page.mouse.move(x, y, steps=steps)
    except Exception as e:
        print(f"[STEALTH] Failed to move mouse: {e}")
