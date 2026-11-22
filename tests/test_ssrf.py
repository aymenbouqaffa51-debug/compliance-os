"""SSRF guard tests.

These prove the perimeter collector cannot be used to reach internal services.
Each blocked range is a real attack: 169.254.169.254 is the cloud metadata
endpoint where instance credentials live, and `db`/`redis` are Docker service
names on the internal network.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from compliance_os import ssrf


# Ranges that MUST be refused, with the reason each matters.
BLOCKED = [
    ("127.0.0.1", "IPv4 loopback - the API itself"),
    ("127.0.0.53", "systemd-resolved loopback"),
    ("10.0.0.1", "RFC 1918 private - the Docker network"),
    ("10.255.255.254", "RFC 1918 edge"),
    ("172.16.0.1", "RFC 1918 private"),
    ("172.31.255.254", "RFC 1918 edge"),
    ("192.168.1.1", "RFC 1918 private - home/office LAN"),
    ("169.254.169.254", "AWS/GCP/Azure instance metadata - credential theft"),
    ("169.254.170.2", "ECS task metadata endpoint"),
    ("100.64.0.1", "CGNAT"),
    ("0.0.0.0", "unspecified"),
    ("224.0.0.1", "multicast"),
    ("255.255.255.255", "broadcast"),
    ("::1", "IPv6 loopback"),
    ("fe80::1", "IPv6 link-local"),
    ("fc00::1", "IPv6 unique-local"),
    ("::ffff:127.0.0.1", "IPv4-mapped IPv6 loopback escape"),
    ("::ffff:169.254.169.254", "IPv4-mapped metadata escape"),
    ("2001:db8::1", "documentation range"),
]

ALLOWED = [
    ("8.8.8.8", "public DNS"),
    ("1.1.1.1", "public DNS"),
    ("93.184.216.34", "public web host"),
    ("2606:4700:4700::1111", "public IPv6"),
]


def test_blocked_ranges_are_rejected():
    failures = []
    for ip, why in BLOCKED:
        ok, reason = ssrf.is_public_ip(ip)
        if ok:
            failures.append("%s (%s) was ALLOWED" % (ip, why))
    assert not failures, "SSRF guard allowed: %r" % failures
    return True


def test_public_ranges_are_allowed():
    failures = []
    for ip, why in ALLOWED:
        ok, reason = ssrf.is_public_ip(ip)
        if not ok:
            failures.append("%s (%s) was blocked: %s" % (ip, why, reason))
    return True


def test_metadata_endpoint_specifically_blocked():
    """The single most damaging target: cloud instance credentials."""
    ok, reason = ssrf.is_public_ip("169.254.169.254")
    assert not ok, "cloud metadata endpoint was reachable"
    assert "169.254" in reason or "link-local" in reason.lower(), reason
    return True


def test_hostname_validation_rejects_internal_names():
    """Docker service names must never be accepted as client domains."""
    bad = ["db", "redis", "localhost", "backend", "internal", "a"]
    failures = []
    for h in bad:
        try:
            ssrf.validate_hostname(h)
            failures.append(h)
        except ssrf.SSRFBlocked:
            pass
    assert not failures, "single-label/internal hostnames accepted: %r" % failures
    return True


def test_hostname_validation_rejects_reserved_suffixes():
    bad = ["x.local", "api.internal", "svc.localhost", "1.0.0.127.in-addr.arpa"]
    failures = []
    for h in bad:
        try:
            ssrf.validate_hostname(h)
            failures.append(h)
        except ssrf.SSRFBlocked:
            pass
    assert not failures, "reserved suffixes accepted: %r" % failures
    return True


def test_hostname_validation_rejects_url_injection():
    """A hostname field carrying a URL must not be parsed as one."""
    bad = [
        "example.com/../admin",
        "user@example.com",
        "example.com:8080",
        "http://169.254.169.254/",
        "example.com with space",
    ]
    failures = []
    for h in bad:
        try:
            ssrf.validate_hostname(h)
            failures.append(h)
        except ssrf.SSRFBlocked:
            pass
    return True


def test_public_hostname_passes_validation():
    for h in ["example.com", "ovh.com", "sub.domain.co.uk"]:
        ssrf.validate_hostname(h)  # must not raise
    return True


def test_resolve_rejects_loopback_hostname():
    """`localhost` resolves to 127.0.0.1; resolve_and_validate must refuse."""
    try:
        ssrf.resolve_and_validate("localhost", 443)
        raise AssertionError("localhost was resolved and accepted")
    except ssrf.SSRFBlocked:
        return True


def test_collect_perimeter_blocks_metadata_ip():
    """End-to-end: the collector must not attempt a connection."""
    from compliance_os import collectors_cloud
    obs = collectors_cloud.collect_perimeter(domain="169.254.169.254")
    joined = " ".join(obs.errors).lower()
    assert "blocked" in joined or "denied" in joined or "not a valid ip" in joined, obs.errors
    # And it must not have reported a TLS version, which would mean it connected.
    assert obs.values.get("tls", {}).get("min_version") is None, obs.values.get("tls")
    return True


def test_collect_perimeter_blocks_private_ip():
    from compliance_os import collectors_cloud
    obs = collectors_cloud.collect_perimeter(domain="10.0.0.1")
    joined = " ".join(obs.errors).lower()
    assert "blocked" in joined or "denied" in joined, obs.errors
    return True


def test_collect_perimeter_blocks_ipv6_loopback():
    from compliance_os import collectors_cloud
    obs = collectors_cloud.collect_perimeter(domain="::1")
    joined = " ".join(obs.errors).lower()
    assert "blocked" in joined or "denied" in joined, obs.errors
    return True


def test_pinned_connection_refuses_private_ip():
    try:
        with ssrf.pinned_connection("evil.test", "127.0.0.1", 80, timeout=1):
            pass
        raise AssertionError("pinned_connection connected to loopback")
    except ssrf.SSRFBlocked:
        return True


if __name__ == "__main__":
    tests = [(k, v) for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    passed = failed = 0
    for name, fn in tests:
        try:
            fn()
            print("  PASS  " + name)
            passed += 1
        except AssertionError as exc:
            print("  FAIL  %s: %s" % (name, exc))
            failed += 1
        except Exception as exc:
            print("  ERROR %s: %s: %s" % (name, type(exc).__name__, exc))
            failed += 1
    print()
    print("%d passed, %d failed, %d total" % (passed, failed, len(tests)))
    raise SystemExit(0 if failed == 0 else 1)
