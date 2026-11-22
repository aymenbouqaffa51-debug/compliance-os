"""Test suite. Run with:  python3 -m pytest tests/ -v
or without pytest:       python3 tests/test_engine.py
"""

import os
import sys
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from compliance_os import registry, scoring
from compliance_os.models import (
    STATE_GAP, STATE_IMPLEMENTED, STATE_NOT_APPLICABLE, STATE_PARTIAL,
)


def _ws():
    d = tempfile.mkdtemp()
    ws = registry.Workspace(d)
    ws.init()
    return ws, d


def test_frameworks_load():
    ids = registry.framework_ids()
    assert len(ids) == 4, ids
    for fid in ids:
        fw = registry.load_framework(fid)
        assert fw.controls, fid
        assert fw.name, fid
    return True


def test_control_ids_unique():
    for fid in registry.framework_ids():
        fw = registry.load_framework(fid)
        ids = [c.id for c in fw.controls]
        assert len(ids) == len(set(ids)), "duplicate ids in %s" % fid
    return True


def test_no_dangling_crossmap_references():
    """Every maps_to target must resolve to a control that actually ships.

    This was a real defect: 19 references pointed at controls that were never
    loaded, which silently degraded the cross-framework evidence feature.
    """
    all_ids = set()
    for fid in registry.framework_ids():
        all_ids |= {c.id for c in registry.load_framework(fid).controls}

    dangling = []
    for fid in registry.framework_ids():
        for c in registry.load_framework(fid).controls:
            for target in c.maps_to:
                if target not in all_ids:
                    dangling.append("%s/%s -> %s" % (fid, c.id, target))
    assert not dangling, "dangling cross-map references: %r" % dangling
    return True


def test_crossmaps_are_bidirectional():
    """If A maps to B, then B should map back to A.

    Bidirectional mapping is what lets one evidence item satisfy both an ISO
    auditor and a CNDP form. A one-way map means evidence attached to one
    control never lights up its counterpart.
    """
    by_id = {}
    for fid in registry.framework_ids():
        for c in registry.load_framework(fid).controls:
            by_id[c.id] = c

    one_way = []
    for cid, control in by_id.items():
        for target in control.maps_to:
            other = by_id.get(target)
            if other is None:
                continue  # covered by the dangling test
            if cid not in other.maps_to:
                one_way.append("%s -> %s (no reverse)" % (cid, target))

    # Report the count rather than failing on any single omission: our shipped
    # selection is partial and some one-way links are intentional (an ISO
    # control may reference a Moroccan control that is coarser-grained).
    total_links = sum(len(c.maps_to) for c in by_id.values())
    ratio = 1.0 - (len(one_way) / total_links if total_links else 0.0)
    print("    cross-map links: %d, bidirectional: %.0f%%" % (total_links, ratio * 100))
    assert ratio >= 0.80, (
        "only %.0f%% of cross-map links are bidirectional (%d one-way). "
        "Examples: %r" % (ratio * 100, len(one_way), one_way[:5])
    )
    return True


def test_moroccan_crossmaps_exist():
    """At least some ISO controls must reach the Moroccan layer."""
    ma = set()
    for fid in ("loi-09-08", "loi-05-20"):
        ma |= {c.id for c in registry.load_framework(fid).controls}
    assert ma, "no Moroccan controls"
    iso = registry.load_framework("iso-27001-2022")
    mapped = 0
    for c in iso.controls:
        for target in c.maps_to:
            if target.startswith("MA"):
                assert target in ma, "%s maps to missing %s" % (c.id, target)
                mapped += 1
    assert mapped >= 15, "only %d ISO->MA mappings" % mapped
    return True


def test_not_applicable_excluded_from_denominator():
    ws, d = _ws()
    try:
        client = ws.create_client("Minimal SARL", headcount="5",
                                  handles_sensitive_data=False, handles_cin=False)
        fw = registry.load_framework("loi-09-08")
        a = ws.load_assessment(client.slug, fw.id)
        for c in fw.controls:
            a.row(c.id).state = STATE_IMPLEMENTED
        ws.save_assessment(a)
        s = scoring.score(fw, client, a)
        assert s.pct == 100.0, "all implemented should be 100%%, got %.1f" % s.pct

        # Now mark one high-weight control not_applicable: it must leave the
        # denominator, so a fully-implemented remainder stays at 100%.
        a.row("MA09-08-06").state = STATE_NOT_APPLICABLE
        ws.save_assessment(a)
        s2 = scoring.score(fw, client, a)
        assert s2.pct == 100.0, (
            "not_applicable must not reduce the score, got %.1f" % s2.pct)
        return True
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_weighting_changes_score():
    ws, d = _ws()
    try:
        client = ws.create_client("Weight SARL", headcount="40")
        fw = registry.load_framework("loi-09-08")
        a = ws.load_assessment(client.slug, fw.id)
        # Mark everything implemented except the heaviest control, which is a gap
        heaviest = max(fw.controls, key=lambda c: c.weight)
        for c in fw.controls:
            a.row(c.id).state = STATE_IMPLEMENTED
        a.row(heaviest.id).state = STATE_GAP
        ws.save_assessment(a)
        s = scoring.score(fw, client, a)
        # Losing a weight-3 control must cost more than losing a weight-1 one
        a2 = ws.load_assessment(client.slug, fw.id)
        a2.row(heaviest.id).state = STATE_IMPLEMENTED
        lightest = min(fw.controls, key=lambda c: c.weight)
        a2.row(lightest.id).state = STATE_GAP
        ws.save_assessment(a2)
        s2 = scoring.score(fw, client, a2)
        assert s2.pct > s.pct, (
            "gapping a light control (%.1f%%) should score better than "
            "gapping a heavy one (%.1f%%)" % (s2.pct, s.pct))
        return True
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_conditional_control_applies_on_cin():
    """The CNDP art.12 control must apply only when CIN is processed."""
    ws, d = _ws()
    try:
        plain = ws.create_client("No CIN SARL", handles_cin=False, handles_sensitive_data=False)
        with_cin = ws.create_client("Has CIN SARL", handles_cin=True)
        fw = registry.load_framework("loi-09-08")

        r_plain = {r["control"].id: r["applies"] for r in scoring.resolve(fw, plain)}
        r_cin = {r["control"].id: r["applies"] for r in scoring.resolve(fw, with_cin)}

        assert r_plain["MA09-08-02"] is False, "art.12 control should not apply without CIN"
        assert r_cin["MA09-08-02"] is True, "art.12 control must apply with CIN"
        # A non-conditional control applies to both
        assert r_plain["MA09-08-03"] is True
        assert r_cin["MA09-08-03"] is True
        return True
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_partial_scores_half():
    ws, d = _ws()
    try:
        client = ws.create_client("Partial SARL", headcount="20")
        fw = registry.load_framework("loi-05-20")
        a = ws.load_assessment(client.slug, fw.id)
        for c in fw.controls:
            a.row(c.id).state = STATE_PARTIAL
        ws.save_assessment(a)
        s = scoring.score(fw, client, a)
        assert 49.0 <= s.pct <= 51.0, "all-partial should be ~50%%, got %.1f" % s.pct
        return True
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_gap_report_generates():
    ws, d = _ws()
    try:
        from compliance_os.report import write_gap_report
        client = ws.create_client("Report SARL", sector="SaaS", headcount="42", handles_cin=True)
        fw = registry.load_framework("loi-09-08")
        a = ws.load_assessment(client.slug, fw.id)
        a.row("MA09-08-01").state = STATE_IMPLEMENTED
        a.row("MA09-08-02").state = STATE_GAP
        a.row("MA09-08-02").notes = "Autorisation absente"
        ws.save_assessment(a)
        os.makedirs(ws.reports_dir(client.slug), exist_ok=True)
        path = write_gap_report(ws, client, fw, a, lang="fr")
        assert os.path.isfile(path)
        body = open(path, encoding="utf-8").read()
        assert "MA09-08-02" in body
        assert "Rapport d" in body
        assert "Autorisation absente" in body
        assert "certification" in body.lower()
        return True
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_client_roundtrip():
    ws, d = _ws()
    try:
        c = ws.create_client("Round Trip SARL", sector="Fintech", headcount="88",
                             export_markets=["France", "Germany"], handles_cin=True)
        c2 = ws.load_client(c.slug)
        assert c2.legal_name == c.legal_name
        assert c2.handles_cin is True
        assert c2.export_markets == ["France", "Germany"]
        assert ws.list_clients() == [c.slug]
        return True
    finally:
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    tests = [(k, v) for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    passed = failed = 0
    for name, fn in tests:
        try:
            fn()
            print("  PASS  %s" % name)
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
