# Update the cities table in the database based on input json

# Required imports
import argparse
import psycopg2
import json
import time
import requests
from database_helper import get_connection
from capWagesReader import CapWagesReader
from helperFunctions import team_formatter
 
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
    all_tables = ["players", "teams", "cities", "team_season_stats", "skater_season_stats", "goalie_season_stats", "contracts", "seasons"]
    
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
        
    # Update the constracts table
    if "contracts" in tables_to_update:
    
        # Create a CapWagerReader and find the player slugs to be updated to the database
        cap_wages_reader = CapWagesReader()
        cap_wages_reader.set_dotenv_API_key("API_KEY")
        cap_wages_reader.find_all_player_slugs()
    
        # Update the database for all the player slugs available
        updateContracts(connection, cursor, cap_wages_reader)
    
    # TODO: Update all other types of tables

    # Close the connection
    connection.close()
        

# Follow good coding practices
if __name__ == "__main__":
    main()
