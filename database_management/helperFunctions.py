import country_converter as coco
from manualDataEntry import NHLPlayerData

class cityFormatter():

    def __init__(self):
        
        # Dictionary to format US states and Canadian provinces into two letter abbreviations
        self.states = {
            # US States
            "Alabama": "AL",
            "Alaska": "AK",
            "Arizona": "AZ",
            "Arkansas": "AR",
            "California": "CA",
            "Colorado": "CO",
            "Connecticut": "CT",
            "Delaware": "DE",
            "Florida": "FL",
            "Georgia": "GA",
            "Hawaii": "HI",
            "Hawa'ii": "HI",
            "Idaho": "ID",
            "Illinois": "IL",
            "Indiana": "IN",
            "Iowa": "IA",
            "Kansas": "KS",
            "Kentucky": "KY",
            "Louisiana": "LA",
            "Maine": "ME",
            "Maryland": "MD",
            "Massachusetts": "MA",
            "Michigan": "MI",
            "Minnesota": "MN",
            "Mississippi": "MS",
            "Missouri": "MO",
            "Montana": "MT",
            "Nebraska": "NE",
            "Nevada": "NV",
            "New Hampshire": "NH",
            "New Jersey": "NJ",
            "New Mexico": "NM",
            "New York": "NY",
            "North Carolina": "NC",
            "North Dakota": "ND",
            "Ohio": "OH",
            "Oklahoma": "OK",
            "Oregon": "OR",
            "Pennsylvania": "PA",
            "Rhode Island": "RI",
            "South Carolina": "SC",
            "South Dakota": "SD",
            "Tennessee": "TN",
            "Texas": "TX",
            "Utah": "UT",
            "Vermont": "VT",
            "Virginia": "VA",
            "Washington": "WA",
            "West Virginia": "WV",
            "Wisconsin": "WI",
            "Wyoming": "WY",
            # Canadian Provinces and Territories
            "Alberta": "AB",
            "British Columbia": "BC",
            "Manitoba": "MB",
            "New Brunswick": "NB",
            "Newfoundland and Labrador": "NL",
            "Nova Scotia": "NS",
            "Ontario": "ON",
            "Prince Edward Island": "PE",
            "Quebec": "QC",
            "Québec": "QC",
            "Saskatchewan": "SK",
            "Northwest Territories": "NT",
            "Nunavut": "NU",
            "Yukon": "YT"
        }

    def formatCityName(self, player):
        """
        Format the birth city of a player from NHL API dictionary to a good format
    
        Argument:
            player: Player dictionary read from NHL API
        
        Return:
            Birth city, state, and country for the player
        """
            
        city = ""
        state = ""
        if "birthStateProvince" in player:
            plain_state = self.states.get(player["birthStateProvince"]["default"], player["birthStateProvince"]["default"])
            state = ", {}".format(plain_state)
        
        # There are players who are missing birth city
        # These cases have been fixed by manually entering the missing data
        if "birthCity" in player:
            city = player["birthCity"]["default"] + state
            countryCode = player["birthCountry"]
        else:
            data_provider = NHLPlayerData()
            city = data_provider.get_birth_city(player["id"])
            state = data_provider.get_birth_state(player["id"])
            countryCode = data_provider.get_birth_country(player["id"])
        
            if state != "":
                state = ", {}".format(state)
                city = city + state
    
        # Transform the country code to full country name to be used in geolocation
        # Comma is there so separate country from the name for the geolocator
        country = ", " + coco.convert(names=countryCode, to="name_short")
    
        return city, state[2:], country
        
        
class team_formatter():

    def __init__(self):
        
        # Dictionary linking full team names to their three letter code
        self.teams = {
            "Colorado Avalanche": "COL",
            "Tampa Bay Lightning": "TBL",
            "Minnesota Wild": "MIN",
            "Carolina Hurricanes": "CAR",
            "Dallas Stars": "DAL",
            "Detroit Red Wings": "DET",
            "Buffalo Sabres": "BUF",
            "Montréal Canadiens": "MTL",
            "Montreal Canadiens": "MTL",
            "Boston Bruins": "BOS",
            "Pittsburgh Penguins": "PIT",
            "New York Islanders": "NYI",
            "Vegas Golden Knights": "VGK",
            "Edmonton Oilers": "EDM",
            "Utah Mammoth": "UTA",
            "Utah Hockey Club": "UTA",
            "Florida Panthers": "FLA",
            "Seattle Kraken": "SEA",
            "Columbus Blue Jackets": "CBJ",
            "Anaheim Ducks": "ANA",
            "Washington Capitals": "WSH",
            "San Jose Sharks": "SJS",
            "New Jersey Devils": "NJD",
            "Los Angeles Kings": "LAK",
            "Ottawa Senators": "OTT",
            "Philadelphia Flyers": "PHI",
            "Toronto Maple Leafs": "TOR",
            "Nashville Predators": "NSH",
            "Chicago Blackhawks": "CHI",
            "New York Rangers": "NYR",
            "Winnipeg Jets": "WPG",
            "St. Louis Blues": "STL",
            "Calgary Flames": "CGY",
            "Vancouver Canucks": "VAN",
            "Arizona Coyotes": "ARI",
            "Phoenix Coyotes": "PHX",
            "Atlanta Thrashers": "ATL",
            "Avalanche": "COL",
            "Lightning": "TBL",
            "Wild": "MIN",
            "Hurricanes": "CAR",
            "Stars": "DAL",
            "Red Wings": "DET",
            "Sabres": "BUF",
            "Canadiens": "MTL",
            "Bruins": "BOS",
            "Penguins": "PIT",
            "Islanders": "NYI",
            "Golden Knights": "VGK",
            "Oilers": "EDM",
            "Mammoth": "UTA",
            "Panthers": "FLA",
            "Kraken": "SEA",
            "Blue Jackets": "CBJ",
            "Ducks": "ANA",
            "Capitals": "WSH",
            "Sharks": "SJS",
            "Devils": "NJD",
            "Kings": "LAK",
            "Senators": "OTT",
            "Flyers": "PHI",
            "Maple Leafs": "TOR",
            "Predators": "NSH",
            "Blackhawks": "CHI",
            "Rangers": "NYR",
            "Jets": "WPG",
            "Blues": "STL",
            "Flames": "CGY",
            "Canucks": "VAN",
            "Coyotes": "ARI",
            "Thrashers": "ATL"
        }

    def get_team_code(self, team_name):
        """
        Get the team code from team name
    
        Argument:
            team_name: Full team name
        
        Return:
            Three letter team code corresponding to the team name
        """
    
        return self.teams.get(team_name, "Not found")

def getAccentedName(player, nameString):
    """ 
    Function for getting player name using local spelling if possible

    Arguments:
        player = Dictionary containing player data from NHL API
        nameString = Can be either firstname or lastname
        
    Return:
        Properly accented player name
    """
    
    # If there are no alternative formats for the name, return default format
    if len(player[nameString]) == 1:
        return player[nameString]["default"]
        
    # If there are other formats, try to find the local language
    if player["birthCountry"] == "FIN":
        if "fi" in player[nameString]:
            return player[nameString]["fi"]
            
    if player["birthCountry"] == "SWE" or player["birthCountry"] == "DNK" or player["birthCountry"] == "NOR":
        if "sv" in player[nameString]:
            return player[nameString]["sv"]
            
    if player["birthCountry"] == "CZE" or player["birthCountry"] == "SVK":
        if "cs" in player[nameString]:
            return player[nameString]["cs"]
            
    if player["birthCountry"] == "DEU" or player["birthCountry"] == "CHE":
        if "de" in player[nameString]:
            return player[nameString]["de"]
            
    if player["birthCountry"] == "AUT":
        if "de" in player[nameString]:
            return player[nameString]["de"]
        if "cs" in player[nameString]:
            return player[nameString]["cs"]
            
    # There are a lot of Canadian players that might have French pronunciation for their name
    # This might be valid also for French and Swiss players, so do not have country specific argument
    if "fr" in player[nameString]:
        return player[nameString]["fr"]
            
        
    # If we cannot find properly accented name, just use the default name
    return player[nameString]["default"]


def add_quotes(input_string):
    """ 
    Function for adding quotes around a string. Do not do this for "NULL" string

    Arguments:
        input_string = String needing quotes

    Return:
        input_string enclosed in quotes, unless the input_string is "NULL"
    """
    
    if input_string == "NULL":
        return input_string
    
    return "\"" + input_string + "\""
