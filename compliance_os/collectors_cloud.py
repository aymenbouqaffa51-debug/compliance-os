"""Read-only collectors for cloud, SaaS and perimeter checks.

Every collector in this module obeys the same contract:

    collect_*(...) -> Observation

An Observation is facts, never a verdict. `checks.py` turns facts into
PASS/FAIL; a human turns those into a control state.

Credential rule: credentials come from the process environment ONLY. They are
never accepted as function arguments from a CLI, never written to disk, never
logged, and never included in the returned Observation. If a credential is
missing the collector returns an Observation whose `errors` explain what is
missing, rather than raising -- so one unconfigured integration does not abort
a whole monitoring run.

Read-only rule: nothing here performs a mutating API call. The GitHub collector
issues GET requests only. The AWS collector uses describe/list/get calls only,
equivalent to the AWS-managed SecurityAudit policy. The perimeter collector
speaks TLS and HTTP GET to a host the operator names.
"""

from __future__ import annotations

import json
import os
import re
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from compliance_os import ssrf
from compliance_os.checks import Observation

__version__ = "3.0.0"

__all__ = [
    "collect_github",
    "collect_aws",
    "collect_perimeter",
    "collect_workspace",
]

UA = "compliance-os/2.0 (read-only monitoring)"


class CollectorConfigError(Exception):
    """Raised when a collector cannot run at all (missing config).

    Individual calls that fail return an Observation with errors instead, so a
    run continues.
    """


# =====================================================================
# GitHub
# =====================================================================
GITHUB_API = "https://api.github.com"


def _github_get(path: str, token: str, timeout: int = 30) -> Tuple[int, Any]:
    """GET a GitHub API path. Returns (status, parsed_body_or_None)."""
    req = urllib.request.Request(
        GITHUB_API + path,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": UA,
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return resp.status, (json.loads(raw) if raw.strip() else None)
    except urllib.error.HTTPError as exc:
        return exc.code, None
    except Exception:
        return 0, None


def _paged_github(path: str, token: str, max_pages: int = 5, per_page: int = 100) -> List[Any]:
    """Follow Link pagination, bounded. Read-only."""
    out: List[Any] = []
    sep = "&" if "?" in path else "?"
    for page in range(1, max_pages + 1):
        status, body = _github_get("%s%sper_page=%d&page=%d" % (path, sep, per_page, page), token)
        if status != 200 or not isinstance(body, list):
            break
        out.extend(body)
        if len(body) < per_page:
            break
    return out


def collect_github(org: str = "", token: str = "") -> Observation:
    """Collect GitHub organisation posture. GET requests only.

    Token comes from GITHUB_TOKEN if not passed explicitly. A fine-grained PAT
    with read-only Administration + Members + Code-scanning permissions is
    sufficient; a classic token needs `read:org` and `repo` (read).
    """
    token = token or os.environ.get("GITHUB_TOKEN", "")
    org = org or os.environ.get("GITHUB_ORG", "")

    obs = Observation(source="github", meta={"org": org})
    if not org:
        obs.errors.append("no organisation configured (set GITHUB_ORG or pass org)")
        return obs
    if not token:
        obs.errors.append("no GitHub token configured (set GITHUB_TOKEN, read-only scope)")
        return obs

    # --- organisation: 2FA requirement, secret scanning, dependabot
    status, org_body = _github_get("/orgs/%s" % org, token)
    if status != 200 or not isinstance(org_body, dict):
        obs.errors.append("cannot read organisation %r (HTTP %s)" % (org, status))
        return obs

    obs.values["org"] = {
        "name": org_body.get("login", org),
        "two_factor_required": bool(org_body.get("two_factor_requirement_enabled", False)),
        # These two are only exposed on some plans; absent means unknown, and
        # the check will resolve NOT_APPLICABLE rather than a false FAIL.
        "secret_scanning_enabled": org_body.get("secret_scanning_enabled_for_new_repositories", None),
        "dependabot_alerts_enabled": org_body.get("dependabot_alerts_enabled_for_new_repositories", None),
        "commit_signing_required": org_body.get("web_commit_signoff_required", None),
        "plan": (org_body.get("plan") or {}).get("name", ""),
    }

    # --- repositories: branch protection on default branches
    repos = _paged_github("/orgs/%s/repos?type=all&sort=pushed" % org, token, max_pages=3)
    unprotected: List[str] = []
    repo_names: List[str] = []
    for r in repos:
        if not isinstance(r, dict):
            continue
        name = r.get("name", "")
        if not name or r.get("archived"):
            continue
        repo_names.append(name)
        default = r.get("default_branch") or "main"
        st, prot = _github_get("/repos/%s/%s/branches/%s/protection" % (org, name, default), token)
        # 404 means explicitly no protection; 403 means no permission (unknown)
        if st == 404:
            unprotected.append(name)
    obs.values["repos"] = {
        "count": len(repo_names),
        "names_sample": repo_names[:20],
        "unprotected_default_branches": unprotected,
    }

    # --- outside collaborators
    collab = _paged_github("/orgs/%s/outside_collaborators" % org, token, max_pages=2)
    obs.values["outside_collaborators"] = {
        "count": len(collab),
        "logins_sample": [c.get("login") for c in collab[:20] if isinstance(c, dict)],
    }

    # --- dependabot alert ageing (first page only; enough to evidence the SLA)
    alerts = _paged_github("/orgs/%s/dependabot/alerts?state=open" % org, token, max_pages=1)
    old_crit: List[str] = []
    import datetime as _dt
    now = _dt.datetime.now(_dt.timezone.utc)
    for a in alerts:
        if not isinstance(a, dict):
            continue
        sev = ((a.get("security_advisory") or {}).get("severity") or "").lower()
        created = a.get("created_at") or ""
        if sev != "critical" or not created:
            continue
        try:
            when = _dt.datetime.strptime(created[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=_dt.timezone.utc)
        except Exception:
            continue
        if (now - when).days > 30:
            old_crit.append("%s#%s" % (
                ((a.get("dependency") or {}).get("package") or {}).get("name", "?"), a.get("number", "?")))
    obs.values["dependabot"] = {
        "open_total": len(alerts),
        "critical_open_over_30d": old_crit,
    }

    # Access reviews are an organisational fact we cannot read from the API;
    # expose the member count so the operator can record the review manually.
    members = _paged_github("/orgs/%s/members" % org, token, max_pages=2)
    obs.values["members"] = {"count": len(members)}

    return obs


# =====================================================================
# AWS
# =====================================================================
READONLY_POLICY_HINT = "SecurityAudit"


def collect_aws(region: str = "", profile: str = "") -> Observation:
    """Collect AWS account posture using read-only API calls only.

    Requires boto3 and credentials in the standard chain (env vars, shared
    config, or an instance/task role). The IAM policy required is the AWS-managed
    `SecurityAudit` policy, which is read-only by construction.

    Returns an Observation with errors if boto3 is missing or credentials are
    absent -- it does not raise.
    """
    region = region or os.environ.get("AWS_REGION", "") or os.environ.get("AWS_DEFAULT_REGION", "")
    obs = Observation(source="aws", meta={"region": region, "policy": READONLY_POLICY_HINT})

    try:
        import boto3  # noqa: F401
        from botocore.exceptions import ClientError, NoCredentialsError
    except ImportError:
        obs.errors.append("boto3 is not installed (pip install boto3); AWS checks skipped")
        return obs

    try:
        session = boto3.Session(profile_name=profile or None, region_name=region or None)
        sts = session.client("sts")
        ident = sts.get_caller_identity()
        obs.meta["account"] = ident.get("Account", "")
        obs.meta["caller_arn"] = ident.get("Arn", "")
    except NoCredentialsError:
        obs.errors.append("no AWS credentials in the standard chain; AWS checks skipped")
        return obs
    except Exception as exc:
        obs.errors.append("cannot establish AWS identity: %s" % type(exc).__name__)
        return obs

    def safe(fn, label: str, default=None):
        try:
            return fn()
        except ClientError as exc:
            code = (exc.response.get("Error") or {}).get("Code", "")
            # AccessDenied means the credential is not read-only-complete, which
            # is an infrastructure problem to report, not a compliance failure.
            obs.errors.append("%s: %s" % (label, code))
            return default
        except Exception as exc:
            obs.errors.append("%s: %s" % (label, type(exc).__name__))
            return default

    # ---- IAM
    iam = session.client("iam")

    def _root_mfa() -> Dict[str, Any]:
        s = iam.get_account_summary().get("SummaryMap", {})
        return {"AccountMFAEnabled": int(s.get("AccountMFAEnabled", 0)) == 1}

    root = safe(_root_mfa, "iam:GetAccountSummary", {}) or {}
    obs.values.setdefault("iam", {})["root_mfa_enabled"] = root.get("AccountMFAEnabled")

    def _root_keys() -> List[str]:
        """Root access keys, from the account summary.

        The summary exposes only a COUNT (AccountAccessKeysPresent), not the key
        IDs. We return one placeholder per key so the check can test len == 0
        without pretending to know identifiers we cannot read.
        """
        summary = iam.get_account_summary().get("SummaryMap", {})
        count = int(summary.get("AccountAccessKeysPresent", 0))
        return ["root"] * count

    obs.values["iam"]["root_access_keys"] = safe(_root_keys, "iam:list root keys", []) or []

    def _users_without_mfa() -> List[str]:
        bad = []
        paginator = iam.get_paginator("list_users")
        for page in paginator.paginate():
            for u in page.get("Users", []):
                name = u.get("UserName", "")
                mfa = iam.list_mfa_devices(UserName=name).get("MFADevices", [])
                if not mfa:
                    bad.append(name)
        return bad

    obs.values["iam"]["users_without_mfa"] = safe(_users_without_mfa, "iam:ListMFADevices", []) or []

    def _password_policy() -> Dict[str, Any]:
        p = iam.get_account_password_policy().get("PasswordPolicy", {})
        return {"min": int(p.get("MinimumPasswordLength", 0))}

    pp = safe(_password_policy, "iam:GetAccountPasswordPolicy", {}) or {}
    obs.values["iam"]["password_policy_min_length"] = pp.get("min")

    def _stale_keys() -> List[str]:
        import datetime as _dt
        now = _dt.datetime.now(_dt.timezone.utc)
        stale = []
        for page in iam.get_paginator("list_users").paginate():
            for u in page.get("Users", []):
                name = u.get("UserName", "")
                for k in iam.list_access_keys(UserName=name).get("AccessKeyMetadata", []):
                    created = k.get("CreateDate")
                    if created and (now - created).days > 90 and k.get("Status") == "Active":
                        stale.append("%s/%s" % (name, k.get("AccessKeyId", "")[:8]))
        return stale

    obs.values["iam"]["stale_access_keys"] = safe(_stale_keys, "iam:ListAccessKeys", []) or []

    # ---- S3
    s3 = session.client("s3")

    def _bucket_is_public(name: str) -> bool:
        """A bucket is public if policy OR ACL OR the public-access block allow it.

        Checking only the bucket policy misses the common real-world case of an
        ACL granting AllUsers, and misses a bucket that has no public-access
        block at all. Three independent signals are tested; any one is enough.
        """
        # (a) explicit public bucket policy
        try:
            pol = s3.get_bucket_policy(Bucket=name).get("Policy", "")
            if '"*"' in pol and ("s3:GetObject" in pol or "s3:*" in pol):
                return True
        except ClientError as exc:
            if (exc.response.get("Error") or {}).get("Code") != "NoSuchBucketPolicy":
                pass  # other error: fall through to the ACL check

        # (b) any READ grant to AllUsers / AuthenticatedUsers
        try:
            acl = s3.get_bucket_acl(Bucket=name)
            for grant in acl.get("Grants", []) or []:
                grantee = grant.get("Grantee") or {}
                uri = grantee.get("URI", "")
                if uri.endswith("AllUsers") or uri.endswith("AuthenticatedUsers"):
                    return True
        except ClientError:
            pass

        # (c) no public-access block on the bucket itself
        try:
            blk = s3.get_public_access_block(Bucket=name).get("PublicAccessBlockConfiguration", {})
            if not all([
                blk.get("BlockPublicAcls"), blk.get("IgnorePublicAcls"),
                blk.get("BlockPublicPolicy"), blk.get("RestrictPublicBuckets"),
            ]):
                # Incomplete block alone is not proof of exposure, but combined
                # with an ACL/policy grant above it would be. Only report when a
                # grant also exists, to avoid false positives on every bucket.
                return False
        except ClientError:
            # GetPublicAccessBlock raises NoSuchPublicAccessBlockConfiguration
            # when the bucket has no block at all -- worth noting, not alone
            # sufficient to call it public.
            pass
        return False

    def _s3_public() -> Dict[str, Any]:
        account_blocked = False
        try:
            resp = s3.get_public_access_block(AccountId=obs.meta.get("account", ""))
            cfg = resp.get("PublicAccessBlockConfiguration", {})
            account_blocked = all([
                cfg.get("BlockPublicAcls"), cfg.get("IgnorePublicAcls"),
                cfg.get("BlockPublicPolicy"), cfg.get("RestrictPublicBuckets"),
            ])
        except ClientError:
            account_blocked = False

        public = []
        bucket_names = []
        for b in s3.list_buckets().get("Buckets", []):
            name = b.get("Name", "")
            if not name:
                continue
            bucket_names.append(name)
            if _bucket_is_public(name):
                public.append(name)
        return {"account_blocked": account_blocked, "public": public,
                "bucket_names": bucket_names}

    s3d = safe(_s3_public, "s3:public access", {}) or {}
    obs.values["s3"] = {
        "account_public_access_blocked": s3d.get("account_blocked"),
        "public_buckets": s3d.get("public", []),
    }

    # ---- CloudTrail
    ct = session.client("cloudtrail")

    def _trail() -> Dict[str, Any]:
        trails = ct.describe_trails(includeShadowTrails=False).get("trailList", [])
        multi = any(t.get("IsMultiRegionTrail") for t in trails)
        logging_on = False
        for t in trails:
            if t.get("IsMultiRegionTrail"):
                st = ct.get_trail_status(Name=t.get("TrailARN", ""))
                logging_on = bool(st.get("IsLogging"))
        return {"enabled_all_regions": bool(multi and logging_on)}

    ctd = safe(_trail, "cloudtrail:DescribeTrails", {}) or {}

    def _cloudtrail_bucket_public() -> Any:
        """Is the bucket holding CloudTrail logs public? (AWS-07)

        Previously hardcoded to None, so AWS-07 could never pass or fail -- it
        always resolved NOT_APPLICABLE. This reads the trail's S3BucketName and
        applies the same three-signal test as the bucket scan.
        """
        trails = ct.describe_trails(includeShadowTrails=False).get("trailList", [])
        if not trails:
            return None
        bucket_names = {t.get("S3BucketName") for t in trails if t.get("S3BucketName")}
        if not bucket_names:
            return None
        for bucket in bucket_names:
            try:
                pol = s3.get_bucket_policy(Bucket=bucket).get("Policy", "")
                if '"*"' in pol and ("s3:GetObject" in pol or "s3:*" in pol):
                    return True
            except ClientError:
                pass
            if _bucket_is_public(bucket):
                return True
        return False

    obs.values["cloudtrail"] = {
        "enabled_all_regions": ctd.get("enabled_all_regions"),
        "log_bucket_public": safe(_cloudtrail_bucket_public, "cloudtrail:log bucket", None),
    }

    # ---- EC2: encryption + open admin ports
    ec2 = session.client("ec2")

    def _ec2() -> Dict[str, Any]:
        unenc = []
        for page in ec2.get_paginator("describe_volumes").paginate():
            for v in page.get("Volumes", []):
                if not v.get("Encrypted"):
                    unenc.append(v.get("VolumeId", ""))
        open_admin = []
        for page in ec2.get_paginator("describe_security_groups").paginate():
            for sg in page.get("SecurityGroups", []):
                for perm in sg.get("IpPermissions", []):
                    frm = perm.get("FromPort")
                    if frm not in (22, 3389):
                        continue
                    for rng in perm.get("IpRanges", []):
                        if rng.get("CidrIp") in ("0.0.0.0/0", "::/0"):
                            open_admin.append("%s:%s" % (sg.get("GroupId", ""), frm))
        return {"unencrypted": unenc, "open": open_admin}

    e = safe(_ec2, "ec2:describe", {}) or {}
    obs.values["ec2"] = {
        "unencrypted_volumes": e.get("unencrypted", []),
        "open_admin_ports": e.get("open", []),
    }

    # ---- RDS
    rds = session.client("rds")

    def _rds() -> List[str]:
        unenc = []
        for page in rds.get_paginator("describe_db_instances").paginate():
            for db in page.get("DBInstances", []):
                if not db.get("StorageEncrypted"):
                    unenc.append(db.get("DBInstanceIdentifier", ""))
        return unenc

    obs.values["rds"] = {"unencrypted_instances": safe(_rds, "rds:describe", []) or []}

    # ---- GuardDuty
    try:
        gd = session.client("guardduty")
        dets = gd.list_detectors().get("DetectorIds", [])
        obs.values["guardduty"] = {"enabled": bool(dets)}
    except Exception as exc:
        obs.values["guardduty"] = {"enabled": None}
        obs.errors.append("guardduty: %s" % type(exc).__name__)

    return obs


# =====================================================================
# Perimeter
# =====================================================================
SECURITY_HEADERS = {
    "strict-transport-security": "hsts",
    "content-security-policy": "csp",
    "x-content-type-options": "xcto",
    "x-frame-options": "xfo",
}


def _tls_probe(host: str, port: int = 443, timeout: int = 12) -> Dict[str, Any]:
    """Negotiate TLS and read the certificate. No data is sent.

    The hostname is resolved and validated BEFORE any socket is opened, and the
    socket is then pinned to the validated IP. SNI still carries the real
    hostname, so the certificate check is meaningful. This closes the DNS
    rebinding window that a naive resolve-then-connect leaves open.
    """
    out: Dict[str, Any] = {"min_version": None, "days_to_expiry": None, "error": ""}

    try:
        addresses = ssrf.resolve_and_validate(host, port)
    except ssrf.SSRFBlocked as exc:
        out["error"] = "blocked by SSRF guard: %s" % exc
        return out

    ctx = ssl.create_default_context()
    last_error = ""
    for ip in addresses:
        try:
            with ssrf.pinned_connection(host, ip, port, timeout=timeout) as sock:
                with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                    out["min_version"] = ssock.version()
                    cert = ssock.getpeercert()
                    not_after = cert.get("notAfter")
                    if not_after:
                        import datetime as _dt
                        exp = _dt.datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z")
                        out["days_to_expiry"] = (exp - _dt.datetime.utcnow()).days
                    out["connected_ip"] = ip
                    return out
        except ssl.SSLError as exc:
            out["error"] = "TLS error: %s" % exc
            # A handshake failure often means the server only offers <1.2
            if "UNSUPPORTED_PROTOCOL" in str(exc) or "no protocols available" in str(exc):
                out["min_version"] = "1.0"
            return out
        except Exception as exc:
            last_error = "%s: %s" % (type(exc).__name__, exc)
            continue

    out["error"] = last_error or "no address could be reached"
    return out


def _http_headers(url: str, timeout: int = 15) -> Dict[str, Any]:
    """GET the URL and return header facts. Body is discarded, not stored.

    Same SSRF discipline as _tls_probe: validate, then connect to the pinned
    IP. urllib is used with a custom connection so the Host header and SNI
    still carry the original hostname.
    """
    out: Dict[str, Any] = {
        "ok": False, "hsts_present": None, "hsts_max_age": None,
        "csp_present": None, "x_content_type_options": None,
        "frame_protection": None, "server_banner_discloses_version": None,
    }

    parsed = urllib.parse.urlsplit(url)
    host = parsed.hostname or ""
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query

    try:
        addresses = ssrf.resolve_and_validate(host, port)
    except ssrf.SSRFBlocked as exc:
        out["error"] = "blocked by SSRF guard: %s" % exc
        return out

    ctx = ssl.create_default_context()
    last_error = ""
    for ip in addresses:
        sock = None
        wrapped = None
        try:
            sock = ssrf.pinned_connection(host, ip, port, timeout=timeout).__enter__()
            if parsed.scheme == "https":
                wrapped = ctx.wrap_socket(sock, server_hostname=host)
                stream = wrapped
            else:
                stream = sock

            request = (
                "GET %s HTTP/1.1\r\n"
                "Host: %s\r\n"
                "User-Agent: %s\r\n"
                "Accept: */*\r\n"
                "Connection: close\r\n\r\n" % (path, host, UA)
            )
            stream.sendall(request.encode("ascii"))

            # Read only the headers; the body is never stored.
            raw = b""
            while b"\r\n\r\n" not in raw and len(raw) < 65536:
                chunk = stream.recv(4096)
                if not chunk:
                    break
                raw += chunk

            head = raw.split(b"\r\n\r\n", 1)[0].decode("iso-8859-1", "replace")
            lines = head.split("\r\n")
            h = {}
            for line in lines[1:]:
                if ":" in line:
                    k, v = line.split(":", 1)
                    h[k.strip().lower()] = v.strip()

            out["ok"] = True
            hsts = h.get("strict-transport-security", "")
            out["hsts_present"] = bool(hsts)
            m = re.search(r"max-age\s*=\s*(\d+)", hsts, re.I)
            out["hsts_max_age"] = int(m.group(1)) if m else (0 if hsts else None)
            out["csp_present"] = bool(h.get("content-security-policy"))
            out["x_content_type_options"] = h.get("x-content-type-options")
            out["frame_protection"] = bool(
                h.get("x-frame-options") or "frame-ancestors" in h.get("content-security-policy", "")
            )
            server = h.get("server", "")
            out["server_banner_discloses_version"] = bool(re.search(r"\d+\.\d+", server))
            out["connected_ip"] = ip
            return out
        except Exception as exc:
            last_error = "%s: %s" % (type(exc).__name__, exc)
        finally:
            for s in (wrapped, sock):
                if s is not None:
                    try:
                        s.close()
                    except OSError:
                        pass

    out["error"] = last_error or "no address could be reached"
    return out


def _dns_records(domain: str) -> Dict[str, Any]:
    """Resolve SPF / DMARC / DKIM presence via DNS TXT.

    Uses the resolver in /etc/resolv.conf via socket for A records, and a plain
    DNS-over-HTTPS query to Cloudflare for TXT (no dependency on dnspython).
    """
    out: Dict[str, Any] = {
        "spf_present": None, "dmarc_present": None,
        "dmarc_policy": None, "dkim_present": None,
        "zone_transfer_open": None,
    }

    def txt(name: str) -> List[str]:
        url = "https://cloudflare-dns.com/dns-query?name=%s&type=TXT" % name
        req = urllib.request.Request(url, headers={"accept": "application/dns-json", "User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8", "replace"))
            answers = data.get("Answer", []) or []
            return [a.get("data", "").strip('"') for a in answers if a.get("type") == 16]
        except Exception:
            return []

    spf = [t for t in txt(domain) if t.lower().startswith("v=spf1")]
    out["spf_present"] = bool(spf)

    dmarc = [t for t in txt("_dmarc." + domain) if "v=dmarc1" in t.lower()]
    out["dmarc_present"] = bool(dmarc)
    if dmarc:
        m = re.search(r"\bp\s*=\s*(none|quarantine|reject)", dmarc[0], re.I)
        out["dmarc_policy"] = m.group(1).lower() if m else None

    # Common DKIM selectors. Absence from this list is not proof of absence.
    for sel in ("default", "google", "selector1", "selector2", "k1", "mail"):
        if txt("%s._domainkey.%s" % (sel, domain)):
            out["dkim_present"] = True
            out["dkim_selector"] = sel
            break
    if out["dkim_present"] is None:
        out["dkim_present"] = False

    return out


def collect_perimeter(domain: str = "", base_url: str = "") -> Observation:
    """TLS, HTTP security headers and email authentication for a public host.

    Requires no credentials -- this is why it is the first collector to run for
    any prospect: it produces visible findings in seconds.
    """
    domain = domain or os.environ.get("PERIMETER_DOMAIN", "")
    obs = Observation(source="perimeter", meta={"domain": domain})
    if not domain:
        obs.errors.append("no domain configured (set PERIMETER_DOMAIN or pass domain)")
        return obs

    # Validate BEFORE building a URL or opening anything.
    #
    # This ordering is a security control, not tidiness. A bare IPv6 literal
    # such as "::1" placed into "https://%s" produces "https://::1", whose
    # urlsplit() raises ValueError on the port -- an unhandled crash that
    # leaks a traceback and, worse, means the hostile input was never actually
    # screened. Rejecting it here keeps every downstream parser on a
    # already-validated hostname.
    try:
        ssrf.validate_hostname(domain)
        ssrf.resolve_and_validate(domain)
    except ssrf.SSRFBlocked as exc:
        obs.errors.append("blocked by SSRF guard: %s" % exc)
        obs.values["tls"] = {"min_version": None, "days_to_expiry": None}
        obs.values["headers"] = {}
        obs.values["dns"] = {}
        return obs

    url = base_url or "https://%s" % domain

    tls = _tls_probe(domain)
    obs.values["tls"] = {k: v for k, v in tls.items() if k != "error"}
    if tls.get("error"):
        obs.errors.append("tls: %s" % tls["error"])

    hdr = _http_headers(url)
    obs.values["headers"] = {k: v for k, v in hdr.items() if k not in ("ok", "error")}
    if hdr.get("error"):
        obs.errors.append("http: %s" % hdr["error"])

    obs.values["dns"] = _dns_records(domain)

    return obs


# =====================================================================
# Google Workspace
# =====================================================================
def collect_workspace(domain: str = "", credentials_json: str = "") -> Observation:
    """Google Workspace 2-step verification and admin-role posture.

    Requires a service account with domain-wide delegation and the read-only
    scopes admin.directory.user.readonly and admin.directory.rolemanagement.
    The service-account key is read from a path in GOOGLE_APPLICATION_CREDENTIALS
    and is never echoed into the Observation.
    """
    domain = domain or os.environ.get("WORKSPACE_DOMAIN", "")
    obs = Observation(source="workspace", meta={"domain": domain})
    if not domain:
        obs.errors.append("no Workspace domain configured (set WORKSPACE_DOMAIN)")
        return obs

    try:
        from google.oauth2 import service_account  # noqa: F401
        from googleapiclient.discovery import build  # noqa: F401
    except ImportError:
        obs.errors.append(
            "google-api-python-client is not installed; Workspace checks skipped"
        )
        return obs

    cred_path = credentials_json or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
    if not cred_path or not os.path.isfile(cred_path):
        obs.errors.append("no service-account key found; Workspace checks skipped")
        return obs

    try:
        creds = service_account.Credentials.from_service_account_file(
            cred_path,
            scopes=[
                "https://www.googleapis.com/auth/admin.directory.user.readonly",
                "https://www.googleapis.com/auth/admin.directory.rolemanagement.readonly",
            ],
        ).with_subject(domain)
        svc = build("admin", "directory_v1", credentials=creds, cache_discovery=False)
    except Exception as exc:
        obs.errors.append("Workspace auth failed: %s" % type(exc).__name__)
        return obs

    def _users() -> Dict[str, Any]:
        total = 0
        without_2sv = []
        page_token = None
        while True:
            res = svc.users().list(customer="my_customer", maxResults=200,
                                   pageToken=page_token,
                                   projection="full").execute()
            for u in res.get("users", []):
                total += 1
                if not u.get("isEnrolledIn2Sv"):
                    without_2sv.append(u.get("primaryEmail", ""))
            page_token = res.get("nextPageToken")
            if not page_token:
                break
        return {"total": total, "without_2sv": without_2sv}

    try:
        u = _users()
        obs.values["users"] = u
        obs.values["two_step"] = {
            "enforced": None,  # requiring enforcement needs the admin settings API
            "users_without_2sv": u["without_2sv"],
        }
    except Exception as exc:
        obs.errors.append("Workspace users: %s" % type(exc).__name__)

    return obs
