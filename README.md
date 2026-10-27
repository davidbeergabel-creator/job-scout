# job-scout

Collects senior commercial / GTM / partnerships / operations / AI roles in Israel for David Beer-Gabel's job search, and hands them to the Notion tracker where Claude scores them.

## How it works
1. **watchlist.json** — ~430 target company names (AI-native, cyber/infra, fintech/SaaS, SIs, globals with an Israel site). Edit freely; add `"ats"` + `"slug"` to pin a board, or `"careers_url"` for a Comeet careers page.
2. **discover** — probes each company's name against the public job-board APIs of Greenhouse, Lever, Ashby, Workable, SmartRecruiters and Recruitee (and reads the Comeet token from a careers page). Results in `data/watchlist.resolved.json`; unresolved companies are retried monthly.
3. **scan** (every 6 hours via GitHub Actions) — fetches every resolved board, plus JSearch (LinkedIn/Indeed/Glassdoor aggregator) once a day when `RAPIDAPI_KEY` is set; filters titles by seniority + domain + Israel; dedupes against `data/seen.json`; writes `data/new-<date>.json` and `data/postings.json`; and, when `NOTION_TOKEN` is set, creates unscored **Roles** rows (and **Companies** rows if missing) in Notion.
4. **Claude** (the "Job search — scan roles & warm paths" scheduled task) scores the unscored rows with the rubric, finds warm paths, and pushes what matters.

## Secrets (GitHub → Settings → Secrets and variables → Actions)
- `NOTION_TOKEN` — internal integration token; share the "Job Search" Notion page with the integration.
- `RAPIDAPI_KEY` — JSearch on RapidAPI (optional; without it the scan runs on ATS boards only).

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
- `data/last-run.json` — last run summary
