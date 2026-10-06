import time

import requests

from . import config

_session = requests.Session()
_session.headers["User-Agent"] = config.USER_AGENT


class NotFound(Exception):
    """The server says the page doesn't exist; retrying won't help."""


def get(url, params=None, retries=3, headers=None):
    """GET with a few retries. Raises NotFound on a 404, and the last error
    on any other final failure."""
    last = None
    for attempt in range(retries):
        try:
            resp = _session.get(url, params=params, timeout=config.HTTP_TIMEOUT, headers=headers)
            if resp.status_code == 404:
                raise NotFound(url)
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
