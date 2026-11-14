# CLAUDE.md

TradeOps Reconciler — hackathon project (MongoDB *Agents in Context*, Track #3 "Finish the Job").

**Start every session by reading `docs/AI_CONTEXT.md`** — it has current status, rules, the Atlas setup checklist
and the build order. Design lives in `docs/architecture.md`; exact contracts in `docs/api-contracts.md`.

**End every session by updating `docs/AI_CONTEXT.md`** §2 (status table) and §6 (session log) with what you
built, what you verified (and how), and any blockers.

Hard rules (details in AI_CONTEXT §3): synthetic data only · no Streamlit, not a dashboard · no LLM in MVP ·
only the worker calls custodian PATCH, and only after exact-hash approval and a majority-written intent in Atlas ·
never fake results · secrets only in `.env` · runtime DB access via PyMongo, not MCP.

Stack: Python 3.12 + uv + FastAPI + PyMongo + httpx (backend, simulators, worker); React + Vite + TS (frontend).
