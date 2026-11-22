"""Grounded compliance agent.

WHAT THIS IS
------------
An assistant that answers questions about a client's compliance position by
RETRIEVING the facts from the database and then composing an answer from those
facts. It is not a chatbot that improvises.

WHY THE DESIGN IS THIS WAY
--------------------------
A compliance assistant that hallucinates is worse than no assistant. If it says
"your encryption control passes" and the register says `gap`, the client repeats
that to their auditor and the engagement is over. So:

  1. Every answer is built from a `ContextBundle` of retrieved facts.
  2. Every claim carries a citation id (`control:A.8.24`, `score:iso-27001-2022`).
  3. If the facts do not support an answer, the agent says so and routes the
     user to the right screen instead of guessing.
  4. The LLM layer, when configured, may only REWRITE the composed answer --
     it never selects the facts. If it is unavailable, the deterministic path
     produces the full answer on its own.

That last point matters commercially: the product must work with no API key, so
a self-hosted deployment in Morocco does not depend on a US LLM provider being
reachable or on a CNDP transfer authorisation being granted.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

__all__ = [
    "ContextBundle",
    "AgentAnswer",
    "Citation",
    "build_context",
    "answer_question",
    "SUGGESTED_QUESTIONS",
]


# --------------------------------------------------------------------- models
@dataclass
class Citation:
    """A reference to a fact the answer relies on."""

    kind: str            # control | score | monitor | policy | questionnaire | client
    ref: str             # e.g. "A.8.24", "iso-27001-2022", "PER-01"
    label: str = ""

    def to_dict(self) -> Dict[str, str]:
        return {"kind": self.kind, "ref": self.ref, "label": self.label}


@dataclass
class ContextBundle:
    """Everything the agent is allowed to know about one client."""

    client_slug: str = ""
    legal_name: str = ""
    sector: str = ""
    headcount: str = ""
    hosting_country: str = "France"
    is_public_entity: bool = False
    is_iiv: bool = False
    handles_cin: bool = False
    handles_sensitive_data: bool = False

    scores: List[Dict[str, Any]] = field(default_factory=list)
    gaps: List[Dict[str, Any]] = field(default_factory=list)
    partials: List[Dict[str, Any]] = field(default_factory=list)
    unassessed_count: int = 0
    implemented_count: int = 0

    monitor_score: Optional[float] = None
    monitor_failing: List[Dict[str, Any]] = field(default_factory=list)
    monitor_drift: List[Dict[str, Any]] = field(default_factory=list)
    monitor_last_run: str = ""

    policy_current: List[Dict[str, Any]] = field(default_factory=list)
    policy_ack_total: int = 0

    questionnaire_total: int = 0
    questionnaire_needs_review: int = 0

    evidence_total: int = 0

    @property
    def has_data(self) -> bool:
        return bool(self.scores or self.monitor_score is not None)

    def to_dict(self) -> Dict[str, Any]:
        d = {}
        for k in self.__dataclass_fields__:
            v = getattr(self, k)
            d[k] = v
        return d


@dataclass
class AgentAnswer:
    text: str
    citations: List[Citation] = field(default_factory=list)
    intent: str = "unknown"
    grounded: bool = True
    follow_ups: List[str] = field(default_factory=list)
    used_llm: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "citations": [c.to_dict() for c in self.citations],
            "intent": self.intent,
            "grounded": self.grounded,
            "follow_ups": self.follow_ups,
            "used_llm": self.used_llm,
        }


SUGGESTED_QUESTIONS = [
    "What are my biggest gaps right now?",
    "Are we ready for an ISO 27001 audit?",
    "What failed in the last monitor run?",
    "Has anything regressed since last week?",
    "Which policies still need acknowledgement?",
    "What should I fix first?",
    "Are we allowed to host client data in France?",
    "What does Law 05-20 require of us?",
]


# ------------------------------------------------------------------- intents
_INTENTS: List[Tuple[str, re.Pattern]] = [
    ("gaps", re.compile(
        r"\b(gaps?|missing|not (?:done|implemented)|fail(?:s|ing|ed)?|weak(?:est)?|"
        r"problems?|issues?|risks?|behind|worst)", re.I)),
    ("readiness", re.compile(
        r"\b(readiness|ready|audit(?:or|s)?|certif\w*|prepared?|pass(?:ing|ed)?|"
        r"scores?|percent\w*)", re.I)),
    ("monitors", re.compile(
        r"\b(monitors?|checks?|tls|ssl|headers?|dns|dmarc|spf|dkim|scans?|"
        r"perimeter|automated)", re.I)),
    ("drift", re.compile(
        r"\bdrift|\bregress\w*|\bchanged|\bsince\b|\bbroke(?:n)?\b", re.I)),
    ("policies", re.compile(
        r"\bpolic\w*|\bpssi\b|\backnowledg\w*|\bsign(?:ed|ature)?\b|"
        r"\baccepted\b|\bcharte\b|\bprocedures?\b", re.I)),
    ("questionnaires", re.compile(
        r"\bquestionnaires?|\bvendors?\b|\bbuyers?\b|\bcaiq\b|"
        r"\bsig\b|\bquestionnaire\w*", re.I)),
    # A country name on its own is NOT a transfer question. "What is the capital
    # of France?" must not produce a hosting answer. So this pattern matches
    # transfer CONTEXT (host/transfer/residency/adequacy/F118) and, separately,
    # country names are only counted when such a context word is also present.
    ("transfer", re.compile(
        r"\bhost(?:ing|ed|s)?\b|\btransfers?\b|\babroad\b|"
        r"\bresiden\w*|\bsovereign\w*|\bf118\b|\badequacy\b|"
        r"\bstor(?:e|ed|es|ing)\b|"
        r"\bdata (?:leave|leaves|leaving|go|goes|going)\b", re.I)),
    ("law0520", re.compile(
        r"05-?20|\bdgssi\b|\bdnssi\b|\biiv\b|\barticle 49\b|"
        r"\bcybersecurity law\b", re.I)),
    ("dataprotection", re.compile(
        r"09-?08|\bpersonal data\b|\bcndp\b|\bgdpr\b|\bconsent\w*|"
        r"\bdpo\b|\bprivacy\b|\bcin\b|\bsensitive\b", re.I)),
    ("priority", re.compile(
        r"\bpriority|\bprioriti\w*|\bfirst\b|\bnext step\w*|"
        r"\bwhere (?:do|should) i\b|\bquick win\w*|\bmost important\b", re.I)),
]


def classify(question: str) -> str:
    """Pick the intent with the most keyword evidence.

    Deliberately simple and inspectable: a regex router a reviewer can read in
    ten seconds beats an opaque classifier in a product that has to be defensible.
    """
    q = question or ""

    # A country name is only evidence of a transfer question when a transfer
    # context word is present too. This prevents "capital of France" from
    # being answered as a hosting question.
    _COUNTRY = re.compile(
        r"\b(france|germany|finland|ireland|spain|netherlands|belgium|portugal|"
        r"italy|sweden|austria|denmark|poland|estonia|greece|hungary|latvia|"
        r"lithuania|luxembourg|malta|romania|slovakia|slovenia|bulgaria|cyprus|"
        r"croatia|iceland|liechtenstein|norway|switzerland|canada|"
        r"united kingdom|uk|united states|usa|india|china|brazil|australia)\b",
        re.I)
    _TRANSFER_CONTEXT = re.compile(
        r"\bhost|\btransfer|\bresiden|\bsovereign|\bf118|\badequacy|"
        r"\beu\b|\beurope\w*|\bstor(?:e|ed|ing)\b|\bkeep|\bstore", re.I)

    best, best_score = "unknown", 0
    for name, pat in _INTENTS:
        hits = len(pat.findall(q))
        # Domain NOUNS beat generic verbs. "What failed in the monitor run?"
        # contains 'failed' (a gaps word) and 'monitor' (a monitors word); the
        # question is about monitors, so the specific noun must win.
        weight = 1
        if name in ("transfer", "law0520", "dataprotection", "drift"):
            weight = 3
        elif name in ("monitors", "policies", "questionnaires"):
            weight = 3
        if name == "transfer":
            # No context word -> no transfer intent, even if a country is named.
            if not _TRANSFER_CONTEXT.search(q):
                continue
            if _COUNTRY.search(q):
                hits += 1
        score = hits * weight
        if score > best_score:
            best, best_score = name, score

    # "Where is our data hosted in France?" has context + country: fine.
    # "What is the capital of France?" has neither: correctly falls through.
    return best


# -------------------------------------------------------------- answer text
def _fmt_pct(v: Optional[float]) -> str:
    return "n/a" if v is None else "%.1f%%" % v


def _answer_gaps(ctx: ContextBundle) -> AgentAnswer:
    cits: List[Citation] = []
    if not ctx.gaps:
        return AgentAnswer(
            text=(
                "No control is currently recorded as a gap for %s. That reflects your "
                "assessment register, not an audit: %d control(s) are still unassessed, "
                "so the true position may be worse than this." % (ctx.legal_name, ctx.unassessed_count)
            ),
            citations=[Citation("score", s["framework_id"], s["framework_name"]) for s in ctx.scores],
            intent="gaps",
            follow_ups=["What is still unassessed?", "Are we ready for an ISO 27001 audit?"],
        )

    # Rank by weight so the heaviest gaps surface first.
    ranked = sorted(ctx.gaps, key=lambda g: (-float(g.get("weight") or 0), g.get("id", "")))
    lines = ["%d control(s) are recorded as gaps. Heaviest first:" % len(ctx.gaps), ""]
    for g in ranked[:8]:
        owner = g.get("owner") or "no owner"
        due = g.get("due") or "no due date"
        lines.append("- **%s** %s (%s; weight %s; %s; due %s)" % (
            g.get("id", ""), g.get("title", ""), g.get("framework", ""),
            g.get("weight", ""), owner, due))
        cits.append(Citation("control", g.get("id", ""), g.get("title", "")))

    if len(ranked) > 8:
        lines.append("- ...and %d more" % (len(ranked) - 8))
    lines.append("")
    lines.append(
        "Start with the highest-weight gap that has no owner, or the one whose due "
        "date has passed. A gap without an owner never closes."
    )
    return AgentAnswer(
        text=chr(10).join(lines), citations=cits, intent="gaps",
        follow_ups=["What should I fix first?", "Has anything regressed since last week?"],
    )


def _answer_readiness(ctx: ContextBundle) -> AgentAnswer:
    if not ctx.scores:
        return AgentAnswer(
            text="No assessment has been recorded for %s yet, so there is no readiness "
                 "position to report. Assess a framework first." % ctx.legal_name,
            intent="readiness", grounded=False,
            follow_ups=["What are my biggest gaps right now?"],
        )

    cits = [Citation("score", s["framework_id"], s["framework_name"]) for s in ctx.scores]
    lines = ["Readiness for %s:" % ctx.legal_name, ""]
    for s in ctx.scores:
        lines.append("- **%s**: %s -- %s (%d gap, %d partial, %d unassessed)" % (
            s["framework_name"], _fmt_pct(s.get("pct")), s.get("verdict", ""),
            s.get("gaps", 0), s.get("partials", 0), s.get("unassessed", 0)))
    lines.append("")

    worst = min(ctx.scores, key=lambda s: s.get("pct") or 0)
    best = max(ctx.scores, key=lambda s: s.get("pct") or 0)
    lines.append("Strongest: **%s** at %s. Weakest: **%s** at %s." % (
        best["framework_name"], _fmt_pct(best.get("pct")),
        worst["framework_name"], _fmt_pct(worst.get("pct"))))

    total_gaps = sum(s.get("gaps", 0) for s in ctx.scores)
    if total_gaps:
        lines.append("")
        lines.append(
            "You are not audit-ready while %d control(s) sit as gaps. Readiness "
            "percentage is a planning signal, not an auditor's opinion." % total_gaps
        )
    else:
        lines.append("")
        lines.append(
            "No open gaps are recorded. Before booking an audit, confirm the %d "
            "unassessed control(s) genuinely do not apply to you -- an auditor will "
            "ask for the justification." % ctx.unassessed_count
        )
    return AgentAnswer(
        text=chr(10).join(lines), citations=cits, intent="readiness",
        follow_ups=["What are my biggest gaps right now?", "What should I fix first?"],
    )


def _answer_monitors(ctx: ContextBundle) -> AgentAnswer:
    if ctx.monitor_score is None:
        return AgentAnswer(
            text="No automated monitor run has been recorded for %s. Add a domain or an "
                 "integration, then run the checks -- the perimeter checks need no "
                 "credentials at all." % ctx.legal_name,
            intent="monitors", grounded=False,
            follow_ups=["What are my biggest gaps right now?"],
        )

    lines = [
        "Last automated run scored **%s** across your technical controls." % _fmt_pct(ctx.monitor_score),
        "",
    ]
    cits = [Citation("monitor", "last_run", ctx.monitor_last_run)]
    if not ctx.monitor_failing:
        lines.append("Every applicable check passed. Note that checks whose data source "
                     "was not configured are reported as not-applicable, not as passes.")
    else:
        lines.append("%d check(s) failing:" % len(ctx.monitor_failing))
        lines.append("")
        for f in ctx.monitor_failing[:10]:
            lines.append("- **%s** %s -- observed `%s` (%s)" % (
                f.get("check_id", ""), f.get("title", ""),
                json.dumps(f.get("observed")) if f.get("observed") is not None else "n/a",
                f.get("severity", "")))
            cits.append(Citation("monitor", f.get("check_id", ""), f.get("title", "")))
    lines.append("")
    lines.append(
        "These are observations, not control verdicts. A failing check means the fact "
        "differs from the expected value; whether the control fails is your call."
    )
    return AgentAnswer(
        text=chr(10).join(lines), citations=cits, intent="monitors",
        follow_ups=["Has anything regressed since last week?", "What should I fix first?"],
    )


def _answer_drift(ctx: ContextBundle) -> AgentAnswer:
    if not ctx.monitor_drift:
        return AgentAnswer(
            text="No regression has been detected since the previous run. A regression is "
                 "a check that passed and then failed -- that is what the drift engine "
                 "alerts on.",
            citations=[Citation("monitor", "last_run", ctx.monitor_last_run)],
            intent="drift",
            follow_ups=["What failed in the last monitor run?"],
        )
    lines = ["%d regression(s) detected since the previous run:" % len(ctx.monitor_drift), ""]
    cits = []
    for d in ctx.monitor_drift[:10]:
        lines.append("- **%s** %s (%s)" % (
            d.get("check_id", ""), d.get("title", ""), d.get("drift", "regression")))
        cits.append(Citation("monitor", d.get("check_id", ""), d.get("title", "")))
    lines.append("")
    lines.append(
        "A regression means the control was working and now is not. Treat these as "
        "incidents to investigate, not as a checklist to re-tick."
    )
    return AgentAnswer(
        text=chr(10).join(lines), citations=cits, intent="drift",
        follow_ups=["What failed in the last monitor run?", "What should I fix first?"],
    )


def _answer_policies(ctx: ContextBundle) -> AgentAnswer:
    if not ctx.policy_current:
        return AgentAnswer(
            text="No policy has been published for %s yet. The generator ships 20 ISMS "
                 "policies (PSSI, access control, incident management, data protection "
                 "and the rest) pre-filled with your details." % ctx.legal_name,
            intent="policies", grounded=False,
            follow_ups=["What are my biggest gaps right now?"],
        )
    lines = [
        "%d policy version(s) are current. %d acknowledgement(s) recorded in total." % (
            len(ctx.policy_current), ctx.policy_ack_total),
        "",
    ]
    cits = []
    for p in ctx.policy_current:
        lines.append("- **%s** v%s -- %d acknowledged" % (
            p.get("title", ""), p.get("version", 1), p.get("acknowledgement_count", 0)))
        cits.append(Citation("policy", p.get("policy_id", ""), p.get("title", "")))
    lines.append("")
    if ctx.policy_ack_total == 0:
        lines.append(
            "No one has acknowledged these yet. An unsigned policy is a document, not a "
            "control -- an auditor will ask for the acceptance record."
        )
    else:
        lines.append(
            "Check the acceptance rate per policy against headcount. Anything under "
            "100% is a finding an auditor will raise."
        )
    return AgentAnswer(
        text=chr(10).join(lines), citations=cits, intent="policies",
        follow_ups=["Which policies still need acknowledgement?"],
    )


def _answer_transfer(ctx: ContextBundle) -> AgentAnswer:
    """Hosting and cross-border transfer position, from the canonical CNDP list."""
    from compliance_os import cndp

    pos = cndp.transfer_position(ctx.hosting_country)
    lines = [
        "Client data is recorded as hosted in **%s**." % ctx.hosting_country,
        "",
        "- On the CNDP adequacy list (deliberation 236-2015): **%s**" % pos["on_list_text"],
        "- Transfer basis: %s" % pos["transfer_basis"],
        "- F118 authorisation: %s" % pos["f118_required"],
        "",
    ]
    if pos["on_list"]:
        lines.append(
            "France, Germany and Finland are all on the list, so EU hosting needs no "
            "transfer authorisation. That is also the cheapest hosting option, which "
            "makes it the default for a Moroccan service provider."
        )
    elif pos["known"]:
        lines.append(
            "This country is **not** on the list. Sending personal data there needs a "
            "CNDP authorisation (form F118) or a documented derogation. Do not rely on "
            "standard contractual clauses alone under Moroccan law."
        )
    else:
        lines.append(
            "This country is not recognised in the reference list, so the position is "
            "marked for verification. Confirm with the CNDP before relying on it."
        )
    return AgentAnswer(
        text=chr(10).join(lines),
        citations=[Citation("client", "hosting_country", ctx.hosting_country)],
        intent="transfer",
        follow_ups=["What does Law 05-20 require of us?"],
    )


def _answer_law0520(ctx: ContextBundle) -> AgentAnswer:
    in_scope = ctx.is_public_entity or ctx.is_iiv
    lines = ["Law 05-20 on cybersecurity binds a specific set of entities:", ""]
    lines.append("- public administrations")
    lines.append("- vital infrastructure operators (IIV)")
    lines.append("- five designated operator categories")
    lines.append("")
    if in_scope:
        lines.append(
            "**%s is in scope.** That brings the data-classification requirements of "
            "decree 2-21-406 and the DNSSI baseline into play." % ctx.legal_name
        )
    else:
        lines.append(
            "**%s does not appear to be in scope.** There is no general statutory duty "
            "on a private company. Your security obligations come from your contracts -- "
            "client questionnaires, bank vendor reviews, tender requirements." % ctx.legal_name
        )
        lines.append("")
        lines.append(
            "This matters for how you sell: you are not selling legal compliance, you are "
            "selling the ability to answer a buyer's security questionnaire and pass their "
            "vendor review."
        )
    lines.append("")
    lines.append(
        "One caution on language: article 49 makes it an offence to provide the statutory "
        "cybersecurity-services category without DGSSI qualification, with a fine of "
        "200,000 to 400,000 MAD. Describe the work as readiness assessment or gap "
        "assessment, never as an audit or a cybersecurity service."
    )
    return AgentAnswer(
        text=chr(10).join(lines),
        citations=[Citation("client", "scope", "Law 05-20 applicability")],
        intent="law0520",
        follow_ups=["Are we allowed to host client data in France?"],
    )


def _answer_dataprotection(ctx: ContextBundle) -> AgentAnswer:
    lines = ["Law 09-08 (CNDP) position for %s:" % ctx.legal_name, ""]
    cits = [Citation("client", "law_09_08", "Law 09-08")]
    if ctx.handles_sensitive_data or ctx.handles_cin:
        lines.append(
            "**Prior authorisation is required (art. 12).** You process either sensitive "
            "data or national identity numbers. That is a filing before processing starts, "
            "not after."
        )
        if ctx.handles_cin:
            lines.append("")
            lines.append(
                "Because you handle CIN numbers, do not warehouse identity documents. "
                "Record a hash or an attestation that the check was performed instead. "
                "That is a product design constraint, not a preference."
            )
    else:
        lines.append(
            "No sensitive data or CIN processing is recorded, so the general declaration "
            "regime applies rather than the art. 12 prior authorisation."
        )
    lines.append("")
    lines.append(
        "A written processor contract is mandatory under art. 23, and your client must be "
        "able to declare the subcontracting under art. 14(i)."
    )
    lines.append("")
    lines.append(
        "There is **no statutory breach-notification deadline** in Moroccan law. Any "
        "notification duty you have is contractual -- agree it explicitly rather than "
        "assuming a 72-hour rule exists."
    )
    return AgentAnswer(
        text=chr(10).join(lines), citations=cits, intent="dataprotection",
        follow_ups=["Are we allowed to host client data in France?"],
    )


def _answer_priority(ctx: ContextBundle) -> AgentAnswer:
    items: List[Tuple[str, str, Citation]] = []

    for g in sorted(ctx.gaps, key=lambda x: -float(x.get("weight") or 0))[:3]:
        items.append((
            "Close gap **%s** %s" % (g.get("id", ""), g.get("title", "")),
            "weight %s, owner %s, due %s" % (
                g.get("weight", ""), g.get("owner") or "unassigned", g.get("due") or "none"),
            Citation("control", g.get("id", ""), g.get("title", "")),
        ))
    for f in ctx.monitor_failing[:2]:
        items.append((
            "Fix failing check **%s** %s" % (f.get("check_id", ""), f.get("title", "")),
            "observed %s" % json.dumps(f.get("observed")),
            Citation("monitor", f.get("check_id", ""), f.get("title", "")),
        ))
    if ctx.policy_current and ctx.policy_ack_total == 0:
        items.append((
            "Collect policy acknowledgements",
            "published but nobody has signed",
            Citation("policy", "acceptance", "policy acknowledgement"),
        ))
    if ctx.questionnaire_needs_review:
        items.append((
            "Review %d questionnaire answer(s)" % ctx.questionnaire_needs_review,
            "a gap must not be sent to a buyer as a yes",
            Citation("questionnaire", "review", "pending review"),
        ))

    if not items:
        return AgentAnswer(
            text="Nothing is currently flagged: no open gaps, no failing checks, no "
                 "unsigned policies. Verify the %d unassessed control(s) before you "
                 "treat that as a clean bill of health." % ctx.unassessed_count,
            intent="priority", grounded=False,
            follow_ups=["Are we ready for an ISO 27001 audit?"],
        )

    lines = ["Fix these in this order:", ""]
    for i, (headline, detail, _cit) in enumerate(items, 1):
        lines.append("%d. %s -- %s" % (i, headline, detail))
    lines.append("")
    lines.append(
        "The order is weight first, then things that block a buyer: a failing "
        "public-facing control loses a deal faster than an internal gap."
    )
    return AgentAnswer(
        text=chr(10).join(lines),
        citations=[c for _h, _d, c in items],
        intent="priority",
        follow_ups=["What are my biggest gaps right now?"],
    )


def _answer_fallback(ctx: ContextBundle, question: str) -> AgentAnswer:
    """No intent matched: say so, and offer the real position as orientation."""
    lines = [
        "I can only answer from the compliance data recorded for %s, and I could not "
        "map that question to anything I can retrieve." % (ctx.legal_name or "this client"),
        "",
        "What I can tell you right now:",
    ]
    if ctx.scores:
        for s in ctx.scores:
            lines.append("- %s: %s" % (s["framework_name"], _fmt_pct(s.get("pct"))))
    if ctx.monitor_score is not None:
        lines.append("- last monitor run: %s" % _fmt_pct(ctx.monitor_score))
    lines.append("")
    lines.append("Try one of the suggested questions, or ask about gaps, readiness, "
                 "monitors, policies, or data transfer.")
    return AgentAnswer(
        text=chr(10).join(lines),
        citations=[Citation("score", s["framework_id"], s["framework_name"]) for s in ctx.scores],
        intent="unknown", grounded=False,
        follow_ups=SUGGESTED_QUESTIONS[:3],
    )


_ROUTES = {
    "gaps": _answer_gaps,
    "readiness": _answer_readiness,
    "monitors": _answer_monitors,
    "drift": _answer_drift,
    "policies": _answer_policies,
    "transfer": _answer_transfer,
    "law0520": _answer_law0520,
    "dataprotection": _answer_dataprotection,
    "priority": _answer_priority,
    "questionnaires": _answer_policies,
}


def answer_question(question: str, ctx: ContextBundle) -> AgentAnswer:
    """Deterministic, grounded answer. No network, no LLM, fully testable."""
    intent = classify(question)
    handler = _ROUTES.get(intent)
    if handler is None:
        return _answer_fallback(ctx, question)
    return handler(ctx)


# --------------------------------------------------------------- LLM polish
def polish_with_llm(answer: AgentAnswer, question: str, ctx: ContextBundle) -> AgentAnswer:
    """Optionally rewrite the composed answer with an LLM.

    The LLM sees the FACTS and the composed answer, and is told to rewrite only.
    If anything fails -- no key, timeout, malformed response -- the deterministic
    answer is returned unchanged. A polish step must never be able to break the
    product or introduce an unsupported claim.
    """
    api_key = os.environ.get("COMPLIANCE_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return answer

    base_url = os.environ.get("COMPLIANCE_LLM_BASE_URL", "https://api.openai.com/v1")
    model = os.environ.get("COMPLIANCE_LLM_MODEL", "gpt-4o-mini")

    system = (
        "You rewrite a compliance status summary for a professional audience. "
        "RULES: (1) Use ONLY the facts in the provided answer. (2) Never add a claim "
        "that is not already present. (3) Never soften a gap into a pass. (4) Keep "
        "every citation id exactly as written. (5) Be concise and direct. "
        "(6) Do not add a greeting or a sign-off."
    )
    payload = json.dumps({
        "model": model,
        "temperature": 0.2,
        "max_tokens": 700,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": "QUESTION: %s\n\nANSWER TO REWRITE:\n%s" % (
                question, answer.text)},
        ],
    }).encode("utf-8")

    import urllib.error
    import urllib.request
    req = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions", data=payload,
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + api_key},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        text = body["choices"][0]["message"]["content"].strip()
        if not text or len(text) < 20:
            return answer
        # Guard: the rewrite must not invent a citation id.
        known = {c.ref for c in answer.citations}
        mentioned = set(re.findall(r"\b[A-Z]{2,5}-\d+\b|\bA\.\d+\.\d+\b|\bCC\d\.\d\b", text))
        invented = mentioned - known
        if invented and not any(i in answer.text for i in invented):
            return answer   # rewrite introduced new refs: reject it
        answer.text = text
        answer.used_llm = True
        return answer
    except Exception:
        return answer


# ------------------------------------------------------------- context build
def build_context(**kwargs) -> ContextBundle:
    """Build a ContextBundle from plain dicts/lists (the router does the SQL)."""
    ctx = ContextBundle()
    for key in ("client_slug", "legal_name", "sector", "headcount",
                "hosting_country", "is_public_entity", "is_iiv",
                "handles_cin", "handles_sensitive_data"):
        if key in kwargs:
            setattr(ctx, key, kwargs[key])
    ctx.scores = kwargs.get("scores", [])
    ctx.gaps = kwargs.get("gaps", [])
    ctx.partials = kwargs.get("partials", [])
    ctx.unassessed_count = kwargs.get("unassessed_count", 0)
    ctx.implemented_count = kwargs.get("implemented_count", 0)
    ctx.monitor_score = kwargs.get("monitor_score")
    ctx.monitor_failing = kwargs.get("monitor_failing", [])
    ctx.monitor_drift = kwargs.get("monitor_drift", [])
    ctx.monitor_last_run = kwargs.get("monitor_last_run", "")
    ctx.policy_current = kwargs.get("policy_current", [])
    ctx.policy_ack_total = kwargs.get("policy_ack_total", 0)
    ctx.questionnaire_total = kwargs.get("questionnaire_total", 0)
    ctx.questionnaire_needs_review = kwargs.get("questionnaire_needs_review", 0)
    ctx.evidence_total = kwargs.get("evidence_total", 0)
    return ctx
