import json
import os
import threading
from dataclasses import dataclass

_config_loaded = False
_state_lock = threading.Lock()
_categories_lock = threading.Lock()


@dataclass
class Config:
    PUID: str = os.environ.get("PUID", "501")
    PGID: str = os.environ.get("PGID", "20")
    TZ: str = os.environ.get("TZ", "UTC")

    AUTOSTRM_BIND: str = os.environ.get("AUTOSTRM_BIND", "0.0.0.0")
    AUTOSTRM_PORT: str = os.environ.get("AUTOSTRM_PORT", "6500")

    AUTH_USERNAME: str = os.environ.get("AUTH_USERNAME", "autostrm")
    AUTH_PASSWORD: str = os.environ.get("AUTH_PASSWORD", "autostrm")

    TORBOX_BASE_URL: str = os.environ.get("TORBOX_BASE_URL", "https://api.torbox.example")
    TORBOX_API_KEY: str = os.environ.get("TORBOX_API_KEY", "")

    MEDIA_TV_PATH: str = os.environ.get("MEDIA_TV_PATH", "/data/media/tv")
    MEDIA_MOVIES_PATH: str = os.environ.get("MEDIA_MOVIES_PATH", "/data/media/movies")

    CATEGORY_TV: str = os.environ.get("CATEGORY_TV", "tv")
    CATEGORY_MOVIES: str = os.environ.get("CATEGORY_MOVIES", "movies")

    LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "info")

    @property
    def puid(self) -> int:
        try:
            return int(self.PUID)
        except Exception:
            return 501

    @property
    def pgid(self) -> int:
        try:
            return int(self.PGID)
        except Exception:
            return 20


cfg = Config()

CONFIG_DIR = os.environ.get("CONFIG_DIR", "/config")
STATE_FILE = os.path.join(CONFIG_DIR, "state.json")
CATEGORIES_FILE = os.path.join(CONFIG_DIR, "categories.json")


def load_config():
    global _config_loaded
    if _config_loaded:
        return
    os.makedirs(CONFIG_DIR, exist_ok=True)
    # initialize files if not present
    if not os.path.exists(STATE_FILE):
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({"jobs": {}}, f)
    if not os.path.exists(CATEGORIES_FILE):
        with open(CATEGORIES_FILE, "w", encoding="utf-8") as f:
            json.dump({cfg.CATEGORY_TV: {"savePath": cfg.MEDIA_TV_PATH},
                       cfg.CATEGORY_MOVIES: {"savePath": cfg.MEDIA_MOVIES_PATH}}, f)
    _config_loaded = True


class StateStore:
    def load_jobs(self) -> dict:
        with _state_lock:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f).get("jobs", {})

    def save_jobs(self, jobs: dict) -> None:
        with _state_lock:
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump({"jobs": jobs}, f, indent=2)


class CategoriesStore:
    def load(self) -> dict:
        with _categories_lock:
            with open(CATEGORIES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)

    def save(self, categories: dict) -> None:
        with _categories_lock:
            with open(CATEGORIES_FILE, "w", encoding="utf-8") as f:
                json.dump(categories, f, indent=2)


state_store = StateStore()
categories_store = CategoriesStore()