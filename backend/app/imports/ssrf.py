import ipaddress
import socket
from urllib.parse import urlsplit

RESOLVER = socket.getaddrinfo  # tests monkeypatch this


class UnsafeURL(ValueError):
    pass


def _bad_ip(raw: str) -> bool:
    ip = ipaddress.ip_address(raw.split("%")[0])
    ip = getattr(ip, "ipv4_mapped", None) or ip
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified


def validate_source_url(url: str, allowed_hosts: set[str] | None = None, resolver=None) -> str:
    """HTTPS only, no credentials/odd ports, optional host allowlist, and every resolved address must be public.
    Limitation: DNS can change between this check and the fetch (rebinding); the worker re-checks each hop."""
    u = urlsplit(url)
    if u.scheme != "https":
        raise UnsafeURL("scheme")
    if not u.hostname or u.username or u.password:
        raise UnsafeURL("host")
    try:
        port = u.port
    except ValueError:
        raise UnsafeURL("port")
    if port not in (None, 443):
        raise UnsafeURL("port")
    host = u.hostname.lower().rstrip(".")
    if allowed_hosts is not None and host not in allowed_hosts:
        raise UnsafeURL("host not allowlisted")
    try:
        infos = (resolver or RESOLVER)(host, 443, type=socket.SOCK_STREAM)
    except OSError:
        raise UnsafeURL("unresolvable")
    ips = {i[4][0] for i in infos}
    if not ips or any(_bad_ip(ip) for ip in ips):
        raise UnsafeURL("address not allowed")
    return host
