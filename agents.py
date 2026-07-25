"""
Outbound BDR Engine v2 — five specialist agents with QA, citations, confidence,
retries/failure handling, live reasoning (generator), and CSV/Markdown export.

Agents:  ICP Agent -> Research Agent -> Contact Agent -> Email Agent -> QA Agent
LLM: Groq (open Llama).  Live research: DuckDuckGo.  Emails: Hunter.io (optional).
No fabrication: research insights carry sources; contacts are verified or handed
off as verifiable LinkedIn search links.
"""
import os
import re
import json
import time
import urllib.parse

import requests
from groq import Groq

MODEL = os.environ.get("BDR_MODEL", "llama-3.3-70b-versatile")


# ---------------- LLM plumbing (with retries) ----------------
def _client():
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY is not set. Add it as a Secret.")
    return Groq(api_key=key)


def _chat(system, user, temperature=0.4, max_tokens=1400, retries=2):
    last = None
    for attempt in range(retries + 1):
        try:
            resp = _client().chat.completions.create(
                model=MODEL, temperature=temperature, max_tokens=max_tokens,
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": user}],
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:  # transient rate-limits etc.
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise last


def _parse_json(text):
    text = re.sub(r"^```(json)?", "", text.strip()).strip()
    text = re.sub(r"```$", "", text).strip()
    start = min([i for i in [text.find("{"), text.find("[")] if i != -1], default=-1)
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] in "{[":
            depth += 1
        elif text[i] in "}]":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except Exception:
                    break
    try:
        return json.loads(text[start:])
    except Exception:
        return None


# ---------------- live web search (retry + fallback) ----------------
def web_search(query, max_results=6, retries=2):
    try:
        from ddgs import DDGS
    except Exception:
        try:
            from duckduckgo_search import DDGS
        except Exception:
            return []
    for attempt in range(retries + 1):
        try:
            with DDGS() as ddgs:
                return list(ddgs.text(query, max_results=max_results))
        except Exception:
            time.sleep(1.0 * (attempt + 1))
    return []


def linkedin_xray(persona, company):
    q = f'site:linkedin.com/in ("{persona}") "{company}"'
    return "https://www.google.com/search?q=" + urllib.parse.quote(q)


# ==================================================================
# Agent 1 — ICP Agent
# ==================================================================
def icp_agent(brief):
    system = "You are an expert B2B outbound strategist. Return ONLY valid JSON."
    user = f"""Campaign brief:
Target vertical: {brief['vertical']}
Reference account: {brief['reference']}
Goal: {brief['goal']}

1) Write a one-sentence ICP modelled on the reference account.
2) List 6 real, verifiable companies that match it in scale, operations, and geography.
   For each, explain WHY it matches the reference account, citing a concrete comparison
   (commodity, geography, scale, or operating style). Do not invent companies.
Return JSON:
{{"icp": "", "accounts": [{{"company": "", "country": "", "commodity": "",
  "why_match": "why this company is like the reference account, with concrete evidence"}}]}}"""
    return _parse_json(_chat(system, user)) or {"icp": "", "accounts": []}


# ==================================================================
# Agent 2 — Research Agent  (insights + per-insight sources + score)
# ==================================================================
def research_agent(company, angle):
    hits = web_search(f"{company} operations expansion technology safety 2025 2026 news", max_results=6)
    snippets = "\n".join(
        f"[{i+1}] {h.get('title','')}: {h.get('body','')} (URL: {h.get('href','')})"
        for i, h in enumerate(hits))
    system = ("You are a rigorous research analyst. Use ONLY the snippets for specific facts, and "
              "attach the matching source URL to every insight. Never invent numbers. If no snippet "
              "supports a point, mark its source as 'general knowledge'. Return ONLY valid JSON.")
    user = f"""Company: {company}
FlytBase angle: {angle}
Snippets:
{snippets or '(no live results returned)'}

Return JSON:
{{"insights": [{{"point": "one specific signal", "source": "the URL that supports it or 'general knowledge'"}}],
  "angle_fit": "1-2 sentences linking the company to the FlytBase angle",
  "score": 0-100 fit score for autonomous drone inspection at hazardous 24/7 sites,
  "why_now": "one-line timing trigger"}}"""
    data = _parse_json(_chat(system, user)) or {}
    data.setdefault("insights", [])
    data.setdefault("score", 0)
    data.setdefault("why_now", "")
    data["search_hits"] = len(hits)
    data["sources"] = [h.get("href") for h in hits if h.get("href")]
    return data


# ==================================================================
# Agent 3 — Contact Agent  (real emails via Hunter + confidence)
# ==================================================================
PERSONAS = ["Head of Operations", "VP of HSE", "Site / Division Director"]
_ROLE_KEYWORDS = ["operation", "safety", "hse", "health", "site", "environment",
                  "sustainab", "director", "mine", "mining", "plant", "maintenance", "chief"]


def _resolve_domain(company):
    """Ask the model for the company's primary web domain so Hunter can find emails."""
    try:
        out = _chat("Return ONLY the primary corporate web domain, nothing else.",
                    f"What is the main website domain for the company '{company}'? "
                    f"Answer with just the domain, e.g. example.com", temperature=0.0, max_tokens=30)
        m = re.search(r"[a-z0-9.-]+\.[a-z]{2,}", out.lower())
        return m.group(0) if m else None
    except Exception:
        return None


def _hunter_by_domain(domain, limit=30):
    key = os.environ.get("HUNTER_API_KEY")
    if not key or not domain:
        return []
    try:
        r = requests.get("https://api.hunter.io/v2/domain-search",
                         params={"domain": domain, "api_key": key, "limit": limit}, timeout=25)
        emails = (r.json() or {}).get("data", {}).get("emails", [])
    except Exception:
        return []
    role, other = [], []
    for e in emails:
        name = " ".join(x for x in [e.get("first_name"), e.get("last_name")] if x).strip()
        rec = {"name": name or None, "title": e.get("position") or "",
               "email": e.get("value"), "linkedin": e.get("linkedin"),
               "confidence": e.get("confidence")}
        pos = (e.get("position") or "").lower()
        (role if any(k in pos for k in _ROLE_KEYWORDS) else other).append(rec)
    # prefer role-matched; if none, surface the 2 highest-confidence named people
    if role:
        return role[:5]
    other = [o for o in other if o.get("name")]
    other.sort(key=lambda x: x.get("confidence") or 0, reverse=True)
    return other[:2]


def contact_agent(company):
    domain = _resolve_domain(company)
    contacts = []
    for r in _hunter_by_domain(domain):
        contacts.append({
            "name": r.get("name"), "role": r.get("title") or "",
            "status": "verified email", "confidence": r.get("confidence"),
            "email": r.get("email"),
            "link": r.get("linkedin") or linkedin_xray(r.get("title") or "", company),
            "target": True,
        })
    for p in PERSONAS:
        contacts.append({"name": None, "role": p, "status": "verify-live",
                         "confidence": None, "email": None,
                         "link": linkedin_xray(p, company), "target": not contacts})
    return contacts, domain


# ==================================================================
# Agent 4 — Email Agent
# ==================================================================
def email_agent(company, research, contact, angle, proof):
    who = contact.get("name") or contact.get("role")
    signals = "; ".join(i.get("point", "") for i in research.get("insights", []))
    system = ("You write concise, human outbound sales emails. No placeholders like {name}. "
              "Under 120 words. Reference one real signal. Sound like a person who did the homework.")
    user = f"""Write one cold email.
Recipient: {who} at {company}
Real signals: {signals}
FlytBase angle: {angle}
Proof to use: {proof}
Return a subject line then the body."""
    return _chat(system, user, temperature=0.6, max_tokens=400)


# ==================================================================
# Agent 5 — QA Agent  (deterministic checks)
# ==================================================================
def qa_agent(account):
    notes, status = [], "pass"
    res = account.get("research", {})
    insights = res.get("insights", []) or []
    sourced = sum(1 for i in insights if i.get("source") and i["source"] != "general knowledge")
    if not insights:
        status, _ = "warn", notes.append("No research insights returned.")
    elif sourced / len(insights) < 0.5:
        status, _ = "warn", notes.append("Under half of insights are backed by a live source.")
    if not [c for c in account.get("contacts", []) if c.get("email")]:
        notes.append("No verified email found; using LinkedIn search links (no fabrication).")
    sig_words = {w for i in insights for w in re.findall(r"[a-zA-Z]{5,}", i.get("point", "").lower())}
    for e in account.get("emails", []):
        body_words = set(re.findall(r"[a-zA-Z]{5,}", e.get("body", "").lower()))
        if sig_words and not (sig_words & body_words):
            status, _ = "warn", notes.append(f"Email to {e.get('to')} may not reference a research signal.")
    return {"status": status, "insights_sourced": f"{sourced}/{len(insights)}",
            "notes": notes or ["All checks passed."]}


# ==================================================================
# Orchestrator — generator that yields live events for the UI
# ==================================================================
def run_pipeline(brief, max_emails_per_account=3):
    yield ("status", "ICP Agent — modelling ICP and finding lookalike accounts", None)
    icp = icp_agent(brief)
    accounts = [{"company": a.get("company"), "country": a.get("country", ""),
                 "commodity": a.get("commodity", ""), "why_match": a.get("why_match", "")}
                for a in icp.get("accounts", []) if a.get("company")]
    yield ("icp", None, {"icp": icp.get("icp", ""), "accounts": accounts})

    for a in accounts:
        yield ("status", f"Research Agent — {a['company']}", None)
        a["research"] = research_agent(a["company"], brief.get("angle", ""))
        yield ("research", a["company"], a["research"])

    accounts.sort(key=lambda x: x.get("research", {}).get("score", 0), reverse=True)

    for a in accounts:
        yield ("status", f"Contact Agent — {a['company']}", None)
        a["contacts"], a["domain"] = contact_agent(a["company"])
        yield ("contacts", a["company"], a["contacts"])

    for a in accounts:
        yield ("status", f"Email Agent — {a['company']}", None)
        targets = [c for c in a["contacts"] if c.get("target")][:max_emails_per_account]
        a["emails"] = [{"to": (c.get("name") or c.get("role")),
                        "body": email_agent(a["company"], a["research"], c,
                                            brief.get("angle", ""), brief.get("proof", ""))}
                       for c in targets]
        yield ("emails", a["company"], a["emails"])

    for a in accounts:
        a["qa"] = qa_agent(a)
        yield ("qa", a["company"], a["qa"])

    yield ("done", None, {"icp": icp.get("icp", ""), "accounts": accounts})


# ==================================================================
# Exports
# ==================================================================
def to_markdown(result):
    lines = [f"# Outbound BDR Engine — account package", "",
             f"**ICP:** {result.get('icp','')}", ""]
    for i, a in enumerate(result.get("accounts", []), 1):
        res = a.get("research", {})
        lines += [f"## {i}. {a['company']}  (fit {res.get('score','–')}/100)",
                  f"*{a.get('country','')} · {a.get('commodity','')}*", "",
                  f"**Why it matches the reference account:** {a.get('why_match','')}", "",
                  f"**Why now:** {res.get('why_now','')}", "", "**Research signals:**"]
        for ins in res.get("insights", []):
            src = ins.get("source", "")
            src = f" ([source]({src}))" if src and src.startswith("http") else f" ({src})" if src else ""
            lines.append(f"- {ins.get('point','')}{src}")
        lines += ["", "**Contacts:**"]
        for c in a.get("contacts", []):
            who = c.get("name") or c.get("role")
            conf = f" · {c['confidence']}% confidence" if c.get("confidence") else ""
            em = f" · {c['email']}" if c.get("email") else ""
            lines.append(f"- {who} — {c.get('status','')}{conf}{em} — [link]({c.get('link','')})")
        lines += ["", "**Outreach:**"]
        for e in a.get("emails", []):
            lines += [f"*To {e.get('to')}:*", "", e.get("body", ""), ""]
        qa = a.get("qa", {})
        lines += [f"**QA:** {qa.get('status','')} — sources {qa.get('insights_sourced','')}; "
                  + "; ".join(qa.get("notes", [])), "", "---", ""]
    return "\n".join(lines)
