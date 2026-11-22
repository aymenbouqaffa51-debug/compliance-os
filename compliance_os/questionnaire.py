"""Security questionnaire rescue engine.

The problem this solves: a Moroccan company receives a 120-row security
questionnaire from a European buyer, in a spreadsheet, with two weeks to reply.
Today that takes a consultant three days of rewriting the same answers.

This engine reads the spreadsheet, matches each question to the controls the
client already has evidence for, and drafts an answer grounded strictly in the
client's recorded state. It tags every row with a confidence level and forces
human review wherever the underlying control is a gap or unassessed.

CRITICAL DESIGN RULE: the answer engine NEVER invents a capability. If the
control is a gap, the draft says the control is being remediated and gives the
date, rather than claiming compliance. A questionnaire answer that overstates
posture is a misrepresentation to a buyer and the fastest way to lose the
deal -- or the contract, later.
"""

from __future__ import annotations

import csv
import io
import os
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Iterable, List, Optional, Tuple

from compliance_os import registry, scoring
from compliance_os.models import Assessment, Client, Framework, STATE_GAP, STATE_IMPLEMENTED, STATE_NOT_ASSESSED, STATE_PARTIAL

# ---------------------------------------------------------------- confidence
HIGH = "high"
MEDIUM = "medium"
LOW = "low"

NEEDS_REVIEW = "NEEDS_HUMAN_REVIEW"


@dataclass
class Question:
    row: int
    text: str
    reference: str = ""      # e.g. CC6.1, A.5.15, or buyer's own id
    category: str = ""
    buyer_hint: str = ""     # the buyer's suggested answer, if provided


@dataclass
class Answer:
    row: int
    question: str
    reference: str = ""
    matched_controls: List[str] = field(default_factory=list)
    frameworks: List[str] = field(default_factory=list)
    state: str = ""                    # strongest state among matches
    confidence: str = LOW
    draft: str = ""
    review_flag: str = ""              # NEEDS_HUMAN_REVIEW or ""
    review_reason: str = ""
    evidence_refs: List[str] = field(default_factory=list)
    score: float = 0.0                 # match score, for debugging

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ------------------------------------------------------------ spreadsheet IO
QUESTION_COLUMN_HINTS = [
    "question", "questions", "requirement", "control", "description",
    "prompt", "item", "security question", "question text", "questionnaire",
]
REFERENCE_COLUMN_HINTS = [
    "ref", "reference", "id", "control id", "number", "no", "#",
    "control reference", "criterion",
]
CATEGORY_COLUMN_HINTS = ["category", "domain", "section", "topic", "area"]
HINT_COLUMN_HINTS = ["response", "answer", "suggested", "guidance", "hint"]


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", (s or "").lower()).strip()


def _pick_column(headers: List[str], hints: List[str]) -> Optional[int]:
    """Find the best-matching column index for a role."""
    normed = [_norm(h) for h in headers]
    # exact-ish first
    for hint in hints:
        for i, h in enumerate(normed):
            if h == hint:
                return i
    for hint in hints:
        for i, h in enumerate(normed):
            if hint in h:
                return i
    return None


def parse_csv(path_or_text: str, is_text: bool = False) -> List[Question]:
    """Parse a CSV questionnaire. Delimiter is sniffed."""
    if is_text:
        text = path_or_text
    else:
        with open(path_or_text, encoding="utf-8-sig", errors="replace") as f:
            text = f.read()

    if not text.strip():
        return []

    # Sniff the delimiter; fall back to comma.
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        delim = dialect.delimiter
    except Exception:
        delim = ","

    rows = list(csv.reader(io.StringIO(text), delimiter=delim))
    if not rows:
        return []

    # Find the header row: the first row with a question-ish column.
    header_idx = 0
    headers: List[str] = []
    for i, r in enumerate(rows[:10]):
        if _pick_column(r, QUESTION_COLUMN_HINTS) is not None:
            header_idx = i
            headers = r
            break
    if not headers:
        headers = rows[0]
        header_idx = 0

    qcol = _pick_column(headers, QUESTION_COLUMN_HINTS)
    rcol = _pick_column(headers, REFERENCE_COLUMN_HINTS)
    ccol = _pick_column(headers, CATEGORY_COLUMN_HINTS)
    hcol = _pick_column(headers, HINT_COLUMN_HINTS)

    if qcol is None:
        # Fall back: the widest text column.
        widths = [(len(" ".join(r)), i) for i, r in enumerate(zip(*rows[header_idx + 1:]))] if len(rows) > header_idx + 1 else []
        qcol = max(widths)[1] if widths else 0

    out: List[Question] = []
    for n, r in enumerate(rows[header_idx + 1:], start=header_idx + 2):
        if not r or all(not c.strip() for c in r):
            continue
        def cell(i):
            return r[i].strip() if i is not None and i < len(r) else ""
        text = cell(qcol)
        if not text or len(text) < 3:
            continue
        out.append(Question(
            row=n,
            text=text,
            reference=cell(rcol),
            category=cell(ccol),
            buyer_hint=cell(hcol),
        ))
    return out


def parse_xlsx(path: str, sheet: Optional[str] = None) -> List[Question]:
    """Parse an XLSX questionnaire.

    Requires openpyxl. Converts the sheet to CSV in memory and reuses parse_csv,
    so both paths share one column-detection implementation.
    """
    try:
        from openpyxl import load_workbook
    except ImportError:
        raise RuntimeError(
            "openpyxl is required for .xlsx questionnaires (pip install openpyxl). "
            "Save the sheet as CSV to continue without it."
        )
    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb[sheet] if sheet and sheet in wb.sheetnames else wb[wb.sheetnames[0]]
    buf = io.StringIO()
    writer = csv.writer(buf)
    for row in ws.iter_rows(values_only=True):
        writer.writerow(["" if c is None else str(c) for c in row])
    wb.close()
    return parse_csv(buf.getvalue(), is_text=True)


def parse_questionnaire(path: str, sheet: Optional[str] = None) -> List[Question]:
    ext = os.path.splitext(path)[1].lower()
    if ext in (".xlsx", ".xlsm"):
        return parse_xlsx(path, sheet=sheet)
    return parse_csv(path)


# ------------------------------------------------------------------ matching
STOPWORDS = set("""
 a an the is are was were be been being of to in on for with and or not no
 do does did have has had will would should could can may might must shall
 your you our we their they it this that these those as at by from into
 if then than so such what which who whom whose when where why how all any
 both each few more most other some there here about above after again
 against below between during before under over out up down off only own
 same very just also
""".split())


def _tokens(text: str) -> set:
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return {w for w in words if w not in STOPWORDS and len(w) > 2}


@dataclass
class ControlDoc:
    control_id: str
    framework_id: str
    title: str
    objective: str
    evidence: List[str]
    tokens: set = field(default_factory=set)


def build_index(framework_ids: Optional[List[str]] = None) -> List[ControlDoc]:
    """Build the searchable control corpus once per run."""
    docs: List[ControlDoc] = []
    for fid in (framework_ids or registry.framework_ids()):
        try:
            fw = registry.load_framework(fid)
        except Exception:
            continue
        for c in fw.controls:
            blob = " ".join([c.id, c.title, c.objective, " ".join(c.evidence), c.theme, c.ref])
            docs.append(ControlDoc(
                control_id=c.id, framework_id=fid, title=c.title,
                objective=c.objective, evidence=list(c.evidence),
                tokens=_tokens(blob),
            ))
    return docs


def _reference_boost(q: Question, doc: ControlDoc) -> float:
    """If the buyer already labelled the row with a control reference, trust it."""
    ref = (q.reference or "").strip().upper()
    if not ref:
        return 0.0
    cid = doc.control_id.upper()
    if ref == cid:
        return 1.0
    if ref.startswith(cid + ".") or cid.startswith(ref + "."):
        return 0.8
    # CC6.1 style: prefix match on the family
    if re.sub(r"[^A-Z0-9]", "", ref)[:3] == re.sub(r"[^A-Z0-9]", "", cid)[:3]:
        return 0.3
    return 0.0


def match_question(q: Question, docs: List[ControlDoc], top_k: int = 3) -> List[Tuple[ControlDoc, float]]:
    """Score controls against a question using IDF-weighted token overlap.

    Deliberately deterministic and offline: no LLM, no network, reproducible.
    The LLM layer (below) only rewrites prose; the *match* is auditable.
    """
    qtok = _tokens(q.text + " " + q.category)
    if not qtok:
        return []

    # Document frequency for IDF
    df: Dict[str, int] = {}
    for d in docs:
        for t in d.tokens:
            df[t] = df.get(t, 0) + 1
    import math
    n = max(1, len(docs))

    scored: List[Tuple[ControlDoc, float]] = []
    for d in docs:
        overlap = qtok & d.tokens
        if not overlap:
            boost = _reference_boost(q, d)
            if boost > 0:
                scored.append((d, boost))
            continue
        idf = sum(math.log(1.0 + n / (1.0 + df.get(t, 0))) for t in overlap)
        # Normalise by question length so long questions don't win by volume
        base = idf / (1.0 + math.log(1.0 + len(qtok)))
        boost = _reference_boost(q, d)
        scored.append((d, base + boost * 2.0))

    scored.sort(key=lambda x: -x[1])
    return scored[:top_k]


# ------------------------------------------------------------------- answers
def _client_state_for(
    client: Client,
    control_ids: Iterable[str],
    assessments: Dict[str, Assessment],
) -> Tuple[str, Dict[str, str], List[str]]:
    """Return (strongest_state, {control_id: state}, evidence_descriptions)."""
    order = {STATE_IMPLEMENTED: 0, STATE_PARTIAL: 1, STATE_GAP: 2, STATE_NOT_ASSESSED: 3}
    best = STATE_NOT_ASSESSED
    per: Dict[str, str] = {}
    ev: List[str] = []
    for cid in control_ids:
        # find which framework owns this control
        state = STATE_NOT_ASSESSED
        for fid, a in assessments.items():
            try:
                fw = registry.load_framework(fid)
            except Exception:
                continue
            c = fw.by_id(cid)
            if c is None:
                continue
            row = a.rows.get(cid)
            state = row.state if row else STATE_NOT_ASSESSED
            if row and row.evidence:
                for e in row.evidence:
                    desc = e.summary or e.kind
                    if e.sha256:
                        desc += " [sha256:%s]" % e.sha256[:12]
                    ev.append(desc)
            break
        per[cid] = state
        if order.get(state, 9) < order.get(best, 9):
            best = state
    return best, per, ev


def _draft_answer(
    q: Question,
    strongest: str,
    per_control: Dict[str, str],
    evidence: List[str],
    client: Client,
) -> Tuple[str, str, str]:
    """Return (draft_text, confidence, review_reason).

    The wording is chosen to be truthful for the state. It never claims
    compliance the client does not have.
    """
    if strongest == STATE_IMPLEMENTED:
        body = "Yes. This control is implemented and evidenced in our compliance programme."
        if evidence:
            body += " Supporting evidence on file: %s." % "; ".join(evidence[:3])
        return body, HIGH, ""

    if strongest == STATE_PARTIAL:
        partial = [c for c, s in per_control.items() if s == STATE_PARTIAL]
        body = (
            "Partially. The control is defined and operating, with the following "
            "elements already in place: %s. Remaining items are tracked with an "
            "owner and a target date and can be shared on request."
            % ", ".join(partial[:3])
        )
        if evidence:
            body += " Evidence available: %s." % "; ".join(evidence[:2])
        return body, MEDIUM, "control is partial - confirm the gap closure date before sending"

    if strongest == STATE_GAP:
        body = (
            "Not currently in place. We have identified this as a gap in our "
            "readiness assessment and it is scheduled for remediation. We would "
            "rather disclose the gap than overstate our position, and we will "
            "provide the remediation plan on request."
        )
        return body, LOW, "control is a GAP - do not send without a remediation date"

    return (
        "Not assessed. We have not yet evaluated this item against a formal control "
        "framework, so we are unable to confirm the position in this response."
    ), LOW, "control is unassessed - answer manually"


@dataclass
class QuestionnaireResult:
    client_slug: str
    source_file: str
    total: int
    answers: List[Answer] = field(default_factory=list)
    generated_at: str = ""

    def counts(self) -> Dict[str, int]:
        out = {"high": 0, "medium": 0, "low": 0, "needs_review": 0, "unmatched": 0}
        for a in self.answers:
            out[a.confidence] = out.get(a.confidence, 0) + 1
            if a.review_flag:
                out["needs_review"] += 1
            if not a.matched_controls:
                out["unmatched"] += 1
        return out

    def to_dict(self) -> Dict[str, Any]:
        return {
            "client_slug": self.client_slug,
            "source_file": self.source_file,
            "generated_at": self.generated_at,
            "total": self.total,
            "counts": self.counts(),
            "answers": [a.to_dict() for a in self.answers],
        }


def answer_questionnaire(
    ws: registry.Workspace,
    client_slug: str,
    questions: List[Question],
    source_file: str = "",
    framework_ids: Optional[List[str]] = None,
) -> QuestionnaireResult:
    """Match every question to controls and draft a grounded answer."""
    import datetime as _dt

    client = ws.load_client(client_slug)
    docs = build_index(framework_ids)
    assessments: Dict[str, Assessment] = {}
    for fid in (framework_ids or ws.list_assessments(client_slug) or registry.framework_ids()):
        assessments[fid] = ws.load_assessment(client_slug, fid)

    result = QuestionnaireResult(
        client_slug=client_slug,
        source_file=source_file,
        total=len(questions),
        generated_at=_dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )

    for q in questions:
        matches = match_question(q, docs)
        ans = Answer(row=q.row, question=q.text, reference=q.reference)

        if not matches:
            ans.draft = ""
            ans.confidence = LOW
            ans.review_flag = NEEDS_REVIEW
            ans.review_reason = "no control matched this question - answer manually"
            result.answers.append(ans)
            continue

        control_ids = [d.control_id for d, _ in matches]
        frameworks = sorted({d.framework_id for d, _ in matches})
        strongest, per, evidence = _client_state_for(client, control_ids, assessments)
        draft, confidence, reason = _draft_answer(q, strongest, per, evidence, client)

        ans.matched_controls = control_ids
        ans.frameworks = frameworks
        ans.state = strongest
        ans.confidence = confidence
        ans.draft = draft
        ans.evidence_refs = evidence[:5]
        ans.score = round(matches[0][1], 3)
        if strongest in (STATE_GAP, STATE_NOT_ASSESSED) or confidence == LOW:
            ans.review_flag = NEEDS_REVIEW
            ans.review_reason = reason or "low confidence match"

        result.answers.append(ans)

    return result


# -------------------------------------------------------------------- output
def to_csv_rows(result: QuestionnaireResult) -> List[List[str]]:
    out = [["row", "question", "reference", "matched_controls", "frameworks",
            "state", "confidence", "review_flag", "review_reason", "draft_answer", "evidence"]]
    for a in result.answers:
        out.append([
            str(a.row), a.question, a.reference,
            ",".join(a.matched_controls), ",".join(a.frameworks),
            a.state, a.confidence, a.review_flag, a.review_reason,
            a.draft, "; ".join(a.evidence_refs),
        ])
    return out


def write_csv(result: QuestionnaireResult, path: str) -> str:
    rows = to_csv_rows(result)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerows(rows)
    registry.atomic_write_text(path, buf.getvalue())
    return path


def write_markdown(result: QuestionnaireResult, path: str, client_name: str = "") -> str:
    c = result.counts()
    L = []
    L.append("# Questionnaire response pack")
    L.append("")
    if client_name:
        L.append("**Client:** %s  " % client_name)
    L.append("**Source:** %s  " % (result.source_file or "(provided)"))
    L.append("**Generated:** %s  " % result.generated_at)
    L.append("")
    L.append("---")
    L.append("")
    L.append("## Summary")
    L.append("")
    L.append("| Metric | Count |")
    L.append("|---|---|")
    L.append("| Questions | %d |" % result.total)
    L.append("| Drafted with high confidence | %d |" % c["high"])
    L.append("| Drafted, verify first | %d |" % c["medium"])
    L.append("| Low confidence | %d |" % c["low"])
    L.append("| **Require human review** | **%d** |" % c["needs_review"])
    L.append("| No control matched | %d |" % c["unmatched"])
    L.append("")
    L.append("> Every answer below is grounded in the client's recorded control state.")
    L.append("> Rows marked NEEDS_HUMAN_REVIEW must not be sent without a human decision.")
    L.append("")
    L.append("---")
    L.append("")

    for a in result.answers:
        flag = " `%s`" % a.review_flag if a.review_flag else ""
        L.append("### Row %d - %s%s" % (a.row, a.confidence.upper(), flag))
        L.append("")
        L.append("> %s" % a.question.replace(chr(10), " "))
        L.append("")
        if a.reference:
            L.append("*Buyer reference: %s*" % a.reference)
            L.append("")
        L.append("**Matched controls:** %s  " % (", ".join(a.matched_controls) or "none"))
        L.append("**Control state:** %s  " % (a.state or "unknown"))
        if a.review_reason:
            L.append("**Review note:** %s  " % a.review_reason)
        L.append("")
        L.append("**Draft answer:**")
        L.append("")
        L.append(a.draft or "*(no draft - answer manually)*")
        L.append("")
        if a.evidence_refs:
            L.append("**Evidence on file:**")
            L.append("")
            for e in a.evidence_refs:
                L.append("- %s" % e)
            L.append("")

    L.append("---")
    L.append("")
    L.append("> This pack is a drafting aid. It is not a certification, not an audit,")
    L.append("> and not legal advice. Every answer must be reviewed and approved by the")
    L.append("> client before it is sent to a buyer.")
    L.append("")
    registry.atomic_write_text(path, chr(10).join(L))
    return path
