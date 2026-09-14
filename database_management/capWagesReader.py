# Class for reading information from CapWages API

import requests
import time
import os
from dotenv import load_dotenv

class CapWagesReader():

    def __init__(self, API_key = None, slug_list = []):
        """
        Initialize the class.

        Arguments:
            API_key = You will need an API key to access CapWages API. Provide the key here
            slug_dict = List of player slugs available in CapWages API. Helps to find playes more easily
        """

        self.slug_list = slug_list
        
        # The API endpoint is a predefined URL.
        self.API_endpoint = "https://capwages.com/api/gateway/v1"

        # Use the setter function to initialize API key and header for API call
        self.API_key = None
        self.API_header = None
        self.set_API_key(API_key)
        

    def set_API_key(self, API_key):
        """
        Method to set a value for the API key. Also update the header for API call

        Arguments:
            API_key = Your personal API key for CapWages API
        """

        self.API_key = API_key

        if API_key is not None:
            self.API_header = {"Authorization": f"ApiKey {API_key}"}
        else:
            self.API_header = None
            
    def set_dotenv_API_key(self, env_key):
        """
        Set the API key based on dotenv environment

        Arguments:
            env_key = Environmental variable holding the API key
        """
        
        load_dotenv()
        API_key = os.getenv(env_key)
        self.set_API_key(API_key)
            
  
    def get_player_details(self, slug):
        """
        Method for getting detailed information from spacific player based on player slug
        
        Arguments:
            slug = String that uniquely identifies the player you are interested in
            
        Return:
            Dictionary containing information about the player
        """
        
        response = requests.get(
            f"{self.API_endpoint}/players/{slug}",
            headers=self.API_header
        )
        
        # Throw an error if we fail to read from the API
        response.raise_for_status()
        return response.json()
        
    # Currently this returns team slugs with underscores, even though they should be dashes!
    def get_player_list(self, page=1, limit=25):
        """
        Method for getting detailed information from spacific player based on player slug
        Based on studying the output, players are returned on alphabetical order ot the slug
        
        Arguments:
            page = Index of the json file which is returned
            limit = Number of players in the returned json file
            
        Return:
            Dictionary a list of basic player information from defined amount of players
        """
        
        response = requests.get(
            f"{self.API_endpoint}/players",
            headers=self.API_header,
            params={"page": page, "limit": limit}
        )
        
        # Throw an error if we fail to read from the API
        response.raise_for_status()
        return response.json()
        
        
    def get_team_lineup(self, team_slug):
        """
        Method for getting current lineup for a team based on team_slug
        
        Arguments:
            team_slug = String that uniquely identifies the team you are interested in
            
        Return:
            Dictionary containing the current lineup for the desired team
        """
        response = requests.get(
            f"{self.API_endpoint}/lineups/{team_slug}",
            headers=self.API_header,
        )
        
        # Throw an error if we fail to read from the API
        response.raise_for_status()
        return response.json()
        

    def find_player_slugs(self, n_players_per_page, first_page, last_page, append_mode = False, output_file = None):
        """
        Find player slugs based on the given input parameters.
        The slugs are stored in the self.slug_list variable.
        
        Arguments:
            n_players_per_page = Number of players per page in CapWages API player list
            first_page = First page number in CapWages API player list
            last_page = Last page number (inclusive) in CapWages API player list
            append_mode = If true, append to exisitng slug_list. If false, empty any infomation from list before adding new players
            output_file = If given, write the player slugs to this file
        """
        
        # Initialize the slug list to empty list unless we are in append mode
        if not append_mode:
            self.slug_list = []
            
        # Check that number of players per page is reasonable
        if n_players_per_page > 100:
            n_players_per_page = 100
            print("CapWagesReader::Warning! You tried to read more than 100 players per page from CapWages API.")
            print("The maximum number is 100, so proceeding with 100 players per page.")
        
        # Get the first page information to determine the allowed range of pages
        player_list = self.get_player_list(1, n_players_per_page)
        time.sleep(1) # Do not overwhelm CapWages API
        
        # Find the number of pages needed to find all the players
        n_pages = player_list["meta"]["pagination"]["totalPages"]
        
        # Make sure that the given page range is reasonable
        if first_page > last_page:
            print("CapWagesReader::Warning! The first page is larger than last page")
            print("This results to an empty set. No slugs were obtained")
            return
        
        if first_page > n_pages:
            print("CapWagesReader::Warning! The first requested page is out of range.")
            print(f"The page range for {n_players_per_page} players per page is 1-{n_pages}")
            print("No player slugs were obtained")
            return
            
        if last_page > n_pages:
            print("CapWagesReader::Warning! The last requested page is out of range.")
            print(f"Adjusting this to be the maximum page number {n_pages}")
            
        
        # Once we have the sanity check for the input completed, find the desired slug range
        for i_page in range(first_page, last_page+1):
            player_list = self.get_player_list(i_page, n_players_per_page)
            time.sleep(1) # Do not overwhelm CapWages API
            
            for i_player in range (0, len(player_list["data"])):
                self.slug_list.append(player_list["data"][i_player]["slug"])
        
        # If output file is given, write the slug list into the file
        if output_file is not None:
            with open(output_file, "w", encoding='utf-8') as f:
                for slug in self.slug_list:
                    f.write(f"{slug}\n")


    def find_all_player_slugs(self, output_file = None):
        """
        Method for determining all available player slugs.
        The slugs are stored in the self.slug_list variable
        Optionally the slugs can also be written to a file for future use
        
        Arguments:
            output_file = If given, write the player slugs to this file
        """
        
        # 100 players in one page is the maximum allowed by the API
        n_players_per_page = 100
        player_list = self.get_player_list(1, n_players_per_page)
        time.sleep(1) # Do not overwhelm CapWages API
        
        # Find the number of pages needed to find all the players
        n_pages = player_list["meta"]["pagination"]["totalPages"]
        
        # Run the player slug finder for all pages
        self.find_player_slugs(n_players_per_page, 1, n_pages, False, output_file)
                    
                    
    def read_slugs_from_file(self, slug_file):
        """
        Method for reading slug information for a file
        
        Arguments:
            slug_file = File containing player slugs
        """
        
        # Initialize the slug list to empty list
        self.slug_list = []
        
        with open(slug_file, "r", encoding='utf-8') as f:
            self.slug_list = f.read().splitlines()
