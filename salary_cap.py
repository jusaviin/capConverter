#!/Users/jviinika/code/nhl/nhlEnvironment/bin/python3

class salary_cap_finder():

    def __init__(self, overrides=None):
        
        # Known and projected salary cap values
        self.salary_cap = {
        # Known salary cap values
            2005: 39000000,
            2006: 44000000,
            2007: 50300000,
            2008: 56700000,
            2009: 56800000,
            2010: 59400000,
            2011: 64300000,
            2012: 70200000,
            2013: 64300000,
            2014: 69000000,
            2015: 71400000,
            2016: 73000000,
            2017: 75000000,
            2018: 79500000,
            2019: 81500000,
            2020: 81500000,
            2021: 81500000,
            2022: 82500000,
            2023: 83500000,
            2024: 88000000,
            2025: 95500000,
            2026: 104000000,
            2027: 113500000,
        # Projected salary cap, filled in the class method below
            2028: 0,
            2029: 0,
            2030: 0,
            2031: 0,
            2032: 0,
            2033: 0,
            2034: 0,
            2035: 0
        }
        
        self.first_projected = 2028
        self.last_projected = 2035
        
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
