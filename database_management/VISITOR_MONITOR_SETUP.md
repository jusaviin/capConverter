# Setting up the visitor monitor

## 1. Run the migration
```
psql "$DATABASE_URL" -f migrations/create_page_visits.sql
```
This creates two tables, both independent of your existing schema:
- `page_visits` — one row per page load (`visited_at`, `session_id`)
- `conversion_events` — one row per click of the Convert button (`converted_at`, `session_id`)

That's it for setup — no external services, no accounts, no extra
dependencies. `app.py` no longer imports anything beyond what it
already needed.

## How it works, no cookies involved
- On each page load, the server generates a random `session_id` and
  renders it directly into `index.html`'s own inline JS as
  `VISIT_SESSION_ID`. Nothing is written to a cookie, `localStorage`,
  or anything else the browser persists — it just sits in that page's
  memory for as long as the tab is open.
- That id is sent back exactly once, as a field in the JSON body of
  the `/api/convert` request, when the visitor clicks Convert. That's
  what lets you join a conversion back to the visit it came from.

## Querying it with pandas
```python
import pandas as pd
from sqlalchemy import create_engine

engine = create_engine("postgresql://user:pass@host:5432/dbname")

visits = pd.read_sql("SELECT * FROM page_visits", engine)
conversions = pd.read_sql("SELECT * FROM conversion_events", engine)

# Conversions per visit (most visits will be 0)
conversions_per_visit = (
    conversions.groupby("session_id").size().rename("num_conversions")
)
visits = visits.join(conversions_per_visit, on="session_id")
visits["num_conversions"] = visits["num_conversions"].fillna(0)

# e.g. what fraction of visits convert at least once
(visits["num_conversions"] > 0).mean()

# e.g. visits per day
visits.set_index("visited_at").resample("D").size()
```

## A couple of things worth knowing
- **This counts page loads, not unique visitors.** Refreshing the page adds another row, with a new session id. Telling repeat visitors apart from new ones would need some form of persistent identity (a cookie, most simply) — not something this implementation does.
- **No geography, no IP, nothing external.** Just a timestamp and a session id on each table. If you ever want country-level data back, that's a separate future step, not something you have to reintroduce anything for now.
- **Calling `/api/convert` directly** (outside the page, e.g. via curl) will log a conversion with `session_id = NULL` — expected, not a bug.
- **Bots and crawlers will still show up** in `page_visits`, with no filtering applied. If your counts look inflated, filtering by `User-Agent` is a reasonable next step, independent of everything else here.
