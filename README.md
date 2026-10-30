# job-scout

Collects senior commercial / GTM / partnerships / operations / AI roles in Israel for David Beer-Gabel's job search, and hands them to the Notion tracker where Claude scores them.

## How it works
1. **watchlist.json** — ~430 target company names (AI-native, cyber/infra, fintech/SaaS, SIs, globals with an Israel site). Edit freely; add `"ats"` + `"slug"` to pin a board, `"careers_url"` to point at the company's careers page (Comeet or any embedded ATS), or `"website"` to pin the domain used for sniffing.
2. **discover** — probes each company's name against the public job-board APIs of Greenhouse, Lever, Ashby, Workable, SmartRecruiters and Recruitee; if nothing answers, fetches the company's own site/careers page and looks for an embedded ATS (incl. the Comeet widget token). Results in `data/watchlist.resolved.json`; unresolved companies are retried monthly. SmartRecruiters answers "200, no jobs" for any slug, so only a non-empty SR board counts as resolved.
3. **scan** (every 6 hours via GitHub Actions) — fetches every resolved board, plus LinkedIn's public job search (12 title queries, Israel, past week; no login). JSearch (Google for Jobs aggregator) is wired in but off by default: as of Oct 2026 it returns zero results for Israel (`country=il`), so it only runs when the workflow is dispatched with `jsearch=true`; filters titles by seniority + domain + Israel; dedupes against `data/seen.json`; writes `data/new-<date>.json` and `data/postings.json`; and, when `NOTION_TOKEN` is set, creates unscored **Roles** rows (and **Companies** rows if missing) in Notion.
4. **Claude** (the "Job search — scan roles & warm paths" scheduled task) scores the unscored rows with the rubric, finds warm paths, and pushes what matters.

## Secrets (GitHub → Settings → Secrets and variables → Actions)
- `NOTION_TOKEN` — internal integration token; share the "Job Search" Notion page with the integration.
- `RAPIDAPI_KEY` — JSearch on RapidAPI (optional, and currently useless for Israel — see above).

## Local
```
python -m unittest discover -s tests
python -m scout.main discover --limit 20
python -m scout.main scan --no-jsearch
```
No third-party dependencies.

## Files
- `data/watchlist.resolved.json` — company → ATS mapping (auto)
- `data/seen.json` — dedupe memory (auto)
- `data/postings.json` — all currently relevant postings (auto)
- `data/new-YYYY-MM-DD.json` — what was new on that day
- `data/rejected.sample.json` — a sample of filtered-out titles, to tune the filters
- `data/last-run.json` — last run summary (incl. `failed_boards` and JSearch request stats — a non-200 status there means the RapidAPI key/subscription needs a look)
