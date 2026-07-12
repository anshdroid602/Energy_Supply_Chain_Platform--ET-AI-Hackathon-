"""Shared requests session with retries + backoff.

Loaders run unattended (GitHub Actions / cron), where a single transient
network blip would otherwise fail the whole feed until the next cycle.
Retries GET on connection errors and 429/5xx with exponential backoff.
"""
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def session(retries=3, backoff=2.0):
    s = requests.Session()
    retry = Retry(
        total=retries,
        backoff_factor=backoff,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    return s


# One module-level session is fine: loaders are single-threaded scripts.
SESSION = session()


def get(url, **kwargs):
    kwargs.setdefault("timeout", 60)
    return SESSION.get(url, **kwargs)
