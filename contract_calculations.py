def average_contract_cap_percentage(cap_hit, start_season, end_season, cap_finder):
    """Return a contract's average cap-hit percentage over its full term.

    Returns ``None`` when the term is invalid or any season has a
    non-positive salary cap, allowing list/comparable callers to skip
    contracts whose percentage cannot be calculated.
    """
    duration = end_season - start_season + 1
    if duration <= 0:
        return None

    fractions_sum = 0
    for year in range(start_season, end_season + 1):
        salary_cap = cap_finder.get_salary_cap(year)
        if salary_cap <= 0:
            return None
        fractions_sum += cap_hit / salary_cap

    return (fractions_sum / duration) * 100


def convert_cap_hit(cap_hit, num_years, contract_start_year, reference_start_year, cap_finder):
    """
    Convert a salary cap hit from its original contract context into
    the equivalent value as if the contract had started in the
    reference year.

    Calculate the sum of the original contract's cap-hit fractions
    directly, then use that same sum both to determine the adjusted
    cap hit and to report the contract's average cap-hit percentage.
    This avoids converting the fraction sum to a percentage and average
    only to reverse those operations for the conversion calculation.
    Salary caps beyond the confirmed range come from cap_finder's
    projection, which may include this user's session-based overrides.
    """
    if num_years <= 0:
        raise ValueError("Cannot calculate cap percentage for an invalid term or salary cap.")

    original_cap_hit_fraction_sum = 0
    for year in range(contract_start_year, contract_start_year + num_years):
        salary_cap = cap_finder.get_salary_cap(year)
        if salary_cap <= 0:
            raise ValueError("Cannot calculate cap percentage for an invalid term or salary cap.")
        original_cap_hit_fraction_sum += cap_hit / salary_cap

    average_cap_percentage = (original_cap_hit_fraction_sum / num_years) * 100
    reference_reciprocal_sum = sum(
        1 / cap_finder.get_salary_cap(year)
        for year in range(reference_start_year, reference_start_year + num_years)
    )

    adjusted = original_cap_hit_fraction_sum / reference_reciprocal_sum
    return adjusted, average_cap_percentage
