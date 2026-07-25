"""
Outbound BDR Engine v2 — Streamlit UI.
Live reasoning panel · per-insight sources · contact confidence · QA · CSV + Markdown export.
Run:  streamlit run app.py   (needs GROQ_API_KEY; HUNTER_API_KEY optional for real emails)
"""
import io
import csv
import json

import streamlit as st
import agents

st.set_page_config(page_title="Outbound BDR Engine", page_icon="🛰️", layout="wide")

st.markdown("""
<style>
  .stApp { background:#1a1a1a; color:#f0f0f0; }
  h1,h2,h3 { color:#f0f0f0; }
  .stButton>button { background:#ec7d42; color:#1a1a1a; border:0; font-weight:700; border-radius:0; }
  .acard { background:#242424; border:1px solid #3d3d3d; padding:16px; margin-bottom:12px; }
  .score { color:#ec7d42; font-weight:700; font-size:20px; }
  .muted { color:#999; font-size:13px; }
  .pass { color:#3a7a65; font-weight:700; } .warn { color:#d9a441; font-weight:700; }
  a { color:#ec7d42; }
</style>
""", unsafe_allow_html=True)

st.title("Outbound BDR Engine")
st.caption("ICP → Research → Contact → Email → QA. Five agents, live research, cited insights, verified contacts.")

with st.sidebar:
    st.subheader("Campaign brief")
    vertical = st.text_area("Target vertical",
                            "Large-scale lithium, copper, and iron ore mining operations in Latin America")
    reference = st.text_input("Reference account", "Sociedad Química y Minera de Chile (SQM)")
    goal = st.text_input("Goal", "Book discovery calls with Head of Operations, VP of HSE, or Site Directors")
    angle = st.text_area("FlytBase angle",
                         "Autonomous drone inspection replacing contracted crews at hazardous, 24/7 extraction sites")
    proof = st.text_input("Proof point",
                          "FlytBase already runs autonomous inspection across SQM's 678 km² mine in Chile (with Adentu)")
    run = st.button("Run Pipeline", use_container_width=True)


def render_account(a, i):
    res = a.get("research", {})
    qa = a.get("qa", {})
    st.markdown("<div class='acard'>", unsafe_allow_html=True)
    st.markdown(f"### {i}. {a['company']} &nbsp; <span class='score'>{res.get('score','–')}/100</span>",
                unsafe_allow_html=True)
    st.markdown(f"<span class='muted'>{a.get('country','')} · {a.get('commodity','')} · "
                f"why now: {res.get('why_now','')}</span>", unsafe_allow_html=True)
    if a.get("why_match"):
        st.markdown(f"**Why it matches the reference account:** {a['why_match']}")
    if res.get("insights"):
        st.markdown("**Research signals (with sources)**")
        for ins in res["insights"]:
            src = ins.get("source", "")
            tag = f" — [source]({src})" if isinstance(src, str) and src.startswith("http") else (f" — _{src}_" if src else "")
            st.markdown(f"- {ins.get('point','')}{tag}")
    if res.get("angle_fit"):
        st.markdown(f"**Angle fit:** {res['angle_fit']}")
    with st.expander("Contacts"):
        for c in a.get("contacts", []):
            who = c.get("name") or c.get("role")
            conf = f" · {c['confidence']}% confidence" if c.get("confidence") else ""
            em = f" · `{c['email']}`" if c.get("email") else ""
            st.markdown(f"- **{who}** — [{c.get('status','')}]({c.get('link','')}){conf}{em}")
    with st.expander("Emails"):
        for e in a.get("emails", []):
            st.markdown(f"**To: {e['to']}**")
            st.code(e["body"])
    cls = "pass" if qa.get("status") == "pass" else "warn"
    st.markdown(f"**QA:** <span class='{cls}'>{qa.get('status','').upper()}</span> · "
                f"sources {qa.get('insights_sourced','')} · {'; '.join(qa.get('notes', []))}",
                unsafe_allow_html=True)
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
                push(f"🎯 **ICP:** {payload.get('icp','')}  \nFound {len(payload.get('accounts',[]))} lookalike accounts.")
            elif kind == "research":
                n = len(payload.get("insights", []))
                push(f"🔎 **{label}** — {n} insights, {payload.get('search_hits',0)} live sources, fit {payload.get('score','–')}/100.")
            elif kind == "contacts":
                real = sum(1 for c in payload if c.get("email"))
                push(f"👤 **{label}** — {real} verified email(s), rest as search links.")
            elif kind == "emails":
                push(f"✉️ **{label}** — {len(payload)} personalized email(s) drafted.")
            elif kind == "qa":
                push(f"✅ **{label}** — QA {payload.get('status','').upper()} ({payload.get('insights_sourced','')} sourced).")
            elif kind == "done":
                st.session_state["result"] = payload
        push("🏁 **Done.**")
    except Exception as e:
        st.error(f"Pipeline error: {e}")

result = st.session_state.get("result")
if result:
    st.markdown(f"**ICP:** {result.get('icp','')}")
    for i, a in enumerate(result["accounts"], 1):
        render_account(a, i)

    # exports
    md = agents.to_markdown(result)
    st.download_button("⬇️ Download Markdown (for AEs)", md, "bdr_package.md", "text/markdown")
    st.download_button("⬇️ Download JSON", json.dumps(result, indent=2), "bdr_output.json", "application/json")
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["rank", "company", "country", "commodity", "score", "why_now", "why_match", "signals", "qa"])
    for i, a in enumerate(result["accounts"], 1):
        res = a.get("research", {})
        w.writerow([i, a["company"], a.get("country", ""), a.get("commodity", ""),
                    res.get("score", ""), res.get("why_now", ""), a.get("why_match", ""),
                    " | ".join(ins.get("point", "") for ins in res.get("insights", [])),
                    a.get("qa", {}).get("status", "")])
    st.download_button("⬇️ Download CSV", buf.getvalue(), "bdr_accounts.csv", "text/csv")
elif not run:
    st.info("Fill the brief in the sidebar and click Run Pipeline.")
