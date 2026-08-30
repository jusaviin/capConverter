import os

from flask import Flask, render_template, request, jsonify
from salary_cap import salary_cap_finder

app = Flask(__name__)

# Reject request bodies over 64KB outright. Every real payload this API
# expects (a handful of numbers, at most 8 override entries) is well
# under 1KB -- this just closes off oversized-body abuse.
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024

def convert_cap_hit(cap_hit, num_years, contract_start_year, reference_start_year, cap_finder):
    """
    Convert a salary cap hit from its original contract context into
    the equivalent value as if the contract had started in the
    reference year.

    We calculate the average cap hit over the duration of the contract
    and adjust the value such that these fractions match. Salary caps
    beyond the confirmed range come from cap_finder's projection,
    which may include this user's own session-based overrides.
    """

    # The numbers get very big, so divide everything by 1000000 to avoid numerics errors
    scale = 1000000

    # First, calculate the average cap hit fraction of the original contract
    average_cap_hit_fraction = 0
    for year in range(contract_start_year, contract_start_year+num_years):
        average_cap_hit_fraction = average_cap_hit_fraction + (cap_hit / cap_finder.get_salary_cap(year))

    # We want to match this fraction starting from the reference year
    # Reference number is b in ax = b calculation
    reference_number = average_cap_hit_fraction
    for year in range(reference_start_year, reference_start_year+num_years):
        reference_number = reference_number * (cap_finder.get_salary_cap(year) / scale)

    # We need sum of multiplications where one is missing
    # Sum of multiplications is a in ax = b calculation
    sum_of_multiplications = 0
    for forbidden_year in range(reference_start_year, reference_start_year+num_years):
        multiplication = 1
        for year in range(reference_start_year, reference_start_year+num_years):
            if year == forbidden_year:
                continue
            multiplication = multiplication * (cap_finder.get_salary_cap(year) / scale)
        sum_of_multiplications = sum_of_multiplications + multiplication

    # From these numbers, we can calculate x
    adjusted = reference_number / sum_of_multiplications * scale
    return adjusted


def _salary_cap_table_response(cap_finder):
    """
    Shared helper: builds the JSON payload describing the current
    salary cap table, in millions, along with which years are
    editable. Used by the GET endpoint and reused after writes so the
    frontend always gets the fresh state back.
    """
    table = cap_finder.get_full_table()
    first_editable, last_editable = cap_finder.get_projected_bounds()

    table_millions = {
        str(year): round(value / 1_000_000, 4) for year, value in table.items()
    }

    return jsonify({
        "table": table_millions,
        "editable_start": first_editable,
        "editable_end": last_editable,
    })


@app.route("/api/salary-cap", methods=["GET"])
def get_salary_cap_table():
    # No server-side state to read anymore -- this always returns the
    # default (9%) table. The frontend merges its own in-memory
    # overrides on top of this when rendering, and sends those
    # overrides explicitly with each /api/convert call.
    return _salary_cap_table_response(salary_cap_finder())


@app.route("/api/salary-cap/percentage", methods=["POST"])
def set_salary_cap_percentage():
    data = request.get_json(force=True)

    try:
        percentage = float(data["percentage"])
    except (KeyError, ValueError, TypeError):
        return jsonify({"error": "Invalid percentage value."}), 400

    # Start from a fresh instance so percentage projects cleanly from 2027
    finder = salary_cap_finder()
    finder.project_percentage(percentage)
    return _salary_cap_table_response(finder)

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/convert", methods=["POST"])
def convert():
    data = request.get_json(force=True)

    try:
        cap_hit = float(data["cap_hit"])
        num_years = int(data["num_years"])
        contract_start_year = int(data["contract_start_year"])
        reference_start_year = int(data["reference_start_year"])
        # Expect custom overrides sent directly from the JS client state
        overrides = data.get("overrides", {})
        if not isinstance(overrides, dict):
            raise TypeError
        # There are only 8 editable years -- anything beyond that is
        # either a bug on the client or a bogus payload. Reject it
        # before spending time parsing every entry.
        if len(overrides) > 8:
            return jsonify({"error": "Too many override entries."}), 400
        parsed_overrides = {int(k): float(v) * 1_000_000 for k, v in overrides.items()}
    except (KeyError, ValueError, TypeError):
        return jsonify({"error": "Invalid or missing input values."}), 400

    cap_finder = salary_cap_finder(overrides=parsed_overrides)

    # The dropdowns in the UI already constrain these, but the API is
    # reachable directly, so the same limits are enforced here too.
    # contract_start_year/reference_start_year are restricted to known
    # (non-projected) years -- the same rule the frontend dropdowns use.
    first_editable, _ = cap_finder.get_projected_bounds()
    table = cap_finder.get_full_table()
    earliest_known_year = min(table)
    latest_known_year = first_editable - 1

    if cap_hit < 0:
        return jsonify({"error": "cap_hit must be non-negative."}), 400
    if not (1 <= num_years <= 8):
        return jsonify({"error": "num_years must be between 1 and 8."}), 400

    for label, year in (
        ("contract_start_year", contract_start_year),
        ("reference_start_year", reference_start_year),
    ):
        if not (earliest_known_year <= year <= latest_known_year):
            return jsonify({
                "error": (
                    f"{label} must be between {earliest_known_year} and "
                    f"{latest_known_year}."
                )
            }), 400

    result = convert_cap_hit(cap_hit, num_years, contract_start_year, reference_start_year, cap_finder)
    return jsonify({"converted_cap_hit": round(result, 2)})


if __name__ == "__main__":
    # Debug mode enables the interactive Werkzeug debugger, which can
    # execute arbitrary code from the browser when an error occurs --
    # never enable it on a server reachable by anyone but you. It's
    # opt-in via env var so the safe default is "off".
    debug_mode = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    app.run(debug=debug_mode, port=5000)
