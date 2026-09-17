import json
import os
import uuid
from datetime import datetime, timezone

from flask import Flask, render_template, request, jsonify
from salary_cap import salary_cap_finder
from database_helper import get_connection

app = Flask(__name__)

# --- Visitor logging -------------------------------------------------

def log_visit():
    """
    Insert one row per page load into the (separate, unrelated-to-the-
    hockey-data) page_visits table, tagged with a fresh session id so
    later actions in the same tab (e.g. clicking Convert) can be tied
    back to this visit. Never lets a logging failure break the actual
    page render. Returns the session id either way -- if the insert
    failed, the page still renders, it just won't have a matching
    visit row to join against.
    """
    session_id = str(uuid.uuid4())

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO page_visits (visited_at, session_id) VALUES (%s, %s)",
            (datetime.now(timezone.utc), session_id),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        app.logger.exception("Failed to log page visit")
    finally:
        conn.close()

    return session_id


def log_conversion(session_id):
    """
    Records one click of the Convert button, tagged with the session
    id the page was rendered with (sent back explicitly in the
    request body -- see index.html). No cookie involved: nothing is
    stored by the browser, the id just lives in the page's own JS for
    as long as the tab is open and gets included with this one
    request. If it's missing or blank -- e.g. the API is called
    directly rather than through the page -- session_id is stored as
    NULL. Never lets a logging failure affect the actual conversion
    result.
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO conversion_events (converted_at, session_id)
            VALUES (%s, %s)
            """,
            (datetime.now(timezone.utc), session_id),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        app.logger.exception("Failed to log conversion event")
    finally:
        conn.close()


def get_max_contract_years(start_season):
    """
    Maximum legal contract length, which depends on when the contract
    starts:
      - 2020 or later: 8 years
      - 2013 through 2019 (inclusive): 12 years
      - before 2013: 24 years
    """
    if start_season >= 2020:
        return 8
    if start_season >= 2013:
        return 12
    return 24


# Shared SQL predicate for "this is a contract row the calculator can
# actually use": all the fields an autofill needs are present, the
# start season falls within known salary-cap history, and the
# duration is within the legal max for its own start season (see
# get_max_contract_years above -- kept in sync with this by hand,
# since duplicating the Python logic in SQL isn't worth the
# indirection for three ranges). Referenced by both
# /api/players/search (so players with no usable contracts are never
# offered in the first place) and /api/players/<id>/contracts (which
# actually returns them), so the two can't drift out of sync.
USABLE_CONTRACT_SQL = """
    c.start_season IS NOT NULL
    AND c.end_season IS NOT NULL
    AND c.cap_hit IS NOT NULL
    AND c.start_season >= 2005
    AND (
          (c.start_season >= 2020 AND (c.end_season - c.start_season + 1) <= 8)
       OR (c.start_season BETWEEN 2013 AND 2019 AND (c.end_season - c.start_season + 1) <= 12)
       OR (c.start_season < 2013 AND (c.end_season - c.start_season + 1) <= 24)
    )
"""

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
    
    # Calculate also the average cap percentage for the duration of the season
    average_cap_percentage = (average_cap_hit_fraction / num_years) * 100
    
    return adjusted, average_cap_percentage


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
    session_id = log_visit()
    # No cookie: session_id is rendered straight into the page's own
    # JS (see index.html) and only ever leaves the browser again if
    # the Convert button is clicked, as part of that one request body.
    return render_template("index.html", session_id=session_id)


@app.route("/api/players/search", methods=["GET"])
def search_players():
    query = request.args.get("q", "").strip()

    # Require a couple of real characters before hitting the DB --
    # avoids returning the entire players table on an empty/near-empty
    # query while someone is still typing.
    if len(query) < 2:
        return jsonify({"players": []})

    pattern = f"%{query}%"

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT p.id, p.first_name, p.last_name, p.position,
                   COALESCE(sk.team, gk.team) AS team
            FROM players p
            LEFT JOIN LATERAL (
                SELECT team FROM skater_season_stats
                WHERE playerid = p.id AND situation = 'all' AND phase = 'regular'
                ORDER BY season DESC
                LIMIT 1
            ) sk ON true
            LEFT JOIN LATERAL (
                SELECT team FROM goalie_season_stats
                WHERE playerid = p.id AND situation = 'all' AND phase = 'regular'
                ORDER BY season DESC
                LIMIT 1
            ) gk ON true
            WHERE unaccent(p.first_name || ' ' || p.last_name) ILIKE unaccent(%s)
              -- Only players who actually have at least one contract the
              -- autofill can use -- same criteria as
              -- /api/players/<id>/contracts -- otherwise selecting them
              -- just leads to an empty "No usable contracts found" list.
              AND EXISTS (
                SELECT 1 FROM contracts c
                WHERE c.player_id = p.id
                  AND {USABLE_CONTRACT_SQL}
              )
            ORDER BY p.last_name, p.first_name
            LIMIT 20
            """.format(USABLE_CONTRACT_SQL=USABLE_CONTRACT_SQL),
            (pattern,),
        )
        rows = cur.fetchall()
    finally:
        conn.close()

    players = [
        {
            "id": row[0],
            "first_name": row[1],
            "last_name": row[2],
            "position": row[3],
            "team": row[4],
        }
        for row in rows
    ]
    return jsonify({"players": players})


@app.route("/api/players/<int:player_id>/contracts", methods=["GET"])
def get_player_contracts(player_id):
    conn = get_connection()
    try:
        cur = conn.cursor()
        # Only contracts that fit what the calculator can actually
        # handle are returned -- see USABLE_CONTRACT_SQL above for the
        # exact criteria (also used by /api/players/search so players
        # with none of these don't show up there in the first place).
        #
        # The team shown is the team the contract was signed with
        # (contracts.signing_team), not a team derived from stats --
        # stats-based lookups broke down for things like entry-level
        # contracts that "start" a season before the player actually
        # debuts in the NHL.
        cur.execute(
            """
            SELECT c.id, c.type, c.start_season, c.end_season, c.cap_hit, c.total_value,
                   c.signing_team AS team
            FROM contracts c
            WHERE c.player_id = %s
              AND {USABLE_CONTRACT_SQL}
            ORDER BY c.start_season DESC
            """.format(USABLE_CONTRACT_SQL=USABLE_CONTRACT_SQL),
            (player_id,),
        )
        rows = cur.fetchall()
    finally:
        conn.close()

    contracts = []
    for contract_id, contract_type, start_season, end_season, cap_hit, total_value, team in rows:
        contracts.append({
            "id": contract_id,
            "type": contract_type,
            "start_season": start_season,
            "end_season": end_season,
            "num_years": end_season - start_season + 1,
            "cap_hit_millions": round(cap_hit / 1_000_000, 4),
            "total_value_millions": (
                round(total_value / 1_000_000, 4) if total_value is not None else None
            ),
            "team": team,
        })

    return jsonify({"contracts": contracts})


@app.route("/api/comparable-contracts", methods=["GET"])
def get_comparable_contracts():
    try:
        season = int(request.args.get("season"))
        cap_hit_millions = float(request.args.get("cap_hit"))
    except (TypeError, ValueError):
        return jsonify({"error": "season and cap_hit query parameters are required."}), 400

    target_cap_hit = cap_hit_millions * 1_000_000
    exclude_contract_id = request.args.get("exclude_contract_id", type=int)
    exclude_clause = " AND c.id != %(exclude_contract_id)s" if exclude_contract_id else ""

    # Parse custom overrides sent from frontend
    overrides_raw = request.args.get("overrides")
    parsed_overrides = {}
    if overrides_raw:
        try:
            overrides_dict = json.loads(overrides_raw)
            if isinstance(overrides_dict, dict):
                parsed_overrides = {int(k): float(v) * 1_000_000 for k, v in overrides_dict.items()}
        except (ValueError, TypeError):
            pass

    cap_finder = salary_cap_finder(overrides=parsed_overrides)

    contract_start_year = request.args.get("contract_start_year", type=int)
    num_years = request.args.get("num_years", type=int)
    original_cap_hit_millions = request.args.get("original_cap_hit", type=float)

    if (
        contract_start_year is not None
        and num_years is not None
        and num_years > 0
        and original_cap_hit_millions is not None
    ):
        original_cap_hit = original_cap_hit_millions * 1_000_000
        avg_fraction = sum(
            original_cap_hit / cap_finder.get_salary_cap(y)
            for y in range(contract_start_year, contract_start_year + num_years)
            if cap_finder.get_salary_cap(y) > 0
        )
        target_avg_cap_percentage = (avg_fraction / num_years) * 100
    else:
        season_cap = cap_finder.get_salary_cap(season)
        target_avg_cap_percentage = (target_cap_hit / season_cap * 100) if season_cap > 0 else 0.0

    conn = get_connection()
    try:
        cur = conn.cursor()

        # Fetch closest 10 by cap hit distance
        cur.execute(
            f"""
            SELECT p.first_name, p.last_name, c.cap_hit, c.start_season, c.end_season, c.type,
                   c.signing_team AS team
            FROM contracts c
            JOIN players p ON p.id = c.player_id
            WHERE c.cap_hit IS NOT NULL
              AND c.start_season IS NOT NULL
              AND c.end_season IS NOT NULL
              AND c.start_season <= %(season)s AND c.end_season >= %(season)s
              {exclude_clause}
            ORDER BY ABS(c.cap_hit - %(target)s) ASC
            LIMIT 10
            """,
            {
                "season": season,
                "target": target_cap_hit,
                "exclude_contract_id": exclude_contract_id,
            },
        )
        all_rows = cur.fetchall()

        # Re-sort the selected 10 by cap hit magnitude (largest to smallest)
        all_rows = sorted(all_rows, key=lambda row: row[2], reverse=True)

        cur.execute(
            f"""
            SELECT p.first_name, p.last_name, c.cap_hit, c.start_season, c.end_season, c.type,
                   c.signing_team AS team
            FROM contracts c
            JOIN players p ON p.id = c.player_id
            WHERE c.cap_hit IS NOT NULL
              AND c.start_season IS NOT NULL
              AND c.end_season IS NOT NULL
              AND c.start_season <= %(season)s AND c.end_season >= %(season)s
              {exclude_clause}
            """,
            {
                "season": season,
                "exclude_contract_id": exclude_contract_id,
            },
        )
        candidates = cur.fetchall()
    finally:
        conn.close()

    formatted_avg_percentage_rows = []
    for first_name, last_name, cap_hit, start_season, end_season, contract_type, team in candidates:
        duration = end_season - start_season + 1
        if duration <= 0:
            continue

        fractions_sum = 0
        valid = True
        for yr in range(start_season, end_season + 1):
            cap_val = cap_finder.get_salary_cap(yr)
            if cap_val <= 0:
                valid = False
                break
            fractions_sum += cap_hit / cap_val

        if not valid:
            continue

        c_avg_cap_percentage = (fractions_sum / duration) * 100
        diff = abs(c_avg_cap_percentage - target_avg_cap_percentage)

        formatted_avg_percentage_rows.append({
            "player_name": f"{first_name} {last_name}",
            "cap_hit_millions": round(cap_hit / 1_000_000, 4),
            "avg_cap_percentage": round(c_avg_cap_percentage, 2),
            "start_season": start_season,
            "end_season": end_season,
            "type": contract_type,
            "team": team,
            "diff": diff,
        })

    # Pick the 10 closest contracts by diff
    formatted_avg_percentage_rows.sort(key=lambda x: x["diff"])
    top_avg_percentage = formatted_avg_percentage_rows[:10]

    # Re-sort those top 10 by average cap percentage magnitude (largest to smallest)
    top_avg_percentage.sort(key=lambda x: x["avg_cap_percentage"], reverse=True)

    for r in top_avg_percentage:
        del r["diff"]

    def format_rows(rows):
        return [
            {
                "player_name": f"{first_name} {last_name}",
                "cap_hit_millions": round(cap_hit / 1_000_000, 4),
                "start_season": start_season,
                "end_season": end_season,
                "type": contract_type,
                "team": team,
            }
            for first_name, last_name, cap_hit, start_season, end_season, contract_type, team in rows
        ]

    return jsonify({
        "all_season": format_rows(all_rows),
        "avg_cap_percentage": top_avg_percentage,
    })

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
        # Optional: whatever session_id the page was rendered with.
        # Not trusted for anything beyond analytics -- just tagged onto
        # the conversion_events row as-is, blank/missing is fine.
        session_id = data.get("session_id") or None
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

    # The max contract length depends on when a contract starts, and a
    # reference season is really just a hypothetical contract of the
    # same length starting then -- so both the real and the reference
    # start seasons need to be able to legally host a contract this
    # long.
    max_num_years = min(
        get_max_contract_years(contract_start_year),
        get_max_contract_years(reference_start_year),
    )
    if not (1 <= num_years <= max_num_years):
        return jsonify({
            "error": (
                f"num_years must be between 1 and {max_num_years} for a contract "
                f"starting in {contract_start_year} converted to a reference "
                f"season starting in {reference_start_year}."
            )
        }), 400

    result, average_cap_percentage = convert_cap_hit(
        cap_hit, num_years, contract_start_year, reference_start_year, cap_finder
    )
    log_conversion(session_id)
    return jsonify({
        "converted_cap_hit": round(result, 2),
        "average_cap_percentage": round(average_cap_percentage, 2),
    })


if __name__ == "__main__":
    # Debug mode enables the interactive Werkzeug debugger, which can
    # execute arbitrary code from the browser when an error occurs --
    # never enable it on a server reachable by anyone but you. It's
    # opt-in via env var so the safe default is "off".
    debug_mode = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    app.run(debug=debug_mode, port=5000)
