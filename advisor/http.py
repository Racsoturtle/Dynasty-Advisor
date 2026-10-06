import time

import requests

from . import config

_session = requests.Session()
_session.headers["User-Agent"] = config.USER_AGENT


def get(url, params=None, retries=3):
    """GET with a few retries. Raises on final failure."""
    last = None
    for attempt in range(retries):
        try:
            resp = _session.get(url, params=params, timeout=config.HTTP_TIMEOUT)
            resp.raise_for_status()
            return resp
        except requests.RequestException as exc:
            last = exc
            time.sleep(2 ** attempt)
    raise last


def get_json(url, params=None):
    return get(url, params).json()


def get_text(url, params=None):
    return get(url, params).text
