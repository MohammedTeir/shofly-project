import ipaddress
import socket
from urllib.parse import urlsplit


class UnsafeURL(ValueError):
    pass


def _bad(raw: str) -> bool:
    ip = ipaddress.ip_address(raw.split("%")[0])
    ip = getattr(ip, "ipv4_mapped", None) or ip
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified


def check_url(url: str, allowed_hosts: set[str] | None = None, resolver=socket.getaddrinfo) -> None:
    """Re-validated on every redirect hop. Same rules as the backend; DNS rebinding between check and connect remains a known gap."""
    u = urlsplit(url)
    try:
        port = u.port
    except ValueError:
        raise UnsafeURL("port")
    if u.scheme != "https" or not u.hostname or u.username or u.password:
        raise UnsafeURL("url")
    host = u.hostname.lower().rstrip(".")
    if port not in (None, 443) and not (port == 8443 and host == "d900.userdrive.org"):
        raise UnsafeURL("port")
    if allowed_hosts and host not in allowed_hosts:
        raise UnsafeURL("host")
    try:
        ips = {i[4][0] for i in resolver(host, port or 443, type=socket.SOCK_STREAM)}
    except OSError:
        raise UnsafeURL("unresolvable")
    if not ips or any(_bad(i) for i in ips):
        raise UnsafeURL("address")
