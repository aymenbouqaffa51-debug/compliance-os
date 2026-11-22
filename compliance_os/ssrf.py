"""SSRF guard for outbound network access.

Threat model
------------
A tenant controls `client.footprint["domain"]`. The perimeter collector resolves
that domain and connects to it. Without validation, a tenant supplies
their own domain and the server connects to whatever resolves next:

    127.0.0.1          -> the API's own loopback
    db                 -> a Docker service name on the internal network
    169.254.169.254    -> AWS/GCP/Azure instance metadata (credential theft)
    10.0.0.5           -> anything inside the VPC

The classic defence is "resolve, check the IP, then connect". That is broken by
DNS rebinding: the attacker answers the first query with a public IP (passes the
check) and the second query -- the one made by the HTTP client -- with
169.254.169.254.

So this module PINS the address:

    resolve once -> validate every address -> connect to that literal IP
    with Host: / SNI set to the original hostname

A rebind after validation cannot help the attacker, because the socket never
performs a second lookup.
"""

from __future__ import annotations

import ipaddress
import socket
from typing import List, Optional, Tuple

__all__ = [
    "SSRFBlocked",
    "resolve_and_validate",
    "is_public_ip",
    "validate_hostname",
    "pinned_connection",
]


class SSRFBlocked(Exception):
    """Raised when a hostname resolves to, or is, a non-public address."""


# Explicitly denied networks. ipaddress already flags most of these via
# is_private / is_loopback / is_link_local / is_reserved / is_multicast, but
# listing them makes the intent reviewable and catches the ones the stdlib
# classifies loosely (e.g. some cloud metadata ranges are merely 'private').
_DENY_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),          # "this" network
    ipaddress.ip_network("10.0.0.0/8"),         # RFC 1918
    ipaddress.ip_network("100.64.0.0/10"),      # CGNAT
    ipaddress.ip_network("127.0.0.0/8"),        # loopback
    ipaddress.ip_network("169.254.0.0/16"),     # link-local + cloud metadata
    ipaddress.ip_network("172.16.0.0/12"),      # RFC 1918
    ipaddress.ip_network("192.0.0.0/24"),       # IETF protocol assignments
    ipaddress.ip_network("192.0.2.0/24"),       # TEST-NET-1
    ipaddress.ip_network("192.88.99.0/24"),     # 6to4 relay anycast
    ipaddress.ip_network("192.168.0.0/16"),     # RFC 1918
    ipaddress.ip_network("198.18.0.0/15"),      # benchmarking
    ipaddress.ip_network("198.51.100.0/24"),    # TEST-NET-2
    ipaddress.ip_network("203.0.113.0/24"),     # TEST-NET-3
    ipaddress.ip_network("224.0.0.0/4"),        # multicast
    ipaddress.ip_network("240.0.0.0/4"),        # reserved
    ipaddress.ip_network("::1/128"),            # IPv6 loopback
    ipaddress.ip_network("::/128"),             # IPv6 unspecified
    ipaddress.ip_network("fc00::/7"),           # IPv6 unique local
    ipaddress.ip_network("fe80::/10"),          # IPv6 link-local
    ipaddress.ip_network("ff00::/8"),           # IPv6 multicast
    ipaddress.ip_network("::ffff:0:0/96"),      # IPv4-mapped IPv6
    ipaddress.ip_network("64:ff9b::/96"),       # NAT64
    ipaddress.ip_network("2001:db8::/32"),      # documentation
]


def is_public_ip(ip: str) -> Tuple[bool, str]:
    """Return (allowed, reason). Only globally routable unicast addresses pass."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False, "not a valid IP address: %r" % ip

    # An IPv4-mapped IPv6 address must be judged by its IPv4 half, otherwise
    # ::ffff:127.0.0.1 would slip past the IPv6 checks.
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        addr = addr.ipv4_mapped

    for net in _DENY_NETWORKS:
        try:
            if addr.version == net.version and addr in net:
                return False, "%s is inside the denied range %s" % (addr, net)
        except TypeError:
            continue

    # Belt and braces: the stdlib's own classification.
    if addr.is_loopback:
        return False, "%s is a loopback address" % addr
    if addr.is_link_local:
        return False, "%s is link-local (cloud metadata lives here)" % addr
    if addr.is_multicast:
        return False, "%s is multicast" % addr
    if addr.is_reserved:
        return False, "%s is reserved" % addr
    if getattr(addr, "is_private", False):
        return False, "%s is a private address" % addr
    if not addr.is_global:
        return False, "%s is not globally routable" % addr

    return True, "public"


def validate_hostname(host: str) -> None:
    """Reject hostname shapes that can never legitimately be a client domain."""
    if not host or not isinstance(host, str):
        raise SSRFBlocked("empty hostname")
    h = host.strip().rstrip(".").lower()
    if not h:
        raise SSRFBlocked("empty hostname")
    if len(h) > 253:
        raise SSRFBlocked("hostname longer than 253 characters")
    # Bare IPs are allowed only if public; caller validates resolved addresses.
    if ":" in h or h.replace(".", "").isdigit():
        ok, reason = is_public_ip(h)
        if not ok:
            raise SSRFBlocked(reason)
        return
    if "/" in h or "@" in h or " " in h or "\\" in h:
        raise SSRFBlocked("hostname contains illegal characters: %r" % host)
    labels = h.split(".")
    if len(labels) < 2:
        # A single-label name resolves inside a container network, e.g. `db`.
        raise SSRFBlocked(
            "%r is a single-label hostname; internal service names are not "
            "valid client domains" % host
        )
    for label in labels:
        if not label or len(label) > 63:
            raise SSRFBlocked("hostname has an invalid label: %r" % host)
        if label.startswith("-") or label.endswith("-"):
            raise SSRFBlocked("hostname label starts or ends with a hyphen: %r" % host)
        if not all(c.isalnum() or c == "-" for c in label):
            raise SSRFBlocked("hostname has an illegal character in a label: %r" % host)
    blocked_suffixes = (".localhost", ".local", ".internal", ".localdomain",
                        ".home.arpa", ".in-addr.arpa", ".ip6.arpa")
    if h.endswith(blocked_suffixes):
        raise SSRFBlocked("hostname uses a reserved/internal suffix: %r" % host)


def resolve_and_validate(host: str, port: int = 443) -> List[str]:
    """Resolve `host` and return validated public IPs.

    Every address the hostname resolves to is validated. If ANY address is
    non-public the whole host is rejected -- accepting the public subset would
    let an attacker put 169.254.169.254 second in the answer list and rely on
the client trying it.
    """
    validate_hostname(host)

    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise SSRFBlocked("hostname %r does not resolve: %s" % (host, exc))

    addresses: List[str] = []
    for info in infos:
        ip = info[4][0]
        # Strip an IPv6 zone index (fe80::1%eth0)
        if "%" in ip:
            ip = ip.split("%", 1)[0]
        if ip not in addresses:
            addresses.append(ip)

    if not addresses:
        raise SSRFBlocked("hostname %r resolved to no addresses" % host)

    for ip in addresses:
        ok, reason = is_public_ip(ip)
        if not ok:
            raise SSRFBlocked(
                "hostname %r resolves to a non-public address: %s" % (host, reason)
            )

    return addresses


class pinned_connection:
    """A socket bound to a pre-validated IP, with SNI for the real hostname.

    Usage:
        with pinned_connection("example.com", "93.184.216.34", 443) as sock:
            tls = ctx.wrap_socket(sock, server_hostname="example.com")

    The DNS lookup already happened during validation; the socket connects to
    the literal IP, so a second lookup cannot be rebound.
    """

    def __init__(self, host: str, ip: str, port: int = 443, timeout: float = 12.0):
        self.host = host
        self.ip = ip
        self.port = port
        self.timeout = timeout
        self._sock: Optional[socket.socket] = None

    def __enter__(self) -> socket.socket:
        ok, reason = is_public_ip(self.ip)
        if not ok:
            raise SSRFBlocked("refusing to connect to %s: %s" % (self.ip, reason))
        family = socket.AF_INET6 if ":" in self.ip else socket.AF_INET
        sock = socket.socket(family, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        sock.connect((self.ip, self.port))
        self._sock = sock
        return sock

    def __exit__(self, *exc_info) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
