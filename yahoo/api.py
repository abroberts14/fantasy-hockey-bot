from collections import OrderedDict
import datetime
import logging
import requests
import xmltodict
import sys
from util.config import NEXT_GAME_URL, Config
from util.constants import BASE_YAHOO_API_URL, NHL_TEAM_ID, TOKEN_PATH
import json
import os
from yahoo_oauth import OAuth2
import yahoo_fantasy_api as yfa


class YahooApi:
    def __init__(self, directory_path):
        self.logger = logging.getLogger(__name__)  # Get the root logger set in main.py
        self.config = Config(directory_path)
        self.directory_path = directory_path
        self.logger.info("Initializing YahooApi")
        self.logger.info("Getting credentials")
        self.credentials = self.config.getCredentials()

        self.logger.info("Checking token")
        self.oauth_file = os.path.join(directory_path, "tokens", "secrets.json")
        if not os.path.exists(self.oauth_file):
            logging.info("Token file does not exist, generating new token")
            self.oauth_json_gen()
        self.oauth_setup()
        # Initialize game, league and team objects
        self.logger.info("Initializing Yahoo Fantasy objects")
        self.league_key = f"{self.credentials['game_key']}.l.{self.credentials['league_id']}"
        self.team_key = f"{self.league_key}.t.{self.credentials['team_id']}"
        try:
            # Create game object for NHL
            self.sc.refresh_access_token()
            self.credentials["access_token"] = self.sc.access_token
            self.credentials["refresh_token"] = self.sc.refresh_token
            self.logger.info(f"isToken Valid: {self.sc.token_is_valid()}")
            self.game = yfa.Game(self.sc, "nhl")

            # Create league object using credentials
            self.league = self.game.to_league(self.league_key)
            self.league_positions = self.league.positions()
            self.league_settings = self.league.settings()
            self.max_moves = self.league_settings["max_weekly_adds"]
            self.team = self.league.to_team(self.team_key)

            self.team_data = self.league.teams()[self.team_key]
            self.logger.info("Successfully initialized Yahoo Fantasy objects")
        except Exception as e:
            self.logger.error(f"Failed to initialize Yahoo Fantasy objects: {str(e)}")
            raise

    def oauth_json_gen(self):
        try:
            credentials = self.config.getCredentials()
            credentials["token_type"] = "bearer"
            credentials["token_time"] = 1699999999
            credentials["guid"] = None
            with open(self.oauth_file, "w") as f:
                f.write(json.dumps(credentials))
        except Exception as e:
            logging.info(f"No access token or refresh token found, need to authorize using 3legged OAuth: {e}")
            pass

    def oauth_setup(self):
        self.logger.info("Setting up OAuth")
        self.logger.info(f"oauth_file: {self.oauth_file}")

        self.sc = OAuth2(
            None,
            None,
            from_file=self.oauth_file,
        )
        if not self.sc.token_is_valid():
            self.sc.refresh_access_token()

        self.credentials["access_token"] = self.sc.access_token
        self.credentials["refresh_token"] = self.sc.refresh_token

    def queryYahooApi(self, url, dataType):
        """
        Queries the yahoo fantasy sports api
        """

        header = "Bearer " + self.credentials["access_token"]
        self.logger.debug("URL: %s" % url)
        response = requests.get(url, headers={"Authorization": header})

        if response.status_code == 200:
            self.logger.debug("Successfully got %s data" % dataType)
            self.logger.debug(response.content)
            payload = xmltodict.parse(response.content)
            self.logger.debug("Successfully parsed %s data" % dataType)
            return payload
        elif response.status_code == 401:
            self.logger.info("Token Expired....renewing")
            self.sc.refresh_access_token()
            self.credentials["access_token"] = self.sc.access_token
            self.credentials["refresh_token"] = self.sc.refresh_token
            return self.queryYahooApi(url, dataType)
        else:
            self.logger.error("Could not get %s information" % dataType)
            self.logger.error("---------DEBUG--------")
            self.logger.error("HTTP Code: %s" % response.status_code)
            self.logger.error("HTTP Response: \n%s" % response.content)
            self.logger.error("-------END DEBUG------")
            sys.exit(1)

    def get_roster(self):
        """
        Get the roster from Yahoo using the yahoo-fantasy-api library
        """
        # G the roster
        roster = self.team.roster()

        return roster

    def get_league(self):
        return self.league

    def getPlayerData(self, playerKey):
        """
        Get player data from Yahoo and parses the response
        """

        rosterUrl = (
            BASE_YAHOO_API_URL
            + "league/"
            + str(self.credentials["game_key"])
            + ".l."
            + str(self.credentials["league_id"])
            + "/players;player_keys="
            + str(playerKey)
            + "/stats;type=biweekly"
        )
        playerData = self.queryYahooApi(rosterUrl, "player")
        player = {}
        player["name"] = playerData["fantasy_content"]["league"]["players"]["player"]["name"]["full"]
        player["team"] = playerData["fantasy_content"]["league"]["players"]["player"]["editorial_team_full_name"]
        player["available_positions"] = playerData["fantasy_content"]["league"]["players"]["player"]["eligible_positions"]["position"]
        if "player_notes_last_timestamp" in playerData["fantasy_content"]["league"]["players"]["player"]:
            player["new_notes_timestamp"] = int(playerData["fantasy_content"]["league"]["players"]["player"]["player_notes_last_timestamp"])
        else:
            player["new_notes_timestamp"] = "-1"
        player["isGoalie"] = player["available_positions"] == "G" or "G" in player["available_positions"]
        if player["isGoalie"]:
            logging.debug(f"Player: {playerData["fantasy_content"]["league"]["players"]["player"]}")
        points = 0
        player["status"] = playerData["fantasy_content"]["league"]["players"]["player"].get("status", "")
        for stat in playerData["fantasy_content"]["league"]["players"]["player"]["player_stats"]["stats"]["stat"]:
            if stat["value"] == "-":
                points += 0
            elif stat["stat_id"] == "22":  # Goals Against counts against overall score
                points -= int(stat["value"])
            elif stat["stat_id"] == "23":  # GAA counts against overall score
                points -= float(stat["value"])

            else:
                # check if its a float or int
                try:
                    points += float(stat["value"])
                except:
                    points += int(stat["value"])

        player["points"] = points

        url = NEXT_GAME_URL % NHL_TEAM_ID[player["team"]]
        # logging.info("Next game url: %s" % url)
        response = requests.get(url)
        nextGame = json.loads(response.content)
        # logging.info("Next game: %s" % nextGame)
        player["next_game"] = nextGame["games"][0]["gameDate"]

        return player
