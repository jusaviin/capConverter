# Create a SQLite database for the NHL and fill in some information
# Notice that all previous tables from the database are wiped using this script
# TODO: There should be some options on which information to fill

# Required imports
import sqlite3
import json
import time
import pandas
import warnings
import requests

# The code gives performance warnings for the pandas dataframes.
# The dataframe here is only used to transfer data from csv files to SQLite database.
# Thus we do not care about these warnings, and can safely suppress them.
warnings.simplefilter(action='ignore', category=pandas.errors.PerformanceWarning)

from nhlpy import NHLClient
from manualDataEntry import NHLTeamData, NHLSeasonData
from helperFunctions import cityFormatter, getAccentedName, add_quotes
from capWagesReader import CapWagesReader

# MoneyPuck has inconsistent team names. Transform all to follow NHL API convention.
moneyPuckDecoder = {"L.A": "LAK",
                    "N.J": "NJD",
                    "T.B": "TBL",
                    "S.J": "SJS"}

def fillSeasons(connection, cursor):
    """ 
    Function for filling the season table in the database

    Arguments:
        connection = Connection object to SQLite database
        cursor = cursor object to SQLite database
    """
    
    # Start by creating on object that finds manually collected season data
    data_provider = NHLSeasonData()
    
    # Find all the seasons we have salary cap data about
    all_seasons = data_provider.get_season_list()
    
    # Loop over all seasons and add information about them to the database
    for season in all_seasons:
        
        sql_command = f"""INSERT INTO seasons (season, salary_cap, cap_floor) 
                          VALUES ({season}, {data_provider.get_salary_cap(season)}, {data_provider.get_cap_floor(season)});"""
                
        # Once the command has been compiled, we can execute it
        cursor.execute(sql_command)
                
    # Once all commands have been execute to the cursor, save them to database by committing them
    connection.commit()
    

def fillPlayers(connection, cursor, nhl_client):
    """ 
    Function for filling the players table in the database
    All the players from NHL API that are included in season rosters for teams are included
    There might be inconsistensies between MoneyPuck and NHL API, these will be solved later
    Notice that player stats will be in another table

    Arguments:
        connection = Connection object to SQLite database
        cursor = cursor object to SQLite database
        nhl_client = Client connected to NHL API to read team information
    """
    
    # We need to avoid adding same players multiple times
    # Remember the player ID of all the added players, and only add new players if ID not already in database
    added_players = []
    
    # Create a formatter class for city names
    cityHelper = cityFormatter()
    
    # Loop over all the seasons we want to include in the database
    for season in range(2025, 2007, -1):
    
        # Create a season string from the season number
        seasonString = "{}{}".format(season, season+1)
        print("Filling players table for season " + seasonString)
        
        teams = nhl_client.teams.teams(date="{}-01-30".format(season+1))
        time.sleep(1) # Do not overwhelm NHL API with excessive requests
        
        for team in teams:
    
            # Get the end-of-season roster for the studied team
            roster = nhl_client.teams.team_roster(team_abbr=team["abbr"], season=seasonString)
            time.sleep(1) # Do not overwhelm NHL API with excessive requests
        
            # Loop over all the players in the roster
            for position in roster:
                for player in roster[position]:
                
                    # Avoid adding same player from multiple seasons
                    if player["id"] in added_players:
                        continue
            
                    # Gather the player information
                    first_name = getAccentedName(player, "firstName")
                    last_name = getAccentedName(player, "lastName")
                    birth_city, _, _ = cityHelper.formatCityName(player)
                    birth_date = player.get("birthDate", "NULL")
                    position = player.get("positionCode", "NULL")
                    handedness = player.get("shootsCatches", "NULL")
                    headshot = player.get("headshot", "NULL")
                    height = player.get("heightInCentimeters", "NULL")
                    weight = player.get("weightInKilograms", "NULL")
                
                    # Compile the SQL command
                    sql_command = f"""INSERT INTO players (id, first_name, last_name, birth_city, birth_date, position, handedness, headshot, height, weight) VALUES ({player["id"]}, \"{first_name}\", \"{last_name}\", \"{birth_city}\", \"{birth_date}\", \"{position}\", \"{handedness}\", \"{headshot}\", {height}, {weight});"""
                
                    # Once the command has been compiled, we can execute it
                    cursor.execute(sql_command)
                    
                    # Mark that this player is already in the database
                    added_players.append(player["id"])
                
            # Commit the changes one team at a time
            connection.commit()
   
def fillTeams(connection, cursor, nhl_client):
    """ 
    Function for filling the teams table in the database

    Arguments:
        connection = Connection object to SQLite database
        cursor = cursor object to SQLite database
        nhl_client = Client connected to NHL API to read team information
    """
    
    # Start by creating on object that finds manually collected data
    data_provider = NHLTeamData()
    
    # Find all the teams that have played in NHL between 2008 and current date
    # Fill their information from the database for the latest season they have participated
    added_teams = []
    
    # To optimize the performance, we can only check the seasons that actually add more teams to the list
    for season in [2026, 2024, 2014, 2011]:
        teams = nhl_client.teams.teams(date="{}-01-30".format(season))
        time.sleep(1) # Do not overwhelm NHL API with excessive requests
        
        for team in teams:
            if team["abbr"] not in added_teams:
                sql_command = f"""INSERT INTO teams (code, name, city, logo, arena, arena_capacity, arena_latitude, arena_longitude) VALUES (\"{team["abbr"]}\", \"{team["name"]}\", \"{data_provider.get_city(team["abbr"])}\", \"{team["logo"]}\", \"{data_provider.get_arena(team["abbr"])}\", {data_provider.get_arena_capacity(team["abbr"])}, {data_provider.get_arena_latitude(team["abbr"])}, {data_provider.get_arena_longitude(team["abbr"])});"""
                
                # Once the command has been compiled, we can execute it
                cursor.execute(sql_command)
                
                # Do not add the same team again
                added_teams.append(team["abbr"])
                
    # Once all commands have been execute to the cursor, save them to database by committing them
    connection.commit()
    
 
def fillCities(connection, cursor, cityFileName):
    """ 
    Function for filling the cities table in the database

    Arguments:
        connection = Connection object to SQLite database
        cursor = cursor object to SQLite database
        cityFileName = json file from which the city information is read
    """

    # Insert city information from json file
    try:
        with open(cityFileName, "r", encoding='utf-8') as f:
            cityLocations = json.load(f)
            print("Filling the cities table from file {}.".format(cityFileName))
        
            # Add all the VALUES for the INSERT command for all cities
            for cityCode in cityLocations:
            
                name_local = add_quotes(cityLocations[cityCode]["nameLocal"])
                name_english = add_quotes(cityLocations[cityCode]["nameEnglish"])
                country = add_quotes(cityLocations[cityCode].get("country","NULL"))
                state = add_quotes(cityLocations[cityCode].get("state","NULL"))
                state_code = add_quotes(cityLocations[cityCode].get("state_code","NULL"))
                latitude = cityLocations[cityCode]["coordinates"][0]
                longitude = cityLocations[cityCode]["coordinates"][1]
        
                # INSERT new values and UPDATE existing values
                sql_command = f"""INSERT INTO cities (name_NHL_API, name_local, name_english, country, state, state_code, latitude, longitude) VALUES (\"{cityCode}\", {name_local}, {name_english}, {country}, {state}, {state_code}, {latitude}, {longitude})
                    ON CONFLICT(name_NHL_API) DO UPDATE SET
                    name_local = excluded.name_local, name_english = excluded.name_english,
                    country = excluded.country, state = excluded.state, state_code = excluded.state_code,
                    latitude = excluded.latitude, longitude = excluded.longitude;"""
            
                # Once the command has been compiled, we can execute it
                cursor.execute(sql_command)
            
            # Commit the changes to save them to the database
            connection.commit()
        
        
    except FileNotFoundError:
        print("Could not open the file {}. Will not fill the cities table.".format(cityFileName))
 
 
def fillMoneyPuckSeasonStats(connection, rename_column, drop_column, input_tag, output_table):
    """ 
    Function for filling the MoneyPuck statistics for all seasons since 2008

    Arguments:
        connection = Connection object to SQLite database
        rename_column = Dictionary of column names to be renames
        drop_column = List of columns names to be dropped from table before writing to SQL database
        input_tag = Tag identifying the input file
        output_table = Table name in the database to which stats are written
    """
    
    # First collect all data to memory:
    all_data = []
    
    # Loop over all the seasons we want to include in the database
    for season in range(2025, 2007, -1):
    
        for phase in ["regular", "playoffs"]:
        
            # There is no playoff data yet for 2025 season
            if season == 2025 and phase == "playoffs":
                continue
        
            # Regular season or playoffs stats for the teams
            moneyPuck_stats = pandas.read_csv("moneyPuck/{}_{}_{}.csv".format(input_tag, season, phase))
        
            # Assign a new column for phase of season
            moneyPuck_stats = moneyPuck_stats.assign(phase=phase)
            
            # Rename some columns to make them consistent between tables
            # We need to do this at this point as some columns are inconsistent between years
            moneyPuck_stats.rename(columns=rename_column, inplace=True)
            
            # Collect the stats to all_team_data list
            all_data.append(moneyPuck_stats)
            
    # Combine all data into a single dataframe
    data_for_sql = pandas.concat(all_data, ignore_index=True)
    
    # Decode team names
    data_for_sql["team"] = data_for_sql["team"].replace(moneyPuckDecoder)
    
    # Drop unwanted columns from the combined dataframe to get better performance
    data_for_sql.drop(columns=drop_column, inplace=True)
        
    # Write the combined dataframe to the database
    data_for_sql.to_sql(name=output_table, con=connection, index=False, if_exists="append") 
 
def fillTeamStats(connection):
    """ 
    Function for filling the team statistics for all seasons since 2008

    Arguments:
        connection = Connection object to SQLite database
    """
    
    # Collect the team specific information
    rename_column = {"iceTime": "icetime", "penalityMinutesFor": "penaltyMinutesFor", "penalityMinutesAgainst": "penaltyMinutesAgainst", "penalitiesFor": "penaltiesFor", "penalitiesAgainst": "penaltiesAgainst"}
    drop_column = ["name", "team.1", "position"]
    input_tag = "teams"
    output_table = "team_season_stats"
    
    # Fill MoneyPuck stats with the defined information
    fillMoneyPuckSeasonStats(connection, rename_column, drop_column, input_tag, output_table)
 
def fillGoalieStats(connection):
    """ 
    Function for filling the team statistics for all seasons since 2008

    Arguments:
        connection = Connection object to SQLite database
    """
    
    # Collect the goalie specific information
    rename_column = {"penalityMinutes": "penaltyMinutes"}
    drop_column = ["name", "position"]
    input_tag = "goalies"
    output_table = "goalie_season_stats"
    
    # Fill MoneyPuck stats with the defined information
    fillMoneyPuckSeasonStats(connection, rename_column, drop_column, input_tag, output_table)
    
            
def fillSkaterStats(connection):
    """ 
    Function for filling the team statistics for all seasons since 2008

    Arguments:
        connection = Connection object to SQLite database
    """
    
    # Collect the skater specific information
    rename_column = {"penalityMinutes": "penaltyMinutes", "penalityMinutesDrawn": "penaltyMinutesDrawn"}
    drop_column = ["name", "position", "I_F_shifts", "I_F_penalityMinutes", "I_F_faceOffsWon"]
    input_tag = "skaters"
    output_table = "skater_season_stats"
    
    # Fill MoneyPuck stats with the defined information
    fillMoneyPuckSeasonStats(connection, rename_column, drop_column, input_tag, output_table)
  
  
def fillContracts(connection, cursor, cap_wages_reader):
    """ 
    Function contract information from CapWages API
    In API version 1.1, the players are only accessible via their slugs
    So we just loop over all slugs and fill all contracts we find from there

    Arguments:
        connection = Connection object to SQLite database
        cursor = cursor object to SQLite database
        cap_wages_reader = Reader connected to CapWages API to read team information
    """
    
    missed_slugs = []
    
    # Loop over all player slugs
    for i, slug in enumerate(cap_wages_reader.slug_list):
    
        if i % 100 == 0:
            print(f"Finding contracts for player {i}/{len(cap_wages_reader.slug_list)}")
            
        # DEBUG
        #print("Finding info for slug {}".format(slug))
    
        # Find the player details from the slug
        try:
            player = cap_wages_reader.get_player_details(slug)
        
    
            # Loop over all contracts the player has
            for contract in player["data"]["contracts"]:

                playerID = player["data"]["nhlId"]
            
                # There can be cases where nhlId is not included with the player
                # We need to skip these as we cannot connect the contract to any player in this case
                if playerID is None:
                    continue
                
                # Convert playerID from string to int
                playerID = int(playerID)
            
                # Collect the rest of the relevent information
                type = contract["contractType"]
                date = contract["signingDate"]
    
                min_season = int(contract["seasons"][0]["season"][:4])
                max_season = int(contract["seasons"][0]["season"][:4])
    
                for season in contract["seasons"]:
                    current_season = int(season["season"][:4])
         
                    if current_season < min_season:
                        min_season = current_season
             
                    if current_season > max_season:
                        max_season = current_season
             
                total_value = contract["contractValue"]
                
                # Cap Hit value can be none in some seasons. Try to find cap hit from any season in the contract
                cap_hit = contract["seasons"][0]["capHit"]
                i_season = 1
                while cap_hit is None:
                
                    # None of the seasons has cap hit! Hopyfully this does not happen...
                    if i_season == len(contract["seasons"]):
                        break
                    
                    # See if the next season in the list has not None cap hit
                    cap_hit = contract["seasons"][i_season]["capHit"]
                    i_season = i_season + 1
    
                
                # Once relevant contract information is gathered, compile the SQL command
                sql_command = f"""INSERT INTO contracts (player_id, type, signing_date, start_season, end_season, total_value, cap_hit) VALUES ({playerID}, \"{type}\", \"{date}\", {min_season}, {max_season}, {total_value}, {cap_hit});"""
                
                # Once the command has been compiled, we can execute it
                cursor.execute(sql_command)
                
        except requests.exceptions.HTTPError:
            missed_slugs.append(slug)
            
            #DEBUG
            print(f"{i} player {slug} not in API!")
        
        finally:
            time.sleep(1) # Do not overwhelm CapWages API
                    
                
    # Commit all changes to the database in the end
    connection.commit()
    
    # DEBUG
    print("Players not in API:")
    print(missed_slugs)
     
def main():
    """
    Main function. Connects to SQLite database and calls methods to fill it.
    """
    
    # Create a client for information to be read from NHL API
    nhl_client = NHLClient()

    # Connect to the SQLite3 database
    databaseName = "nhlDatabase.db"
    connection = sqlite3.connect(databaseName)
    cursor = connection.cursor()
    print("Connected to database {}".format(databaseName))
    
    # Initialize the tables
    initializeTables = False
    if initializeTables:
        initializationFile = "databaseSchema.sql"
        with open(initializationFile, 'r') as sql_file:
            sql_script = sql_file.read()

        # Use a cursor for updating information and run the initialization script
        cursor.executescript(sql_script)
        print("Initialized the tables from file {}".format(initializationFile))
        
    # Development addition: initialize a subset of tables
    # TODO: Remove after database schema is finalized
    initializeDebugTables = False
    if initializeDebugTables:
        initializationFile = "databaseDebugSchema.sql"
        with open(initializationFile, 'r') as sql_file:
            sql_script = sql_file.read()

        # Use a cursor for updating information and run the initialization script
        cursor.executescript(sql_script)
        print("Initialized the tables from file {}".format(initializationFile))
    
    # Fill information from NHL API
    fillNHLAPI = False
    if fillNHLAPI:

        # Fill the cities table
        cityFileName = "nhlPlayerHomeTownsFrom2008To2026.json"
        fillCities(connection, cursor, cityFileName)
        print("Cities table ready")
    
        # Fill the teams table
        print("Filling teams table")
        fillTeams(connection, cursor, nhl_client)
        print("Teams table ready")
    
        # Fill the players table
        print("Filling players table")
        fillPlayers(connection, cursor, nhl_client)
        print("Players table ready")
        
    # Fill information from MoneyPuck csv files
    fillMoneyPuck = False
    if fillMoneyPuck:
        print("Filling stats from MoneyPuck")
    
        # Fill the teams information from MoneyPuck
        fillTeamStats(connection)
        fillGoalieStats(connection)
        fillSkaterStats(connection)
        
    # Fill contract information from CapWages API
    fillCapWagesContracts = False
    if fillCapWagesContracts:
        
        # Create a reader to access CapWages API
        cap_wages_reader = CapWagesReader()
        cap_wages_reader.set_dotenv_API_key("API_KEY")
        
        # Filling can be done in parts by adjusting values here
        n_players_per_page = 100
        first_page = 1
        last_page = 70
        cap_wages_reader.find_player_slugs(n_players_per_page, first_page, last_page)
        
        # Fill the contracts to the database
        fillContracts(connection, cursor, cap_wages_reader)

    # Fill season table with manually obtained information
    fillSeasonTable = True
    if fillSeasonTable:
    
        fillSeasons(connection, cursor)

    # Close the connection
    connection.close()
        

# Follow good coding practices
if __name__ == "__main__":
    main()
