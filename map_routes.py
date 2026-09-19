"""
Routes for the team / roster map page.

This is the web version of mapTeams.py. The SQL is the same idea, but:
  * it runs against Postgres via database_helper.get_connection()
    (so placeholders are %s instead of ?, and no pandas is needed);
  * instead of building a folium map and saving it to a file, the
    endpoints return JSON and templates/map.html draws the map in the
    browser with Leaflet (the library folium wraps anyway).

Registered in app.py with:
    from map_routes import map_bp
    app.register_blueprint(map_bp)
"""

from flask import Blueprint, jsonify, render_template, request

from database_helper import get_connection

map_bp = Blueprint("map", __name__)


def _team_row_to_dict(row):
    code, name, city, logo, latitude, longitude = row
    return {
        "code": code,
        "name": name,
        "city": city,
        "logo": logo,
        "coordinates": [round(float(latitude), 5), round(float(longitude), 5)],
    }


@map_bp.route("/map")
def map_page():
    return render_template("map.html")


@map_bp.route("/api/map/seasons", methods=["GET"])
def map_seasons():
    """All seasons we have team data for, newest first."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT DISTINCT season FROM team_season_stats "
            "WHERE situation = 'all' AND phase = 'regular' ORDER BY season DESC"
        )
        seasons = [row[0] for row in cur.fetchall()]
    finally:
        conn.close()

    return jsonify({"seasons": seasons})


@map_bp.route("/api/map/teams", methods=["GET"])
def map_teams():
    """
    Teams that played in the given season, with arena coordinates.
    Used both to draw the "teams" map and to fill the team dropdown
    in "rosters" mode.
    """
    season = request.args.get("season", type=int)
    if season is None:
        return jsonify({"error": "season query parameter is required."}), 400

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT code, name, city, logo, arena_latitude, arena_longitude
            FROM teams
            WHERE code IN (
                SELECT team FROM team_season_stats
                WHERE season = %s AND situation = 'all' AND phase = 'regular'
            )
              AND arena_latitude IS NOT NULL
              AND arena_longitude IS NOT NULL
            ORDER BY name
            """,
            (season,),
        )
        rows = cur.fetchall()
    finally:
        conn.close()

    return jsonify({"season": season, "teams": [_team_row_to_dict(r) for r in rows]})


@map_bp.route("/api/map/roster", methods=["GET"])
def map_roster():
    """
    One team's roster for one season, grouped by birthplace: each
    entry is a city with its coordinates and the players born there.
    Also returns the team itself so the page can draw its logo.
    """
    team_code = request.args.get("team", "").strip()
    season = request.args.get("season", type=int)

    if not team_code or len(team_code) > 10 or season is None:
        return jsonify({"error": "team and season query parameters are required."}), 400

    conn = get_connection()
    try:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT code, name, city, logo, arena_latitude, arena_longitude
            FROM teams
            WHERE code = %s
            """,
            (team_code,),
        )
        team_row = cur.fetchone()
        if team_row is None or team_row[4] is None or team_row[5] is None:
            return jsonify({"error": "Unknown team."}), 404

        # The roster view (see viewSchema_postgres.sql) already joins
        # players, their regular-season stats rows and their birth city.
        cur.execute(
            """
            SELECT player_first_name, player_last_name,
                   city_name_english, city_state_code,
                   city_latitude, city_longitude
            FROM roster
            WHERE team_code = %s AND season = %s
            ORDER BY player_last_name, player_first_name
            """,
            (team_code, season),
        )
        roster_rows = cur.fetchall()
    finally:
        conn.close()

    # Group players by birthplace. Same rule as mapTeams.py: the key
    # is "City, STATE" when a state/province code exists, otherwise
    # just the city name.
    cities = {}
    player_count = 0
    for first, last, city, state, latitude, longitude in roster_rows:
        if latitude is None or longitude is None or not city:
            continue  # nothing to put on the map for this player

        city_key = f"{city}, {state}" if state else city
        player_name = f"{first} {last}"

        entry = cities.get(city_key)
        if entry is None:
            entry = cities[city_key] = {
                "city": city_key,
                "coordinates": [round(float(latitude), 5), round(float(longitude), 5)],
                "players": [],
            }
        if player_name not in entry["players"]:
            entry["players"].append(player_name)
            player_count += 1

    return jsonify({
        "team": _team_row_to_dict(team_row),
        "season": season,
        "cities": list(cities.values()),
        "player_count": player_count,
        "total_roster_size": len(roster_rows),
    })
