"""
Outbound BDR Engine - Streamlit UI (open-source version).
Run:  streamlit run app.py
Needs env var GROQ_API_KEY (free key from https://console.groq.com).
"""
import json
import io
import csv

import streamlit as st

import agents

st.set_page_config(page_title="Outbound BDR Engine", page_icon="🛰️", layout="wide")

# --- FlytBase-ish styling: charcoal + signal orange ---
st.markdown("""
<style>
  .stApp { background:#1a1a1a; color:#f0f0f0; }
  h1,h2,h3 { color:#f0f0f0; }
  .stButton>button { background:#ec7d42; color:#1a1a1a; border:0; font-weight:700; border-radius:0; }
  .acard { background:#242424; border:1px solid #3d3d3d; padding:16px; margin-bottom:12px; }
  .score { color:#ec7d42; font-weight:700; font-size:20px; }
  .muted { color:#999; font-size:13px; }
  a { color:#ec7d42; }
</style>
""", unsafe_allow_html=True)

st.title("Outbound BDR Engine")
st.caption("One campaign brief → ranked accounts, verified-or-searchable contacts, personalized outreach. Open-source build.")

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

if run:
    brief = {"vertical": vertical, "reference": reference, "goal": goal, "angle": angle, "proof": proof}
    status = st.empty()
    try:
        result = agents.run_pipeline(brief, progress=lambda m: status.info(f"Running… {m}"))
    except Exception as e:
        st.error(f"Pipeline error: {e}")
        st.stop()
    status.success("Pipeline complete")

    st.markdown(f"**ICP:** {result.get('icp','')}")
    st.session_state["result"] = result

result = st.session_state.get("result")
if result:
    for i, a in enumerate(result["accounts"], 1):
        with st.container():
            st.markdown(f"<div class='acard'>", unsafe_allow_html=True)
            st.markdown(f"### {i}. {a['company']} &nbsp; <span class='score'>{a.get('score','–')}</span>",
                        unsafe_allow_html=True)
            st.markdown(f"<span class='muted'>{a.get('country','')} · {a.get('commodity','')} · "
                        f"why now: {a.get('why_now','')}</span>", unsafe_allow_html=True)
            res = a.get("research", {})
            if res.get("signals"):
                st.markdown("**Signals**")
                for s in res["signals"]:
                    st.markdown(f"- {s}")
            if res.get("angle_fit"):
                st.markdown(f"**Angle fit:** {res['angle_fit']}")
            if res.get("sources"):
                st.markdown("**Sources:** " + " · ".join(
                    f"[link]({u})" for u in res["sources"] if u))
            with st.expander("Contacts"):
                for c in a.get("contacts", []):
                    label = c.get("name") or c.get("persona")
                    email = f" · `{c['email']}`" if c.get("email") else ""
                    st.markdown(f"- **{label}** — [{c.get('status','')}]({c.get('link','')}){email}")
            with st.expander("Emails"):
                for e in a.get("emails", []):
                    st.markdown(f"**To: {e['to']}**")
                    st.code(e["body"])
            st.markdown("</div>", unsafe_allow_html=True)

    # --- exports ---
    st.download_button("Download JSON", json.dumps(result, indent=2),
                       "bdr_output.json", "application/json")

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["rank", "company", "country", "commodity", "score", "why_now", "signals"])
    for i, a in enumerate(result["accounts"], 1):
        w.writerow([i, a["company"], a.get("country", ""), a.get("commodity", ""),
                    a.get("score", ""), a.get("why_now", ""),
                    " | ".join(a.get("research", {}).get("signals", []) or [])])
    st.download_button("Download CSV", buf.getvalue(), "bdr_accounts.csv", "text/csv")
else:
    st.info("Fill the brief in the sidebar and click Run Pipeline.")
