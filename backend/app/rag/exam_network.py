"""Reachability of configured OCR proxies, without provider calls or secrets."""
import socket
from urllib.parse import urlsplit


def proxy_available(proxy):
    if not proxy:return True
    try:
        parsed=urlsplit(proxy)
        port=parsed.port or (443 if parsed.scheme=='https' else 80)
        if parsed.scheme not in ('http','https','socks5','socks5h') or not parsed.hostname:return False
        with socket.create_connection((parsed.hostname,port),timeout=1):return True
    except (OSError,ValueError):return False


def default_proxy():
    """Use this laptop's known VPN listener when present, else its system route."""
    local='http://127.0.0.1:10809'
    return local if proxy_available(local) else ''


def scan_network(specs,provider='auto'):
    """A reachable proxy is a prerequisite, not proof of provider access."""
    selected=[s for s in specs if provider in ('auto',s.provider)]
    availability={proxy:proxy_available(proxy) for proxy in {s.proxy for s in selected}}
    unavailable=[s for s in selected if not availability[s.proxy]]
    return {'ready':not selected or len(unavailable)<len(selected),
            'unreachable_proxy_providers':sorted({s.provider for s in unavailable}),
            'affected_credentials':len(unavailable)}
