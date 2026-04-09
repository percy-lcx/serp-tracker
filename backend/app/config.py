import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SCREENSHOT_DIR = Path(os.getenv("SCREENSHOT_DIR", "./data/screenshots"))
if not SCREENSHOT_DIR.is_absolute():
    SCREENSHOT_DIR = BASE_DIR / SCREENSHOT_DIR

CRAWL_DELAY_MIN = int(os.getenv("CRAWL_DELAY_MIN_SECONDS", "5"))
CRAWL_DELAY_MAX = int(os.getenv("CRAWL_DELAY_MAX_SECONDS", "15"))
CAPTCHA_TIMEOUT = int(os.getenv("CAPTCHA_TIMEOUT_SECONDS", "600"))
USER_AGENT_LIST_PATH = os.getenv("USER_AGENT_LIST_PATH", "./backend/config/user_agents.txt")
SCREENSHOT_RETENTION_DAYS = int(os.getenv("SCREENSHOT_RETENTION_DAYS", "30"))
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/serp_tracker.db")
AIO_SELECTORS_PATH = Path(os.getenv("AIO_SELECTORS_PATH", str(BASE_DIR / "backend" / "config" / "aio_selectors.json")))
HEADLESS = os.getenv("HEADLESS", "true").lower() in ("true", "1", "yes")
AIO_DEBUG_DUMP = os.getenv("AIO_DEBUG_DUMP", "false").lower() in ("true", "1", "yes")

BROWSER_DATA_DIR = Path(os.getenv("BROWSER_DATA_DIR", "./data/browser_profile"))
if not BROWSER_DATA_DIR.is_absolute():
    BROWSER_DATA_DIR = BASE_DIR / BROWSER_DATA_DIR
