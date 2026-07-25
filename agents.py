"""
Outbound BDR Engine — Wave A (Streamlit / Groq / DuckDuckGo).
Agents: ICP -> Research -> Contact -> Email -> QA.
Wave A: SQM-vs-candidate match table, ICP match score, cited insights (source+date),
"Why FlytBase" per company, retries, live reasoning (generator), CSV/Markdown export.
Free stack: Groq (LLM) + DuckDuckGo (search, no key) + Hunter.io (optional, emails).
"""
import os
import re
import json
import time
import urllib.parse

import requests
from groq import Groq

MODEL = os.environ.get("BDR_MODEL", "llama-3.3-70b-versatile")
PERSONAS = ["Head of Operations", "VP of HSE", "Site / Division Director"]
ROLE_KW = ["operation", "safety", "hse", "health", "site", "environment",
           "sustainab", "director", "mine", "mining", "plant", "maintenance", "chief"]


# ---------------- LLM plumbing (retries) ----------------
def _client():
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY is not set. Add it as a Secret.")
    return Groq(api_key=key)


def _chat(system, user, temperature=0.4, max_tokens=1600, retries=2):
    last = None
    for attempt in range(retries + 1):
        try:
            resp = _client().chat.completions.create(
                model=MODEL, temperature=temperature, max_tokens=max_tokens,
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": user}],
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
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


# ---------------- live web search ----------------
# Primary: Tavily (reliable, LLM-ready) if TAVILY_API_KEY is set.
# Fallback: DuckDuckGo (free, no key). Returns dicts with title/body/href.
def _tavily_search(query, max_results=6):
    key = os.environ.get("TAVILY_API_KEY")
    if not key:
        return []
    try:
        r = requests.post("https://api.tavily.com/search",
                          json={"api_key": key, "query": query, "max_results": max_results,
                                "search_depth": "basic"}, timeout=25)
        results = (r.json() or {}).get("results", [])
        return [{"title": x.get("title"), "body": x.get("content"), "href": x.get("url")} for x in results]
    except Exception:
        return []


def _ddg_search(query, max_results=6, retries=2):
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


def web_search(query, max_results=6, retries=2):
    hits = _tavily_search(query, max_results)
    if hits:
        return hits
    return _ddg_search(query, max_results, retries)


def linkedin_xray(persona, company):
    q = f'site:linkedin.com/in ("{persona}") "{company}"'
    return "https://www.google.com/search?q=" + urllib.parse.quote(q)


# ==================================================================
# Agent 1 — ICP Agent (evidence match table)
# ==================================================================
def icp_agent(brief):
    system = "You are an expert B2B outbound strategist. Return ONLY valid JSON, no prose."
    user = f"""Campaign brief:
Target vertical: {brief['vertical']}
Reference account: {brief['reference']}
Goal: {brief['goal']}

Write a one-sentence ICP, then list 6 real, verifiable matching companies. For EACH company give an evidence-based comparison against the reference account.
SCORING: match.score is 0-100. A company that aligns with the reference on geography (same region), commodity, scale, hazardous sites, and 24/7 operations must score 85-95. Only assign a low score for a genuine mismatch. Never lowball a strong match.
Return JSON:
{{"icp":"","accounts":[{{"company":"","country":"","commodity":"",
 "match":{{"score":0,"features":[
   {{"feature":"Geography","reference":"","candidate":""}},
   {{"feature":"Commodity","reference":"","candidate":""}},
   {{"feature":"Scale","reference":"","candidate":""}},
   {{"feature":"Hazardous sites","reference":"Yes","candidate":""}},
   {{"feature":"24x7 operations","reference":"Yes","candidate":""}}],
   "reasons":["short evidence bullet","..."]}}}}]}}"""
    return _parse_json(_chat(system, user, 0.4, 2200)) or {"icp": "", "accounts": []}


# ==================================================================
# Agent 2 — Research Agent (cited insights + Why FlytBase)
# ==================================================================
def research_agent(company, angle):
    hits = web_search(f"{company} mining operations expansion technology safety 2025 2026 news", max_results=6)
    snippets = "\n".join(
        f"[{i+1}] {h.get('title','')}: {h.get('body','')} (URL: {h.get('href','')})"
        for i, h in enumerate(hits))
    system = ("You are a rigorous analyst. Use ONLY the snippets for specific facts; attach the matching "
              "source URL and date to each insight; never invent numbers; mark unsupported points source "
              "'general knowledge'. Return ONLY valid JSON.")
    user = f"""Company: {company}
FlytBase angle: {angle}
Snippets:
{snippets or '(no live results)'}

SCORING: score is a 0-100 fit for autonomous drone inspection at hazardous, 24/7 sites. A large hazardous 24/7 mining operation should score 80-95. Do not lowball a strong operational fit.
Return JSON:
{{"insights":[{{"point":"specific recent signal","source":"URL or 'general knowledge'","date":"YYYY-MM or ''"}}],
  "angle_fit":"1-2 sentences linking the company to the FlytBase angle",
  "score":0,
  "why_now":"one-line timing trigger",
  "why_flytbase":{{"fit_reasons":["e.g. Large open-pit mine","Uses contractor inspections"],
    "use_cases":["Autonomous inspections","Stockpile monitoring","Perimeter security","Infrastructure inspection"],
    "priority":"High"}}}}"""
    data = _parse_json(_chat(system, user, 0.4, 1700)) or {}
    data.setdefault("insights", [])
    data.setdefault("score", 0)
    data.setdefault("why_now", "")
    data.setdefault("why_flytbase", {})
    data["sources"] = [h.get("href") for h in hits if h.get("href")]
    data["search_hits"] = len(hits)
    return data


# ==================================================================
# Agent 3 — Contact Agent (domain resolve + Hunter + confidence)
# ==================================================================
def _resolve_domain(company):
    try:
        out = _chat("Return ONLY the primary corporate web domain, nothing else.",
                    f"Main website domain for the company '{company}'? Just the domain, e.g. example.com",
                    temperature=0.0, max_tokens=30)
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
        rec = {"name": name or None, "role": e.get("position") or "", "email": e.get("value"),
               "linkedin": e.get("linkedin"), "confidence": e.get("confidence")}
        pos = (e.get("position") or "").lower()
        (role if any(k in pos for k in ROLE_KW) else other).append(rec)
    if role:
        return role[:5]
    other = [o for o in other if o.get("name")]
    other.sort(key=lambda x: x.get("confidence") or 0, reverse=True)
    return other[:2]


def contact_agent(company):
    domain = _resolve_domain(company)
    contacts = []
    for r in _hunter_by_domain(domain):
        contacts.append({"name": r.get("name"), "role": r.get("role") or "", "status": "verified email",
                         "confidence": r.get("confidence"), "email": r.get("email"),
                         "link": r.get("linkedin") or linkedin_xray(r.get("role") or "", company), "target": True})
    for p in PERSONAS:
        contacts.append({"name": None, "role": p, "status": "verify-live", "confidence": None,
                         "email": None, "link": linkedin_xray(p, company), "target": not any(c["target"] for c in contacts)})
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
    return _chat(system, user, temperature=0.6, max_tokens=420)


# ==================================================================
# Agent 5 — QA Agent
# ==================================================================
def qa_agent(account):
    notes, status = [], "pass"
    insights = account.get("research", {}).get("insights", []) or []
    sourced = sum(1 for i in insights if i.get("source") and i["source"] != "general knowledge")
    if not insights:
        status = "warn"; notes.append("No research insights returned.")
    elif sourced / len(insights) < 0.5:
        status = "warn"; notes.append("Under half of insights are backed by a live source.")
    if not [c for c in account.get("contacts", []) if c.get("email")]:
        notes.append("No verified email found; using LinkedIn search links (no fabrication).")
    return {"status": status, "insights_sourced": f"{sourced}/{len(insights)}",
            "notes": notes or ["All checks passed."]}


# ==================================================================
# Orchestrator — generator yielding live events
# ==================================================================
def run_pipeline(brief, max_emails_per_account=2):
    yield ("status", "ICP Agent — modelling ICP and finding lookalike accounts", None)
    icp = icp_agent(brief)
    accounts = [{"company": a.get("company"), "country": a.get("country", ""),
                 "commodity": a.get("commodity", ""), "match": a.get("match", {})}
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
    L = ["# Outbound BDR Engine — account package", "", f"**ICP:** {result.get('icp','')}", ""]
    for i, a in enumerate(result.get("accounts", []), 1):
        res, m = a.get("research", {}), a.get("match", {})
        L += [f"## {i}. {a['company']}  (fit {res.get('score','–')}/100, match {m.get('score','–')}%)",
              f"*{a.get('country','')} · {a.get('commodity','')}* — why now: {res.get('why_now','')}", ""]
        if m.get("features"):
            L.append("**Match vs reference account:**")
            for f in m["features"]:
                L.append(f"- {f.get('feature')}: reference {f.get('reference')} / candidate {f.get('candidate')}")
            L.append("")
        L.append("**Research signals:**")
        for ins in res.get("insights", []):
            s = ins.get("source", "")
            s = f" ([source]({s})" + (f", {ins.get('date')}" if ins.get("date") else "") + ")" if isinstance(s, str) and s.startswith("http") else (f" ({s})" if s else "")
            L.append(f"- {ins.get('point','')}{s}")
        fb = res.get("why_flytbase", {})
        if fb:
            L += ["", f"**Why FlytBase ({fb.get('priority','')} priority):**"]
            for x in fb.get("fit_reasons", []):
                L.append(f"- {x}")
            if fb.get("use_cases"):
                L.append("Use cases: " + ", ".join(fb["use_cases"]))
        L += ["", "**Contacts:**"]
        for c in a.get("contacts", []):
            who = c.get("name") or c.get("role")
            conf = f" · {c['confidence']}%" if c.get("confidence") else ""
            em = f" · {c['email']}" if c.get("email") else ""
            L.append(f"- {who} — {c.get('status','')}{conf}{em}")
        L += ["", "**Outreach:**"]
        for e in a.get("emails", []):
            L += [f"*To {e.get('to')}:*", "", e.get("body", ""), ""]
        qa = a.get("qa", {})
        L += [f"**QA:** {qa.get('status','')} — {qa.get('insights_sourced','')} sourced; " + "; ".join(qa.get("notes", [])),
              "", "---", ""]
    return "\n".join(L)
