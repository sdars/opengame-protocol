"""Helpers for the rotating SOCKS5 egress pool.

The pool hands out one residential exit IP per port; the username carries the
session id and the country so a new port means a new IP.  Credentials are read
from an env file so nothing secret ends up in the repository.
"""

from __future__ import annotations

import os
from typing import Iterator

DEFAULT_ENV_PATH = os.environ.get('OPENGAME_PROXY_ENV', '/root/grok/.env')


def load_env(path: str = DEFAULT_ENV_PATH) -> dict[str, str]:
    """Parse a KEY=VALUE env file."""

    values: dict[str, str] = {}
    with open(path, encoding='utf-8') as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def proxy_url(env: dict[str, str], offset: int = 0) -> str:
    """Build the SOCKS5 URL for one pool port."""

    host = env['GROK_PROXY_HOST']
    password = env['GROK_PROXY_PASSWORD']
    session = env['GROK_PROXY_SESSION_ID']
    country = env.get('GROK_PROXY_COUNTRY', 'us')
    port = int(env.get('GROK_PROXY_PORT_BASE', '10000')) + offset
    user = '%s__%02d_%s' % (session, offset, country) if offset else '%s__%s' % (session, country)
    return 'socks5h://%s:%s@%s:%d' % (user, password, host, port)


def iter_proxy_urls(env: dict[str, str], offsets: Iterator[int] | list[int]) -> Iterator[str]:
    for offset in offsets:
        yield proxy_url(env, offset)


def exit_ip(proxy: str, timeout: int = 25) -> str:
    """Resolve the public IP the given proxy exits from."""

    import requests

    session = requests.Session()
    session.proxies = {'http': proxy, 'https': proxy}
    session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
    return session.get('https://api.ipify.org', timeout=timeout).text.strip()


__all__ = ['load_env', 'proxy_url', 'iter_proxy_urls', 'exit_ip']
