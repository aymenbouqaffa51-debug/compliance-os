"""Framework loading and the client workspace store.

Everything is plain files on disk under a workspace directory:

    workspace/
      clients/<slug>/client.json
      clients/<slug>/assessments/<framework-id>.json
      clients/<slug>/reports/...

No database. A client workspace is a folder you can zip, back up, hand over,
and delete -- which is what makes the CNDP story (data minimisation, retention,
deletion on exit) true rather than aspirational.

Durability: every write is atomic (temp file in the same directory, fsync, then
os.replace). A crash mid-write cannot leave a truncated client.json.

Safety: every slug and path component is validated against a strict pattern.
A slug is user input, so it is treated as hostile until proven otherwise.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from typing import Any, Dict, List, Optional

import yaml

from compliance_os.models import Assessment, Client, Framework, SCHEMA_VERSION

FRAMEWORK_DIR = os.path.join(os.path.dirname(__file__), "data", "frameworks")

# A slug is a directory name. Lowercase alphanumerics and single hyphens only.
_SLUG_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,62})$")


class ComplianceError(Exception):
    pass


class SchemaError(ComplianceError):
    pass


# --------------------------------------------------------------- frameworks
_cache: Dict[str, Framework] = {}


def framework_ids() -> List[str]:
    if not os.path.isdir(FRAMEWORK_DIR):
        return []
    return sorted(
        os.path.splitext(fn)[0]
        for fn in os.listdir(FRAMEWORK_DIR)
        if fn.endswith((".yaml", ".yml"))
    )


def load_framework(fid: str) -> Framework:
    if fid in _cache:
        return _cache[fid]
    if not re.match(r"^[a-zA-Z0-9._-]+$", fid or ""):
        raise ComplianceError("invalid framework id: %r" % fid)
    for ext in (".yaml", ".yml"):
        path = os.path.join(FRAMEWORK_DIR, fid + ext)
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                fw = Framework.from_dict(yaml.safe_load(f))
            _cache[fid] = fw
            return fw
    raise ComplianceError(
        "Unknown framework %r. Available: %s" % (fid, ", ".join(framework_ids()))
    )


def reload_frameworks() -> None:
    _cache.clear()


# ------------------------------------------------------------------ slugs
def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").strip().lower())
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return (s or "client")[:63]


def validate_slug(slug: str) -> str:
    """Reject anything that is not a clean, safe directory name."""
    if not slug or not isinstance(slug, str):
        raise ComplianceError("slug must be a non-empty string")
    if not _SLUG_RE.match(slug):
        raise ComplianceError(
            "invalid slug %r: use lowercase letters, digits and single hyphens" % slug
        )
    if slug in (".", "..") or slug.startswith("-"):
        raise ComplianceError("invalid slug %r" % slug)
    return slug


# ------------------------------------------------------------- atomic write
def atomic_write_text(path: str, text: str) -> None:
    """Write text durably: temp file in same dir, fsync, then os.replace.

    Same-directory temp file means os.replace is atomic (same filesystem).
    """
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".tmp-", suffix=".part")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def atomic_write_json(path: str, obj: Any) -> None:
    atomic_write_text(path, json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=False) + "\n")


def read_json(path: str) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def check_schema(data: Dict[str, Any], path: str) -> None:
    """Refuse to silently misread a workspace written by a newer version."""
    found = data.get("schema_version", 1)
    if isinstance(found, int) and found > SCHEMA_VERSION:
        raise SchemaError(
            "%s was written by a newer version (schema %s > %s). "
            "Upgrade compliance-os before opening it." % (path, found, SCHEMA_VERSION)
        )


# ---------------------------------------------------------------- workspace
class Workspace:
    def __init__(self, root: str):
        self.root = os.path.abspath(root)

    @property
    def clients_dir(self) -> str:
        return os.path.join(self.root, "clients")

    def client_dir(self, slug: str) -> str:
        return os.path.join(self.clients_dir, validate_slug(slug))

    def client_file(self, slug: str) -> str:
        return os.path.join(self.client_dir(slug), "client.json")

    def assessments_dir(self, slug: str) -> str:
        return os.path.join(self.client_dir(slug), "assessments")

    def reports_dir(self, slug: str) -> str:
        return os.path.join(self.client_dir(slug), "reports")

    def init(self) -> None:
        os.makedirs(self.clients_dir, exist_ok=True)

    def list_clients(self) -> List[str]:
        if not os.path.isdir(self.clients_dir):
            return []
        return sorted(
            d for d in os.listdir(self.clients_dir)
            if os.path.isfile(os.path.join(self.clients_dir, d, "client.json"))
        )

    def create_client(self, legal_name: str, **kwargs) -> Client:
        slug = validate_slug(kwargs.pop("slug", None) or slugify(legal_name))
        if os.path.isdir(self.client_dir(slug)):
            raise ComplianceError("Client %r already exists" % slug)
        client = Client(slug=slug, legal_name=legal_name, **kwargs)
        self.save_client(client)
        return client

    def save_client(self, client: Client) -> None:
        validate_slug(client.slug)
        atomic_write_json(self.client_file(client.slug), client.data)

    def load_client(self, slug: str) -> Client:
        p = self.client_file(slug)
        if not os.path.isfile(p):
            raise ComplianceError(
                "Unknown client %r. Known: %s"
                % (slug, ", ".join(self.list_clients()) or "(none)")
            )
        data = read_json(p)
        check_schema(data, p)
        return Client.from_dict(data)

    def delete_client(self, slug: str) -> None:
        d = self.client_dir(slug)
        if not os.path.isdir(d):
            raise ComplianceError("Unknown client %r" % slug)
        shutil.rmtree(d)

    def assessment_file(self, slug: str, fid: str) -> str:
        if not re.match(r"^[a-zA-Z0-9._-]+$", fid or ""):
            raise ComplianceError("invalid framework id: %r" % fid)
        return os.path.join(self.assessments_dir(slug), fid + ".json")

    def load_assessment(self, slug: str, fid: str) -> Assessment:
        p = self.assessment_file(slug, fid)
        if os.path.isfile(p):
            data = read_json(p)
            check_schema(data, p)
            return Assessment.from_dict(data)
        return Assessment(client_slug=slug, framework_id=fid)

    def save_assessment(self, a: Assessment) -> None:
        import datetime as _dt
        a.updated_at = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        atomic_write_json(self.assessment_file(a.client_slug, a.framework_id), a.to_dict())

    def list_assessments(self, slug: str) -> List[str]:
        d = self.assessments_dir(slug)
        if not os.path.isdir(d):
            return []
        return sorted(os.path.splitext(f)[0] for f in os.listdir(d) if f.endswith(".json"))
