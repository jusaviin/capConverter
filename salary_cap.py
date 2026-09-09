#!/Users/jviinika/code/nhl/nhlEnvironment/bin/python3

import os
import psycopg2
from dotenv import dotenv_values


class salary_cap_finder():

    def __init__(self, overrides=None):

        # Known salary cap values now come from the seasons table in
        # Postgres instead of being hard-coded. POSTGRES_URL is read
        # via python-dotenv: dotenv_values() reads the local .env file
        # directly (no need for the app entry point to call
        # load_dotenv() first), and real process environment variables
        # are merged in on top -- so on Render, where there's no .env
        # file at all, the variable set in Render's dashboard is still
        # found correctly.
        config = {**dotenv_values(), **os.environ}
        postgres_url = config.get("POSTGRES_URL")
        if not postgres_url:
            raise RuntimeError(
                "POSTGRES_URL is not set. Define it in your .env file "
                "(locally) or as an environment variable (in production)."
            )

        self.salary_cap = {}

        conn = psycopg2.connect(postgres_url, connect_timeout=5)
        try:
            cur = conn.cursor()
            # Only non-null salary_cap values count as "known" --
            # a season row can exist (e.g. for cap_floor tracking)
            # without a confirmed cap yet.
            cur.execute(
                "SELECT season, salary_cap FROM seasons "
                "WHERE salary_cap IS NOT NULL ORDER BY season"
            )
            for season, salary_cap in cur.fetchall():
                self.salary_cap[season] = salary_cap
        finally:
            conn.close()

        if not self.salary_cap:
            raise RuntimeError(
                "No known (non-null) salary_cap values found in the "
                "seasons table."
            )

        # Projected years pick up right where the known data ends,
        # covering the same 8-season window (first_projected through
        # first_projected+7) as before.
        known_max_season = max(self.salary_cap)
        self.first_projected = known_max_season + 1
        self.last_projected = self.first_projected + 7

        self.project_percentage(9)

        if overrides:
            self.apply_overrides(overrides)

    def get_salary_cap(self, year):
        """
        Get the salary cap based on year
    
        Argument:
            year: Year for which salary cap is returned
        
        Return:
            Salary cap for the given year
        """
        
        # The first season with hard cap was 2005-2006
        # There is no cap before that
        return self.salary_cap.get(year,-1)

    def get_full_table(self):
        """
        Return a copy of the full salary cap table (known + projected years).
        A copy is returned so callers can't mutate internal state directly.
        """
        return dict(self.salary_cap)

    def get_projected_bounds(self):
        """
        Return the (first_projected, last_projected) years — the only
        range that manual edits or percentage projection are allowed
        to modify.
        """
        return self.first_projected, self.last_projected

    def set_manual_value(self, year, value):
        """
        Manually override the salary cap for a single projected year.

        Arguments:
            year: Year to override. Must fall within
                  [first_projected, last_projected] — known historical
                  years are never editable.
            value: New salary cap value for that year (raw dollars).

        Raises:
            ValueError: if year is outside the editable range.
        """
        if not (self.first_projected <= year <= self.last_projected):
            raise ValueError(
                f"Year {year} is outside the editable range "
                f"({self.first_projected}-{self.last_projected})."
            )
        self.salary_cap[year] = value

    def get_projected_only(self):
        """
        Return just the projected-year portion of the table (raw
        dollars), keyed by year. This is the piece of state that
        differs per user once they customize their projection, so
        it's what gets saved into a session rather than the whole
        table (the known years never change).
        """
        return {
            year: self.salary_cap[year]
            for year in range(self.first_projected, self.last_projected + 1)
        }

    def apply_overrides(self, overrides):
        """
        Apply a dict of {year: raw_value} onto the projected range,
        e.g. state previously saved into a session. Keys outside the
        editable range are ignored rather than raising, since this is
        meant to restore trusted state we saved ourselves — not to
        validate fresh user input (use set_manual_value for that).
        """
        for year, value in overrides.items():
            year = int(year)
            if self.first_projected <= year <= self.last_projected:
                self.salary_cap[year] = value

    def project_percentage(self, percentage):
        """
        Project the future salary cap assuming fixed percent 
        
        Arguments:
            percentage = Fixed percent increase in salary cap
            
        """
        
        for year in range(self.first_projected, self.last_projected+1):
            past_cap = self.salary_cap[year-1]
            self.salary_cap[year] = past_cap + past_cap * (percentage / 100)
