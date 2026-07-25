"""
Outbound BDR Engine — Wave A (Streamlit UI, FlytBase-styled).
Live reasoning · match tables · ICP score · cited insights · Why FlytBase · QA · CSV/Markdown export.
Run: streamlit run app.py   (needs GROQ_API_KEY; HUNTER_API_KEY optional)
"""
import io
import csv
import json

import streamlit as st
import agents

st.set_page_config(page_title="Outbound BDR Engine", page_icon="🛰️", layout="wide")

st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Press+Start+2P&family=Space+Mono:wght@400;700&display=swap');
  .stApp { background:#ECE8DA; color:#22223B; font-family:'Space Mono',monospace;
    background-image:radial-gradient(rgba(34,34,59,0.14) 1px, transparent 1px); background-size:15px 15px; }
  h1 { font-family:'Press Start 2P',monospace !important; color:#E8792B !important; line-height:1.5;
    text-shadow:3px 3px 0 rgba(34,34,59,0.15); }
  h2,h3 { font-family:'Space Mono',monospace !important; font-weight:700 !important; color:#22223B !important; }
  .stApp p, .stApp li, .stApp label, .stMarkdown { font-family:'Space Mono',monospace; }
  .eyebrow { font-family:'Press Start 2P',monospace; font-size:10px; color:#2E7D5B; letter-spacing:1px; }
  .stButton>button, .stDownloadButton>button { background:#F5C518; color:#22223B; border:3px solid #22223B;
    border-radius:0; font-family:'Press Start 2P',monospace; font-size:11px; box-shadow:5px 5px 0 #22223B; padding:12px 16px; }
  .stButton>button:hover { background:#E8792B; box-shadow:2px 2px 0 #22223B; transform:translate(3px,3px); color:#22223B; }
  .acard { background:#FFFCF2; border:3px solid #22223B; box-shadow:6px 6px 0 #22223B; padding:20px; margin-bottom:24px; }
  .score { font-family:'Press Start 2P',monospace; color:#E8792B; font-size:15px; }
  .match { font-family:'Space Mono',monospace; font-weight:700; color:#22223B; font-size:15px; }
  .muted { color:#5c5c66; font-size:13px; }
  .prio { font-family:'Press Start 2P',monospace; font-size:9px; color:#22223B; background:#F5C518;
    border:2px solid #22223B; padding:4px 7px; }
  .stat { background:#F5C518; border:3px solid #22223B; box-shadow:5px 5px 0 #22223B; padding:16px; text-align:center; }
  .statn { font-family:'Press Start 2P',monospace; font-size:20px; color:#22223B; }
  .statl { font-family:'Space Mono',monospace; font-size:11px; text-transform:uppercase; color:#22223B; font-weight:700; }
  .pass { color:#2E7D5B; font-weight:700; } .warn { color:#b5761f; font-weight:700; }
  a { color:#E8792B; font-weight:700; }
  .chip { display:inline-block; font-family:'Space Mono',monospace; font-size:11px; color:#22223B; background:#fff;
    border:2px solid #22223B; padding:2px 8px; margin:2px 5px 2px 0; box-shadow:2px 2px 0 #22223B; }
  .stTextInput input, .stTextArea textarea { border:2px solid #22223B !important; border-radius:0 !important;
    background:#FFFCF2 !important; color:#22223B !important; font-family:'Space Mono',monospace !important; }
  section[data-testid="stSidebar"] { background:#F5C518; border-right:3px solid #22223B; }
  [data-testid="stExpander"] { border:2px solid #22223B !important; border-radius:0 !important; background:#FFFCF2; }
  code { background:#22223B !important; color:#F5C518 !important; }
</style>
""", unsafe_allow_html=True)

st.markdown("<div class='eyebrow'>Physical AI · Outbound</div>", unsafe_allow_html=True)
st.title("Outbound BDR Engine")
st.caption("One campaign brief → ranked accounts, evidence-backed matches, cited research, verified contacts, and personalized outreach. Five agents: ICP, Research, Contact, Email, QA.")

with st.sidebar:
    st.subheader("Campaign brief")
    vertical = st.text_area("Target vertical", "Large-scale lithium, copper, and iron ore mining operations in Latin America")
    reference = st.text_input("Reference account", "Sociedad Química y Minera de Chile (SQM)")
    goal = st.text_input("Goal", "Book discovery calls with Head of Operations, VP of HSE, or Site Directors")
    angle = st.text_area("FlytBase angle", "Autonomous drone inspection replacing contracted crews at hazardous, 24/7 extraction sites")
    proof = st.text_input("Proof point", "FlytBase already runs autonomous inspection across SQM's 678 km² mine in Chile (with Adentu)")
    run = st.button("Run Pipeline", use_container_width=True)


def stat(n, label):
    st.markdown(f"<div class='stat'><div class='statn'>{n}</div><div class='statl'>{label}</div></div>", unsafe_allow_html=True)


def render_account(a, i):
    res, m, fb, qa = a.get("research", {}), a.get("match", {}), a.get("research", {}).get("why_flytbase", {}), a.get("qa", {})
    st.markdown("<div class='acard'>", unsafe_allow_html=True)
    prio = f"<span class='prio'>{fb.get('priority')}</span>" if fb.get("priority") else ""
    st.markdown(f"### {i}. {a['company']} &nbsp; <span class='score'>{res.get('score','–')}/100</span> "
                f"&nbsp; <span class='match'>{m.get('score','–')}% match</span> &nbsp; {prio}", unsafe_allow_html=True)
    st.markdown(f"<span class='muted'>{a.get('country','')} · {a.get('commodity','')} · why now: {res.get('why_now','')}</span>", unsafe_allow_html=True)

    if m.get("features"):
        st.markdown("**Match vs reference account**")
        st.table({"Feature": [f.get("feature") for f in m["features"]],
                  "Reference": [f.get("reference") for f in m["features"]],
                  "Candidate": [f.get("candidate") for f in m["features"]]})

    if res.get("insights"):
        st.markdown("**Research signals (with sources)**")
        for ins in res["insights"]:
            s = ins.get("source", "")
            if isinstance(s, str) and s.startswith("http"):
                d = f" · {ins.get('date')}" if ins.get("date") else ""
                st.markdown(f"- {ins.get('point','')} — [source]({s}){d}")
            else:
                st.markdown(f"- {ins.get('point','')} — _{s}_" if s else f"- {ins.get('point','')}")

    if fb.get("fit_reasons") or fb.get("use_cases"):
        st.markdown("**Why FlytBase**")
        for x in fb.get("fit_reasons", []):
            st.markdown(f"- ✓ {x}")
        if fb.get("use_cases"):
            st.markdown("".join(f"<span class='chip'>{u}</span>" for u in fb["use_cases"]), unsafe_allow_html=True)

    with st.expander(f"Contacts ({len(a.get('contacts', []))})"):
        for c in a.get("contacts", []):
            who = c.get("name") or c.get("role")
            conf = f" · {c['confidence']}% confidence" if c.get("confidence") else ""
            em = f" · `{c['email']}`" if c.get("email") else ""
            st.markdown(f"- **{who}** — [{c.get('status','')}]({c.get('link','')}){conf}{em}")
    with st.expander(f"Outreach ({len(a.get('emails', []))})"):
        for e in a.get("emails", []):
            st.markdown(f"**To: {e['to']}**")
            st.code(e["body"])

    cls = "pass" if qa.get("status") == "pass" else "warn"
    st.markdown(f"**QA:** <span class='{cls}'>{qa.get('status','').upper()}</span> · sources {qa.get('insights_sourced','')} · {'; '.join(qa.get('notes', []))}", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)


if run:
    brief = {"vertical": vertical, "reference": reference, "goal": goal, "angle": angle, "proof": proof}
    st.subheader("Live reasoning")
    panel = st.empty()
    logs = []

    def push(line):
        logs.append(line)
        panel.markdown("\n\n".join(logs[-14:]))

    try:
        for kind, label, payload in agents.run_pipeline(brief):
            if kind == "status":
                push(f"⏳ **{label}**")
            elif kind == "icp":
                push(f"🎯 **ICP:** {payload.get('icp','')}  \nFound {len(payload.get('accounts', []))} lookalike accounts.")
            elif kind == "research":
                push(f"🔎 **{label}** — {len(payload.get('insights', []))} insights, {payload.get('search_hits',0)} live sources, fit {payload.get('score','–')}/100.")
            elif kind == "contacts":
                push(f"👤 **{label}** — {sum(1 for c in payload if c.get('email'))} verified email(s), rest as search links.")
            elif kind == "emails":
                push(f"✉️ **{label}** — {len(payload)} personalized email(s).")
            elif kind == "qa":
                push(f"✅ **{label}** — QA {payload.get('status','').upper()} ({payload.get('insights_sourced','')} sourced).")
            elif kind == "done":
                st.session_state["result"] = payload
        push("🏁 **Done.**")
    except Exception as e:
        st.error(f"Pipeline error: {e}")

result = st.session_state.get("result")
if result:
    accts = result["accounts"]
    c1, c2, c3, c4 = st.columns(4)
    with c1: stat(len(accts), "Accounts")
    with c2: stat(sum(len(a.get("contacts", [])) for a in accts), "Contacts")
    with c3: stat(sum(len([c for c in a.get("contacts", []) if c.get("email")]) for a in accts), "Verified emails")
    with c4: stat(sum(len(a.get("emails", [])) for a in accts), "Emails drafted")

    st.markdown(f"**ICP:** {result.get('icp','')}")
    cA, cB, cC = st.columns(3)
    with cA: st.download_button("⬇️ Markdown (AE brief)", agents.to_markdown(result), "bdr_package.md", "text/markdown", use_container_width=True)
    with cB: st.download_button("⬇️ JSON", json.dumps(result, indent=2), "bdr_output.json", "application/json", use_container_width=True)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["rank", "company", "country", "commodity", "fit", "match%", "why_now", "qa"])
    for i, a in enumerate(accts, 1):
        w.writerow([i, a["company"], a.get("country", ""), a.get("commodity", ""),
                    a.get("research", {}).get("score", ""), a.get("match", {}).get("score", ""),
                    a.get("research", {}).get("why_now", ""), a.get("qa", {}).get("status", "")])
    with cC: st.download_button("⬇️ CSV", buf.getvalue(), "bdr_accounts.csv", "text/csv", use_container_width=True)

    for i, a in enumerate(accts, 1):
        render_account(a, i)
elif not run:
    st.info("Fill the brief in the sidebar and click Run Pipeline.")
