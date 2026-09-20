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

# Quiz length: the person can ask for 1 to QUIZ_MAX_QUESTIONS questions,
# and QUIZ_DEFAULT_QUESTIONS is used when nothing is requested. If the
# chosen filters do not have enough eligible players, the quiz is simply
# shorter.
QUIZ_MAX_QUESTIONS = 20
QUIZ_DEFAULT_QUESTIONS = 10

# count=all asks for every eligible player (one question each). That is
# meant for a single team in a single season, where it is a roster's
# worth of questions. With broader filters it could be thousands of
# players, so the quiz is capped at this many questions (picked at
# random) to keep the response and the quiz itself a sensible size.
QUIZ_ALL_PLAYERS_CAP = 100

# We draw this many random candidate players per requested question,
# because some candidates get skipped (for example when every player on
# their roster was born in the same city, which would make for a
# pointless question).
QUIZ_CANDIDATES_PER_QUESTION = 6


def _team_row_to_dict(row):
    code, name, city, logo, latitude, longitude = row
    return {
        "code": code,
        "name": name,
        "city": city,
        "logo": logo,
        "coordinates": [round(float(latitude), 5), round(float(longitude), 5)],
    }


def _city_key(city, state):
    """
    Label for a birthplace: "City, STATE" when a state/province code
    exists, otherwise just the city name. Same rule as mapTeams.py.
    """
    return f"{city}, {state}" if state else city


def _group_roster_by_city(roster_rows):
    """
    Group roster rows by birthplace.

    Each row is (first_name, last_name, city, state_code, latitude,
    longitude). Returns (cities, player_count) where cities is a list of
    {"city", "coordinates", "players"} dicts. Players without a usable
    birthplace are skipped since there is nothing to put on the map.
    """
    cities = {}
    player_count = 0
    for first, last, city, state, latitude, longitude in roster_rows:
        if latitude is None or longitude is None or not city:
            continue

        city_key = _city_key(city, state)
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

    return list(cities.values()), player_count


@map_bp.route("/map")
def map_page():
    return render_template("map.html")


@map_bp.route("/api/map/seasons", methods=["GET"])
def map_seasons():
    """
    Seasons we have team data for, newest first.

    The team query parameter is optional: with a team code, only the
    seasons in which that team played are returned. The quiz uses this
    so that choosing a team first narrows the season dropdown, the same
    way choosing a season first narrows the team dropdown.
    """
    team_code = request.args.get("team", "").strip() or None
    if team_code and len(team_code) > 10:
        return jsonify({"error": "Invalid team."}), 400

    team_filter = ""
    params = ()
    if team_code:
        team_filter = "AND team = %s"
        params = (team_code,)

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT DISTINCT season FROM team_season_stats
            WHERE situation = 'all' AND phase = 'regular' {team_filter}
            ORDER BY season DESC
            """,
            params,
        )
        seasons = [row[0] for row in cur.fetchall()]
    finally:
        conn.close()

    return jsonify({"seasons": seasons})


@map_bp.route("/api/map/teams", methods=["GET"])
def map_teams():
    """
    Teams with arena coordinates. Used to draw the "teams" map, to fill
    the team dropdown in "rosters" mode, and to fill the team dropdown
    in quiz mode.

    The season query parameter is optional: with a season, only teams
    that played in that season are returned; without one, every team
    that played in any season is returned.
    """
    season = request.args.get("season", type=int)

    season_filter = ""
    params = ()
    if season is not None:
        season_filter = "AND season = %s"
        params = (season,)

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT code, name, city, logo, arena_latitude, arena_longitude
            FROM teams
            WHERE code IN (
                SELECT team FROM team_season_stats
                WHERE situation = 'all' AND phase = 'regular' {season_filter}
            )
              AND arena_latitude IS NOT NULL
              AND arena_longitude IS NOT NULL
            ORDER BY name
            """,
            params,
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

    cities, player_count = _group_roster_by_city(roster_rows)

    return jsonify({
        "team": _team_row_to_dict(team_row),
        "season": season,
        "cities": cities,
        "player_count": player_count,
        "total_roster_size": len(roster_rows),
    })


@map_bp.route("/api/map/quiz", methods=["GET"])
def map_quiz():
    """
    Build a hometown quiz.

    Optional query parameters:
      season -- limit the quiz to one season (default: any season)
      team   -- limit the quiz to one team code (default: any team)
      count  -- number of questions, 1 to QUIZ_MAX_QUESTIONS (default 10),
                or "all" for every eligible player (capped at
                QUIZ_ALL_PLAYERS_CAP)

    Returns up to `count` questions. Each question names a player,
    the team and the season, and lists every hometown on that team's
    roster that season (the markers the person chooses from) plus which
    of them is the correct one. A player appears at most once per quiz,
    even across different seasons.
    """
    season = request.args.get("season", type=int)
    team_code = request.args.get("team", "").strip() or None
    raw_count = request.args.get("count", str(QUIZ_DEFAULT_QUESTIONS)).strip().lower()

    if team_code and len(team_code) > 10:
        return jsonify({"error": "Invalid team."}), 400

    # "all" means every eligible player, up to the cap; otherwise a
    # number of questions within the allowed range.
    all_players = raw_count == "all"
    if all_players:
        count = QUIZ_ALL_PLAYERS_CAP
    else:
        try:
            count = int(raw_count)
        except ValueError:
            count = 0
        if count < 1 or count > QUIZ_MAX_QUESTIONS:
            return jsonify({
                "error": f'count must be "all" or between 1 and {QUIZ_MAX_QUESTIONS}.'
            }), 400

    # Only players we can actually place on the map are eligible.
    filters = [
        "city_latitude IS NOT NULL",
        "city_longitude IS NOT NULL",
        "city_name_english IS NOT NULL",
        "city_name_english <> ''",
    ]
    params = []
    if season is not None:
        filters.append("season = %s")
        params.append(season)
    if team_code:
        filters.append("team_code = %s")
        params.append(team_code)
    params.append(count * QUIZ_CANDIDATES_PER_QUESTION)

    conn = get_connection()
    try:
        cur = conn.cursor()

        # DISTINCT ON (player_id) keeps one random (season, team) row per
        # player, so nobody can be asked about twice. The outer query
        # then shuffles the players and takes a handful of candidates.
        cur.execute(
            f"""
            SELECT player_id, season, team_code, team_name,
                   player_first_name, player_last_name,
                   city_name_english, city_state_code
            FROM (
                SELECT DISTINCT ON (player_id)
                       player_id, season, team_code, team_name,
                       player_first_name, player_last_name,
                       city_name_english, city_state_code
                FROM roster
                WHERE {" AND ".join(filters)}
                ORDER BY player_id, random()
            ) AS one_row_per_player
            ORDER BY random()
            LIMIT %s
            """,
            params,
        )
        candidates = cur.fetchall()

        questions = []
        capped = False  # True if "all players" had to be cut off at the cap
        roster_cache = {}  # (team_code, season) -> list of city dicts

        for (_player_id, q_season, q_team_code, q_team_name,
             first, last, city, state) in candidates:
            if len(questions) >= count:
                # Reaching this point means at least one more candidate
                # was left over, i.e. there were more players than we
                # are asking about.
                capped = all_players
                break

            cache_key = (q_team_code, q_season)
            if cache_key not in roster_cache:
                cur.execute(
                    """
                    SELECT player_first_name, player_last_name,
                           city_name_english, city_state_code,
                           city_latitude, city_longitude
                    FROM roster
                    WHERE team_code = %s AND season = %s
                    """,
                    cache_key,
                )
                cities, _ = _group_roster_by_city(cur.fetchall())
                roster_cache[cache_key] = cities
            cities = roster_cache[cache_key]

            correct_city = _city_key(city, state)

            # A roster where everyone is from one town makes a pointless
            # question, and the correct town must be among the markers.
            if len(cities) < 2 or not any(c["city"] == correct_city for c in cities):
                continue

            questions.append({
                "player": f"{first} {last}",
                "team": q_team_name,
                "team_code": q_team_code,
                "season": q_season,
                "correct_city": correct_city,
                # Player names are left out on purpose: the markers
                # only show the town name.
                "cities": [
                    {"city": c["city"], "coordinates": c["coordinates"]}
                    for c in cities
                ],
            })
    finally:
        conn.close()

    return jsonify({"questions": questions, "capped": capped})
