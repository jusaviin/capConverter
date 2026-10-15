from nhlpy import NHLClient
from geopy.geocoders import Nominatim
from manualDataEntry import NHLTeamData
from helperFunctions import cityFormatter, get_unique_player_ids
import argparse
import time
import json

def addCityToDictionary(geolocator, cityLocations, city, state_code, country = ""):
    """
    Function for adding a new city to the city locations dictionary
    
    Arguments:
        geolocator = Nominatim object for geolocating the cities
        city = City name formatted according to NHL API rules
        cityLocation = Dictionary to which the city infomation is added
        state_code = Two letter abbreviation for state in USA and Canada
        country = Country in which the city is located
    """
    
    # There are some city names in North America that are copied from Europe.
    # In order for the geolocator to find these reliably, provide also USA or
    # Canada to the locator in case state_code is provided but country is not
    if country == "" and state_code != "":
        if state_code in ["AB", "BC", "MB", "NB", "NL", "NT", "NS", "NU", "ON", "PE", "QC", "SK", "YT"]:
            country = ", Canada"
        else:
            country = ", United States"
            
    # Some cities in NHL API are misspelled, which breaks the geolocator
    # Manually fix these misspellings here
    cityLocator = city
    if cityLocator == "St-Francois de Madaw, NB":
        # Saint-François-de-Madawaska is cut short
        cityLocator = "St-Francois de Madawaska, NB"
    elif cityLocator == "Maters" and country == ", Switzerland":
        # Naters is misspelled as Maters
        cityLocator = "Naters"
    elif cityLocator == "Ljunby" and country == ", Sweden":
        # Ljungby is misspelled as Ljunby
        cityLocator = "Ljungby"
    elif cityLocator == "Garden River, First Nations, ON":
        # First Nations throws the geolocator off here
        cityLocator = "Garden River, ON"
        
    
    # Geolocate the city and find its latitude and longitude
    location = geolocator.geocode(cityLocator + country)
    cityInfo = {}
    cityInfo["coordinates"] = [location.latitude, location.longitude]
                
    # This gives the city name in local language
    cityInfo["nameLocal"] = location.raw['name']
                    
    # We also want to use the city name in english. Read that too
    time.sleep(1)  # Can only make 1 Nominatim request per second
    location = geolocator.geocode(cityLocator + country, language="en")
    cityInfo["nameEnglish"] = location.raw['name']
                    
    # Also remember the country and state information in English
    display_name = location.raw["display_name"]
    country = display_name.split(",")[-1].strip()
    state_full = display_name.split(",")[-2].strip()
    
    # In some cases the second last item in display_name gives zip code
    # If this is the case, we need to read the third last split for the state information
    if any(char.isdigit() for char in state_full):
        state_full = display_name.split(",")[-3].strip()
                  
    # Only apply state information for Unites States and Canada
    cityInfo["country"] = country
    if country in ["United States", "Canada"]:
        cityInfo["state"] = state_full
        cityInfo["state_code"] = state_code
                    
                
    # Add the city info to the cityLocations dictionary
    cityLocations[city] = cityInfo
    time.sleep(1)  # Can only make 1 Nominatim request per second
    

def jsonFileName(value):
    """
    Argparse type for validating that the given file name has a .json extension
    """
    if not value.lower().endswith(".json"):
        raise argparse.ArgumentTypeError(
            "file name must have a .json extension, got '{}'".format(value))
    return value


def parseArguments():
    """
    Define and parse the command line arguments.

    Seasons can be given either as a range (--firstseason and --lastseason)
    or as an explicit list of not necessarily consecutive seasons (--seasons).
    The two ways of selecting seasons cannot be combined. If neither is given,
    only the season 2026 is used.
    """
    parser = argparse.ArgumentParser(
        description="Create or update a json file with information about birth cities "
                    "of NHL players and home cities of NHL teams.")

    parser.add_argument("--cityfilename", type=jsonFileName,
                        default="cityCoordinatesUpdatedAgain.json",
                        help="json file to create or update (default: %(default)s)")
    parser.add_argument("--firstseason", type=int, default=None,
                        help="first season of the range to scan, given as the starting "
                             "year, e.g. 2026 for season 2026-2027 (default: 2026)")
    parser.add_argument("--lastseason", type=int, default=None,
                        help="last season of the range to scan, given as the starting "
                             "year (default: 2026)")
    parser.add_argument("--seasons", type=int, nargs="+", default=None,
                        help="explicit list of seasons to scan, given as starting years, "
                             "e.g. --seasons 2018 2021 2026. Cannot be combined with "
                             "--firstseason or --lastseason")
    parser.add_argument("--logfile", type=str, default=None,
                        help=("Log file containing players that were skipped when trying to fill stats tables.")
    )
                             

    args = parser.parse_args()

    # Work out which seasons to scan
    if args.seasons is not None:
        if args.firstseason is not None or args.lastseason is not None:
            parser.error("--seasons cannot be combined with --firstseason or --lastseason")
        startYears = args.seasons
    else:
        first = args.firstseason if args.firstseason is not None else 2026
        last = args.lastseason if args.lastseason is not None else 2026
        if first > last:
            parser.error("--firstseason ({}) cannot be later than --lastseason ({})".format(first, last))
        startYears = range(first, last + 1)

    # NHL API wants seasons in format 20262027. Remove duplicates and sort chronologically
    args.seasonList = [seasonFormatter(year) for year in sorted(set(startYears))]
    return args


def seasonFormatter(startYear):
    """
    Convert the starting year of a season to the format used by NHL API
    Example: 2026 -> "20262027"
    """
    return "{}{}".format(startYear, startYear + 1)


def main():
    """
    Main program. Creates a json file with information about birth cities of NHL players.
    Also cities of all the teams are added to the json file
    """

    # Read the settings from the command line
    args = parseArguments()

    # The city file we want to modify/create
    cityFileName = args.cityfilename

    # If the json file exists, append new cities to that
    # If it does not exist, create a new one
    cityLocations = {}
    try:
        with open(cityFileName, "r", encoding='utf-8') as f:
            cityLocations = json.load(f)
            print("Updating city dictionary in file {}".format(cityFileName))
    except FileNotFoundError:
        print("Creating a new city dictionary with file name {}".format(cityFileName))
        
    # Create the geolocator to find the city coordinates from city name
    geolocator = Nominatim(user_agent="nhlCityLocationCreator")
        
    # Start by adding all the cities from where the NHL teams are from
    # All teams that have played in the league since 2008 are included
    # For some reason cities are not included in NHL API, so adding them manually
    data_finder = NHLTeamData()
    nhlCities = data_finder.get_all_cities()
        
    print("Locating team home cities")
    for city in nhlCities:
        if city not in cityLocations:
            addCityToDictionary(geolocator, cityLocations, city, city[-2:])
    
    # Once the home cities of the teams are gone through, go through all the players

    # Create a city formatter class
    cityHelper = cityFormatter()

    # Prepare the NHL client
    client = NHLClient()

    # The seasons for which the rosters are scanned (format 20262027)
    seasons = args.seasonList

    if args.logfile == None:
        # If we are not given an explicit log of player IDs, search all players in a given season
   
        # Loop over seasons
        for currentSeason in seasons:
            print("Finding cities for all players for {} season".format(currentSeason))
        
            # Find all the teams that were playing in the given season
            teams = client.teams.teams(date="{}-10-01".format(currentSeason[:4]))
            time.sleep(1)

            # Loop over teams that played in the NHL the given season
            for team in teams:

                # Print a message that we are finding cities for a spacific team
                print("Finding city locations for {}".format(team['name']))

                # Loop over all players in the given team
                roster = client.teams.team_roster(team_abbr=team['abbr'], season = currentSeason)
                for position in roster:
                    for player in roster[position]:
            
                        # Get the city and state information in a nice format
                        city, state, country = cityHelper.formatCityName(player)
        
                        # If the city is not already in the cityLocations dictionary, find its coordinates
                        # and add it to the dictionary
                        if city not in cityLocations:
                            addCityToDictionary(geolocator, cityLocations, city, state, country)
                            
    else:
        # If we are given a player ID log, only search for players in the log
        
        searched_ids = get_unique_player_ids(args.logfile)
        for player_id in searched_ids:
            
            # Find the career stats record for the current ID
            player = client.stats.player_career_stats(player_id=player_id)
            time.sleep(1)
        
            city, state, country = cityHelper.formatCityName(player, "playerId")
            
            # If the city is not already in the cityLocations dictionary, find its coordinates
            # and add it to the dictionary
            if city not in cityLocations:
                addCityToDictionary(geolocator, cityLocations, city, state, country)
        

    # After all the city locations have been gone through, save the output to json file
    with open(cityFileName, "w", encoding='utf-8') as f:
        json.dump(cityLocations, f, indent=4, ensure_ascii=False)

# Follow good coding practices
if __name__ == "__main__":
    main()
