-- Standalone visitor log. Deliberately has no foreign keys into the
-- hockey/salary-cap tables -- it's just a record of "someone loaded
-- the page at this time."
--
-- session_id is a random id generated fresh on every page load and
-- rendered straight into that page's own JS (see index.html) -- it is
-- NOT a cookie. It never gets stored by the browser; it just lives in
-- that one page's memory and is sent back once, in the body of the
-- /api/convert request, if and when the visitor clicks Convert. That
-- makes it possible to join conversion_events back to the visit it
-- came from, without persisting any identifier client-side.
CREATE TABLE IF NOT EXISTS page_visits (
    id            BIGSERIAL PRIMARY KEY,
    visited_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    session_id    UUID
);

-- One row per click of the Convert button.
CREATE TABLE IF NOT EXISTS conversion_events (
    id            BIGSERIAL PRIMARY KEY,
    converted_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    session_id    UUID   -- matches page_visits.session_id when present; NULL if the API was called directly.
);

-- Speeds up by-day aggregation and the visits<->conversions join.
CREATE INDEX IF NOT EXISTS idx_page_visits_visited_at ON page_visits (visited_at);
CREATE INDEX IF NOT EXISTS idx_page_visits_session_id ON page_visits (session_id);
CREATE INDEX IF NOT EXISTS idx_conversion_events_session_id ON conversion_events (session_id);
