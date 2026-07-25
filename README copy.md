# Outbound BDR Engine — open-source build

A fully open-source rebuild of the Outbound BDR Engine: one campaign brief in → ranked accounts, verifiable contacts, and personalized outreach out. Five specialist agents in a pipeline, with **live** web research.

## Stack (all free)
- **Streamlit** — UI + hosting (Streamlit Community Cloud)
- **Groq** — free, fast inference on an open Llama model
- **DuckDuckGo search (ddgs)** — live web research, no API key
- No vendor lock-in; the whole pipeline is plain Python you own.

## The five agents (`agents.py`)
1. **Lookalike Finder** — models the ICP from the reference account and lists real similar companies.
2. **Account Researcher** — runs a live web search per company and synthesizes real signals with sources.
3. **Signal & Fit Ranker** — scores each account 0–100 and adds a "why now".
4. **Contact Finder** — target personas + verifiable LinkedIn search links (no fabricated people).
5. **Outreach Writer** — a personalized email per contact, anchored to a real signal.

## Run locally
```bash
pip install -r requirements.txt
export GROQ_API_KEY=your_key   # from https://console.groq.com (free)
streamlit run app.py
```

## Deploy free (Streamlit Community Cloud)
1. Push this folder to a GitHub repo.
2. Go to https://share.streamlit.io → "New app" → pick the repo → main file `app.py`.
3. In the app's **Settings → Secrets**, add: `GROQ_API_KEY = "your_key"`.
4. Deploy → you get a public live link.

## Notes
- Research is grounded on live search snippets; the model is instructed never to invent specific figures.
- Contacts are handed off as verifiable search links rather than fabricated names.
- Next steps: add an enrichment API (Apollo/Clay) for real named contacts, and per-signal citations in the UI.
