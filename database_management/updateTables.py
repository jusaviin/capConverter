# Update the cities table in the database based on input json

# Required imports
import argparse
import csv
import logging
import psycopg2
import json
import time
import requests
from database_helper import get_connection
from capWagesReader import CapWagesReader
from nhlpy import NHLClient
import country_converter as coco
from helperFunctions import team_formatter, cityFormatter, getAccentedName
 
def updateCities(connection, cursor, cityFileName):
    """ 
    Function for updating the cities table in the database

    Arguments:
        connection = Connection object to PostgreSQL database
        cursor = cursor object to PostgreSQL database
        cityFileName = json file from which the city information is read
    """
    try:
        with open(cityFileName, "r", encoding='utf-8') as f:
            cityLocations = json.load(f)
            print("Updating the cities table from file {}.".format(cityFileName))

            sql_command = """
                INSERT INTO cities (
                    name_NHL_API, name_local, name_english, country, state, state_code, latitude, longitude
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (name_NHL_API) DO UPDATE SET
                    name_local = EXCLUDED.name_local,
                    name_english = EXCLUDED.name_english,
                    country = EXCLUDED.country,
                    state = EXCLUDED.state,
                    state_code = EXCLUDED.state_code,
                    latitude = EXCLUDED.latitude,
                    longitude = EXCLUDED.longitude
                WHERE
                    cities.name_local   IS DISTINCT FROM EXCLUDED.name_local OR
                    cities.name_english IS DISTINCT FROM EXCLUDED.name_english OR
                    cities.country      IS DISTINCT FROM EXCLUDED.country OR
                    cities.state        IS DISTINCT FROM EXCLUDED.state OR
                    cities.state_code   IS DISTINCT FROM EXCLUDED.state_code OR
                    cities.latitude     IS DISTINCT FROM EXCLUDED.latitude OR
                    cities.longitude    IS DISTINCT FROM EXCLUDED.longitude;
            """

            rows = []
            for cityCode, info in cityLocations.items():
                rows.append((
                    cityCode,
                    info["nameLocal"],
                    info["nameEnglish"],
                    info.get("country"),
                    info.get("state"),
                    info.get("state_code"),
                    info["coordinates"][0],
                    info["coordinates"][1],
                ))

            cursor.executemany(sql_command, rows)
            connection.commit()

    except FileNotFoundError:
        print("Could not open the file {}. Will not fill the cities table.".format(cityFileName))


def updatePlayers(connection, cursor, nhl_client, first_season, last_season):
    """
    Function for updating the players table in the database
    All the players from NHL API that are included in season rosters for teams are included
    New players are inserted, and information of existing players is updated if it has changed
    Notice that player stats are in another table

    Seasons are processed from the newest to the oldest, and each player is only handled
    once (from the newest season they appear in), so the most recent information wins.

    Arguments:
        connection = Connection object to PostgreSQL database
        cursor = cursor object to PostgreSQL database
        nhl_client = Client connected to NHL API to read team information
        first_season = Newest season to read, given as the start year (2025 = season 2025-2026)
        last_season = Oldest season to read, given as the start year
    """

    sql_command = """
        INSERT INTO players (
            id, first_name, last_name, birth_city, birth_date, position,
            handedness, headshot, height, weight
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE SET
            first_name = EXCLUDED.first_name,
            last_name = EXCLUDED.last_name,
            birth_city = EXCLUDED.birth_city,
            birth_date = EXCLUDED.birth_date,
            position = EXCLUDED.position,
            handedness = EXCLUDED.handedness,
            headshot = EXCLUDED.headshot,
            height = EXCLUDED.height,
            weight = EXCLUDED.weight
        WHERE
            players.first_name  IS DISTINCT FROM EXCLUDED.first_name OR
            players.last_name   IS DISTINCT FROM EXCLUDED.last_name OR
            players.birth_city  IS DISTINCT FROM EXCLUDED.birth_city OR
            players.birth_date  IS DISTINCT FROM EXCLUDED.birth_date OR
            players.position    IS DISTINCT FROM EXCLUDED.position OR
            players.handedness  IS DISTINCT FROM EXCLUDED.handedness OR
            players.headshot    IS DISTINCT FROM EXCLUDED.headshot OR
            players.height      IS DISTINCT FROM EXCLUDED.height OR
            players.weight      IS DISTINCT FROM EXCLUDED.weight;
    """

    # Pre-fetch valid city codes so that a birth city missing from the cities
    # table does not violate the foreign key and abort the whole batch
    cursor.execute("SELECT name_NHL_API FROM cities")
    valid_cities = {row[0] for row in cursor.fetchall()}

    # Create a formatter class for city names
    cityHelper = cityFormatter()

    # Avoid handling the same player multiple times
    handled_players = set()
    unknown_cities = []

    for season in range(first_season, last_season - 1, -1):

        seasonString = "{}{}".format(season, season + 1)
        print("Updating players table for season " + seasonString)
        
        # Now all the teams are listed for all dates for some reason
        # Pick a date that gives a list of all teams
        date_check = "{}-01-30".format(season + 1)
        if season == 2026:
            date_check = "2026-10-01"

        teams = nhl_client.teams.teams(date=date_check)
        time.sleep(1)  # Do not overwhelm NHL API with excessive requests

        for team in teams:

            # Get the end-of-season roster for the studied team
            roster = nhl_client.teams.team_roster(team_abbr=team["abbr"], season=seasonString)
            time.sleep(1)  # Do not overwhelm NHL API with excessive requests

            rows = []
            for position_group in roster:
                for player in roster[position_group]:

                    if player["id"] in handled_players:
                        continue
                    handled_players.add(player["id"])

                    birth_city, _, _ = cityHelper.formatCityName(player)

                    # Missing city information is stored as NULL
                    if birth_city not in valid_cities:
                        unknown_cities.append((player["id"], birth_city))
                        birth_city = None

                    rows.append((
                        player["id"],
                        getAccentedName(player, "firstName"),
                        getAccentedName(player, "lastName"),
                        birth_city,
                        player.get("birthDate"),
                        player.get("positionCode"),
                        player.get("shootsCatches"),
                        player.get("headshot"),
                        player.get("heightInCentimeters"),
                        player.get("weightInKilograms"),
                    ))

            # Commit the changes one team at a time
            if rows:
                cursor.executemany(sql_command, rows)
                connection.commit()
                
    # After all the information from NHL API is 

    if unknown_cities:
        unknown_log_path = "unknown_birth_cities.log"
        with open(unknown_log_path, "w", encoding='utf-8') as f:
            f.write(f"{len(unknown_cities)} player(s) had a birth city missing from the cities table (stored as NULL):\n")
            for playerID, city in unknown_cities:
                f.write(f"player_id={playerID} birth_city={city}\n")
        print(f"{len(unknown_cities)} player(s) with unknown birth city -- see {unknown_log_path} for details")


def updateNationalities(connection, cursor, nationalityFileName):
    """
    Function for filling the nationality column of the players table from a csv file
    NHL API does not contain nationality information, so it comes from a separate file
    Only players that already exist in the players table are updated; no new players are inserted
    Rows with an empty nationality are skipped, so existing values are never overwritten with NULL
    The csv has three letter country codes, which are stored as English country names (CAN -> Canada).
    Most codes are ISO 3166-1 alpha-3, but some are IOC codes (DEN, SUI, LAT, RSA), so both are handled.

    Arguments:
        connection = Connection object to PostgreSQL database
        cursor = cursor object to PostgreSQL database
        nationalityFileName = csv file with columns playerId and nationality
    """
    try:
        with open(nationalityFileName, "r", encoding="utf-8-sig", newline="") as f:
            print("Updating player nationalities from file {}.".format(nationalityFileName))

            # Pre-fetch the players that are in the table, so that we only update those
            cursor.execute("SELECT id FROM players")
            valid_player_ids = {row[0] for row in cursor.fetchall()}

            # Codes that are valid ISO3 are read as ISO3. Anything else is read as an IOC
            # code (DEN, SUI, LAT, RSA, GER, ...). One source is not enough for the whole
            # file, since e.g. DEU is only valid in ISO3 and DEN is only valid in IOC.
            logging.getLogger("country_converter").setLevel(logging.ERROR)
            converter = coco.CountryConverter()
            valid_iso3 = set(converter.data["ISO3"].dropna())
            code_cache = {}

            rows = []
            not_in_table = 0
            unknown_codes = set()
            missing_nationality = 0

            for entry in csv.DictReader(f):
                playerID = int(entry["playerId"])
                nationality = (entry["nationality"] or "").strip().upper()

                if playerID not in valid_player_ids:
                    not_in_table += 1
                    continue

                if not nationality:
                    missing_nationality += 1
                    continue

                if nationality not in code_cache:
                    source = "ISO3" if nationality in valid_iso3 else "IOC"
                    countryName = coco.convert(names=nationality, src=source, to="name_short")
                    code_cache[nationality] = None if countryName == "not found" else countryName
                if code_cache[nationality] is None:
                    unknown_codes.add(nationality)
                    continue
                nationality = code_cache[nationality]

                rows.append((nationality, playerID, nationality))

        # Only touch rows where the value actually changes
        sql_command = """
            UPDATE players
            SET nationality = %s
            WHERE id = %s
                AND nationality IS DISTINCT FROM %s;
        """

        cursor.executemany(sql_command, rows)
        connection.commit()

        print("Nationality given for {} player(s) in the file that are in the players table.".format(len(rows)))
        print("Skipped {} player(s) not in the players table and {} player(s) with no nationality in the file.".format(
            not_in_table, missing_nationality))
        if unknown_codes:
            print("Skipped players with unrecognized nationality code(s): {}".format(sorted(unknown_codes)))

    except FileNotFoundError:
        print("Could not open the file {}. Will not update the nationalities.".format(nationalityFileName))


def updateContracts(connection, cursor, cap_wages_reader):
    """ 
    Function to update contract information from CapWages API
    In API version 1.1, the players are only accessible via their slugs
    So we just loop over all slugs and update all contracts we find from there
    It would be cool to have some way to get recently updated contracts from API
    Maybe this can be discussed with the CapWages people on what could be done

    Arguments:
        connection = Connection object to Postgres database
        cursor = cursor object to Postgres database
        cap_wages_reader = Reader connected to CapWages API to read team information
    """
    
    # CapWages API gives the team name as a full name string
    # For database, we want to transform that into a three letter code
    # To do this, load a helper class
    team_code_finder = team_formatter()
    
    contract_date_corrections = {
        # Known cases where the CapWages API reports an incorrect signing_date
        # (it appears to get copied from an adjacent contract for the same
        # player). Keyed on (player_id, API-reported signing_date, start_season)
        # since start_season comes from the contract's season list and is
        # unaffected by the date bug, making it a reliable disambiguator.
        (8470774, "2008-07-25", 2005): "2005-07-25",
        (8470171, "2008-12-19", 2007): "2006-12-19",
        (8471743, "2017-04-06", 2016): "2016-04-06",
        (8473580, "2014-07-05", 2013): "2013-07-05",
        (8474688, "2015-07-01", 2014): "2014-07-01",
    }
    
    # Pre-fetch valid player_ids and team codes so we can filter out
    # contracts that would otherwise violate a foreign key -- CapWages
    # has contract history for players not yet in our players table
    # (and possibly defunct/unmapped teams), and we want to skip those
    # rows rather than have one bad row abort the whole batch.
    cursor.execute("SELECT id FROM players")
    valid_player_ids = {row[0] for row in cursor.fetchall()}

    cursor.execute("SELECT code FROM teams")
    valid_team_codes = {row[0] for row in cursor.fetchall()}

    sql_command = """
        INSERT INTO contracts (
            player_id, type, signing_date, start_season, end_season, total_value,
            cap_hit, signing_team, signing_gm, expiry_status
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (player_id, signing_date) DO UPDATE SET
            type = EXCLUDED.type,
            start_season = EXCLUDED.start_season,
            end_season = EXCLUDED.end_season,
            total_value = EXCLUDED.total_value,
            cap_hit = EXCLUDED.cap_hit,
            signing_team = EXCLUDED.signing_team,
            signing_gm = EXCLUDED.signing_gm,
            expiry_status = EXCLUDED.expiry_status
        WHERE
            contracts.type          IS DISTINCT FROM EXCLUDED.type OR
            contracts.start_season  IS DISTINCT FROM EXCLUDED.start_season OR
            contracts.end_season    IS DISTINCT FROM EXCLUDED.end_season OR
            contracts.total_value   IS DISTINCT FROM EXCLUDED.total_value OR
            contracts.cap_hit       IS DISTINCT FROM EXCLUDED.cap_hit OR
            contracts.signing_team  IS DISTINCT FROM EXCLUDED.signing_team OR
            contracts.signing_gm    IS DISTINCT FROM EXCLUDED.signing_gm OR
            contracts.expiry_status IS DISTINCT FROM EXCLUDED.expiry_status;
    """

    missed_slugs = []
    skipped_contracts = []
    rows = []

    # Loop over all player slugs
    for i, slug in enumerate(cap_wages_reader.slug_list):

        if i % 100 == 0:
            print(f"Finding contracts for player {i}/{len(cap_wages_reader.slug_list)}")

        try:
            player = cap_wages_reader.get_player_details(slug)

            for contract in player["data"]["contracts"]:

                playerID = player["data"]["nhlId"]

                # There can be cases where nhlId is not available in the players table
                # We need to skip these as we cannot connect the contract to any player in this case
                if playerID is None:
                    continue

                playerID = int(playerID)
                
                # Skip contracts for players not yet in our players table --
                # would violate the player_id foreign key
                if playerID not in valid_player_ids:
                    skipped_contracts.append((playerID, slug, "player_id not in players table"))
                    continue

                contract_type = contract["contractType"]
                signing_date = contract["signingDate"]

                min_season = int(contract["seasons"][0]["season"][:4])
                max_season = int(contract["seasons"][0]["season"][:4])

                for season in contract["seasons"]:
                    current_season = int(season["season"][:4])
                    if current_season < min_season:
                        min_season = current_season
                    if current_season > max_season:
                        max_season = current_season

                # Some players' entry-level (or other) contracts come back from
                # the API with the wrong signing_date -- known cases are
                # corrected here using start_season, which is unaffected by
                # the bug, to identify which contract is really meant.
                correction_key = (playerID, signing_date, min_season)
                if correction_key in contract_date_corrections:
                    signing_date = contract_date_corrections[correction_key]

                total_value = contract["contractValue"]

                # Cap Hit value can be none in some seasons. Try to find cap hit from any season in the contract
                cap_hit = contract["seasons"][0]["capHit"]
                i_season = 1
                while cap_hit is None:
                    if i_season == len(contract["seasons"]):
                        break
                    cap_hit = contract["seasons"][i_season]["capHit"]
                    i_season += 1
                    
                # Extra signing information
                signing_team_full_name = contract["signingTeam"]
                signing_gm = contract["signedBy"]
                expiry_status = contract["expiryStatus"]
                
                # We need to extract the three letter abbreviation from the full team name
                signing_team = team_code_finder.get_team_code(signing_team_full_name)
                
                # Skip contracts whose signing team doesn't resolve to a
                # known code -- would violate the signing_team foreign key
                if signing_team not in valid_team_codes:
                    skipped_contracts.append((playerID, slug, f"unknown signing_team '{signing_team_full_name}'"))
                    continue

                rows.append((
                    playerID,
                    contract_type,
                    signing_date,
                    min_season,
                    max_season,
                    total_value,
                    cap_hit,
                    signing_team,
                    signing_gm,
                    expiry_status
                ))

        except requests.exceptions.HTTPError:
            missed_slugs.append(slug)
            print(f"{i} player {slug} not in API!")

        finally:
            time.sleep(1)  # Do not overwhelm CapWages API

    cursor.executemany(sql_command, rows)
    connection.commit()

    print("Players not in API:")
    print(missed_slugs)
    
    if skipped_contracts:
        skipped_log_path = "skipped_contracts.log"
        with open(skipped_log_path, "w", encoding='utf-8') as f:
            f.write(f"Skipped {len(skipped_contracts)} contract(s) due to missing foreign key targets:\n")
            for playerID, slug, reason in skipped_contracts:
                f.write(f"player_id={playerID} slug={slug}: {reason}\n")
        print(f"Skipped {len(skipped_contracts)} contract(s) -- see {skipped_log_path} for details")


def main():
    """
    Main function. Connects to PostgreSQL database and updates the cities table from input file
    """
    
    # Define all tables that are available in the database
    all_tables = ["players", "nationalities", "teams", "cities", "team_season_stats", "skater_season_stats", "goalie_season_stats", "contracts", "seasons"]
    
    # Read the command line configuration
    parser = argparse.ArgumentParser(
        description="Update selected tables in the NHL database"
    )
    parser.add_argument(
        "--tables",
        nargs="+",
        choices=all_tables + ["all"],
        required=True,
        help=(
            "Which table(s) to update. Space-separated list, e.g. "
            "'--tables cities contracts'. Use 'all' to update every table."
        ),
    )
    parser.add_argument(
        "--cityjson",
        type=str,
        default="nhlPlayerHomeTownsFrom2008To2026.json",
        help=(
            "JSON file containing the player birth city information"
        ),
    )
    parser.add_argument(
        "--slugfile",
        type=str,
        default=None,
        help=(
            "Text file with slugs for players whose contracts are updated."
        ),
    )
    parser.add_argument(
        "--newestseason",
        type=int,
        default=2026,
        help=(
            "Newest season (start year, 2026 = 2026-2027) read when updating the players table"
        ),
    )
    parser.add_argument(
        "--oldestseason",
        type=int,
        default=2026,
        help=(
            "Oldest season (start year) read when updating the players table"
        ),
    )
    parser.add_argument(
        "--nationalityfile",
        type=str,
        default="moneyPuck/playerBiography.csv",
        help=(
            "CSV file containing nationalities for the players."
        ),
    )
    parser.add_argument(
        "--remote",
        action="store_true",
        help=(
            "If set, updates the database in REMOTE_URL instead of POSTGRES_URL"
        ),
    )
    args = parser.parse_args()
    
    # Based on the tables argument, select which tables to update in the database
    tables_to_update = all_tables if "all" in args.tables else args.tables

    # Connect to the Postgres database
    connection = get_connection(args.remote)
    cursor = connection.cursor()
    
    # Print that connection has been established
    database_type = "remote" if args.remote else "local"
    print("Connected to {} database".format(database_type))
    
    # Update the cities table
    if "cities" in tables_to_update:
        updateCities(connection, cursor, args.cityjson)
        
    # Update the players table
    # This is done after cities (birth_city refers to it) and before contracts (player_id refers to players)
    if "players" in tables_to_update:
        if args.oldestseason > args.newestseason:
            parser.error("--oldestseason must not be later than --newestseason")
        nhl_client = NHLClient()
        updatePlayers(connection, cursor, nhl_client, args.newestseason, args.oldestseason)
        
    # Update player nationalities in players table
    if "nationalities" in tables_to_update:
        updateNationalities(connection, cursor, args.nationalityfile)

    # Update the constracts table
    if "contracts" in tables_to_update:
    
        # Create a CapWagerReader and initialize it with API key
        cap_wages_reader = CapWagesReader()
        cap_wages_reader.set_dotenv_API_key("API_KEY")
        
        # If slugfile is given, only update those players
        # Otherwise go through all player contracts
        if args.slugfile == None:
            cap_wages_reader.find_all_player_slugs()
        else:
            cap_wages_reader.read_slugs_from_file(args.slugfile)
    
        # Update the database for all the player slugs available
        updateContracts(connection, cursor, cap_wages_reader)
        
        # Run sanity check for cap hits in the table
        sql_command = """
            UPDATE contracts
            SET cap_hit = total_value
            WHERE type ILIKE '%%entry%%'
                AND cap_hit IS NOT NULL
                AND total_value IS NOT NULL
                AND cap_hit > total_value
                AND start_season = end_season;
        """
        try:
            cursor.execute(sql_command)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    
    # TODO: Update all other types of tables
    
    # Close the connection
    connection.close()
        

# Follow good coding practices
if __name__ == "__main__":
    main()
