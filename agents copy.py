"""
Outbound BDR Engine - open-source version.
Five specialist agents, run in sequence. LLM = Groq (open Llama model).
Live research = DuckDuckGo (free, no key). No fabrication: research is grounded
on real search snippets; contacts are verified or handed off as a live search link.
"""
import os
import re
import json
import urllib.parse

from groq import Groq

MODEL = os.environ.get("BDR_MODEL", "llama-3.3-70b-versatile")


# ---------- LLM plumbing ----------
def _client():
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY is not set. Add it as an environment variable / secret.")
    return Groq(api_key=key)


def _chat(system, user, temperature=0.4, max_tokens=1400):
    resp = _client().chat.completions.create(
        model=MODEL,
        temperature=temperature,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return resp.choices[0].message.content.strip()


def _parse_json(text):
    """Extract the first JSON object/array from an LLM reply, robustly."""
    text = text.strip()
    # strip code fences
    text = re.sub(r"^```(json)?", "", text).strip()
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


# ---------- live web search (free, no key) ----------
def web_search(query, max_results=5):
    """Returns [{title, body, href}]. Falls back to [] if the library is unavailable."""
    DDGS = None
    try:
        from ddgs import DDGS  # newer package name
    except Exception:
        try:
            from duckduckgo_search import DDGS  # older package name
        except Exception:
            return []
    try:
        with DDGS() as ddgs:
            return list(ddgs.text(query, max_results=max_results))
    except Exception:
        return []


def linkedin_xray(persona, company):
    q = f'site:linkedin.com/in ("{persona}") "{company}"'
    return "https://www.google.com/search?q=" + urllib.parse.quote(q)


# ---------- Agent 1: Lookalike Finder ----------
def lookalike_finder(brief):
    system = "You are an expert B2B outbound researcher. Return ONLY valid JSON, no prose."
    user = f"""Campaign brief:
Target vertical: {brief['vertical']}
Reference account: {brief['reference']}
Goal: {brief['goal']}

Model the ideal customer profile (ICP) from the reference account, then list 6 real,
well-known companies that closely match it in scale, operations, and geography.
Only use companies you are confident actually exist. Do not invent companies.
Return JSON:
{{"icp": "one sentence ICP", "accounts": [{{"company": "", "country": "", "commodity": "", "reason": "why it fits, tied to a real signal"}}]}}"""
    data = _parse_json(_chat(system, user)) or {}
    return data


# ---------- Agent 2: Account Researcher (live) ----------
def account_researcher(company, angle):
    results = web_search(f"{company} operations expansion technology safety 2025 2026 news", max_results=5)
    snippets = "\n".join(
        f"- {r.get('title','')}: {r.get('body','')} ({r.get('href','')})" for r in results
    )
    system = ("You are a diligent research analyst. Use ONLY the provided search snippets for "
              "specific facts and numbers. If snippets are empty, give only high-level public "
              "knowledge and mark it general. Never invent specific figures. Return ONLY valid JSON.")
    user = f"""Company: {company}
FlytBase angle: {angle}
Search snippets:
{snippets or '(no live results returned)'}

Return JSON:
{{"signals": ["3-4 short signals, each tied to a snippet where possible"],
  "angle_fit": "1-2 sentences connecting the company to the FlytBase angle",
  "sources": ["urls actually used"]}}"""
    data = _parse_json(_chat(system, user)) or {}
    data.setdefault("sources", [r.get("href") for r in results if r.get("href")])
    return data


# ---------- Agent 3: Signal & Fit Ranker ----------
def signal_fit_ranker(accounts):
    """accounts: list of {company, research}. Returns same list with score + why_now, sorted desc."""
    brief_lines = []
    for a in accounts:
        sig = "; ".join(a.get("research", {}).get("signals", []) or [])
        brief_lines.append(f"{a['company']}: {sig}")
    joined = "\n".join(brief_lines)
    system = "You rank sales accounts by fit. Return ONLY valid JSON."
    user = f"""Score each account 0-100 for fit with autonomous drone inspection at hazardous 24/7 mining sites,
and give a one-line 'why now'. Accounts and their signals:
{joined}

Return JSON: [{{"company": "", "score": 0, "why_now": ""}}]"""
    ranked = _parse_json(_chat(system, user)) or []
    score_map = {r.get("company"): r for r in ranked if isinstance(r, dict)}
    for a in accounts:
        r = score_map.get(a["company"], {})
        a["score"] = r.get("score", 0)
        a["why_now"] = r.get("why_now", "")
    return sorted(accounts, key=lambda x: x.get("score", 0), reverse=True)


# ---------- Agent 4: Contact Finder (verifiable, no fabrication) ----------
PERSONAS = ["Head of Operations", "VP of HSE", "Site / Division Director"]


def contact_finder(company):
    contacts = [{"name": None, "persona": p, "status": "verify-live",
                 "link": linkedin_xray(p, company)} for p in PERSONAS]
    return contacts


# ---------- Agent 5: Outreach Writer ----------
def outreach_writer(company, research, contact, angle, proof):
    who = contact.get("name") or contact.get("persona")
    signals = "; ".join(research.get("signals", []) or [])
    system = ("You write concise, human outbound sales emails. No placeholders like {name}. "
              "Under 120 words. Reference one real signal. Sound like a person who did their homework.")
    user = f"""Write one cold email.
Recipient: {who} at {company}
Their company's real signals: {signals}
FlytBase angle: {angle}
Real proof to use: {proof}
Return just the email with a subject line."""
    return _chat(system, user, temperature=0.6, max_tokens=400)


# ---------- Orchestrator ----------
def run_pipeline(brief, progress=lambda *_: None):
    angle = brief.get("angle", "")
    proof = brief.get("proof", "")

    progress("Agent 1: Lookalike Finder")
    icp_data = lookalike_finder(brief)
    accounts = [{"company": a["company"], "country": a.get("country", ""),
                 "commodity": a.get("commodity", ""), "reason": a.get("reason", "")}
                for a in icp_data.get("accounts", [])]

    progress("Agent 2: Account Researcher (live web)")
    for a in accounts:
        a["research"] = account_researcher(a["company"], angle)

    progress("Agent 3: Signal & Fit Ranker")
    accounts = signal_fit_ranker(accounts)

    progress("Agent 4: Contact Finder")
    for a in accounts:
        a["contacts"] = contact_finder(a["company"])

    progress("Agent 5: Outreach Writer")
    for a in accounts:
        a["emails"] = []
        for c in a["contacts"]:
            a["emails"].append({"to": c["persona"], "body": outreach_writer(
                a["company"], a["research"], c, angle, proof)})

    return {"icp": icp_data.get("icp", ""), "accounts": accounts}
