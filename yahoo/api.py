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
from yahoo.payload_manager import RosterPayloadManager


class YahooApi:
    def __init__(self, directory_path):
        self.logger = logging.getLogger(__name__)  # Get the root logger set in main.py
        self.config = Config(directory_path)
        self.logger.info("Initializing YahooApi")
        self.logger.info("Getting credentials")
        self.credentials = self.config.getCredentials()
        self.roster_payload_manager = RosterPayloadManager(
            self.credentials, self.config
        )
        self.logger.info("Checking token")

    def queryYahooApi(self, url, dataType):
        """
        Queries the yahoo fantasy sports api
        """

        oauth = self.config.readOAuthToken()
        header = "Bearer " + oauth["token"]
        self.logger.info("URL: %s" % url)
        response = requests.get(url, headers={"Authorization": header})

        if response.status_code == 200:
            self.logger.debug("Successfully got %s data" % dataType)
            self.logger.debug(response.content)
            payload = xmltodict.parse(response.content)
            self.logger.debug("Successfully parsed %s data" % dataType)
            return payload
        elif response.status_code == 401:
            self.logger.info("Token Expired....renewing")
            oauth = self.config.refreshAccessToken(oauth["refreshToken"])
            return self.queryYahooApi(url, dataType)
        else:
            self.logger.error("Could not get %s information" % dataType)
            self.logger.error("---------DEBUG--------")
            self.logger.error("HTTP Code: %s" % response.status_code)
            self.logger.error("HTTP Response: \n%s" % response.content)
            self.logger.error("-------END DEBUG------")
            sys.exit(1)

    def getLeagueSettings(self):
        """
        Get the league settings from Yahoo and parses the response
        """

        rosterUrl = (
            BASE_YAHOO_API_URL
            + "league/"
            + self.credentials["gameKey"]
            + ".l."
            + self.credentials["leagueId"]
            + "/settings"
        )
        return self.queryYahooApi(rosterUrl, "league")

    def getRoster(self):
        """
        Get the roster from Yahoo and parses the response
        """

        rosterUrl = (
            BASE_YAHOO_API_URL
            + "team/"
            + str(self.credentials["gameKey"])
            + ".l."
            + str(self.credentials["leagueId"])
            + ".t."
            + str(self.credentials["teamId"])
            + "/roster/players"
        )
        return self.queryYahooApi(rosterUrl, "roster")

    def getPlayerData(self, playerKey):
        """
        Get player data from Yahoo and parses the response
        """

        rosterUrl = (
            BASE_YAHOO_API_URL
            + "league/"
            + str(self.credentials["gameKey"])
            + ".l."
            + str(self.credentials["leagueId"])
            + "/players;player_keys="
            + playerKey
            + "/stats;type=biweekly"
        )
        playerData = self.queryYahooApi(rosterUrl, "player")
        player = {}
        player["name"] = playerData["fantasy_content"]["league"]["players"]["player"][
            "name"
        ]["full"]
        player["team"] = playerData["fantasy_content"]["league"]["players"]["player"][
            "editorial_team_full_name"
        ]
        player["available_positions"] = playerData["fantasy_content"]["league"][
            "players"
        ]["player"]["eligible_positions"]["position"]
        if (
            "player_notes_last_timestamp"
            in playerData["fantasy_content"]["league"]["players"]["player"]
        ):
            player["new_notes_timestamp"] = int(
                playerData["fantasy_content"]["league"]["players"]["player"][
                    "player_notes_last_timestamp"
                ]
            )
        else:
            player["new_notes_timestamp"] = "-1"
        player["isGoalie"] = (
            player["available_positions"] == "G" or "G" in player["available_positions"]
        )

        points = 0

        for stat in playerData["fantasy_content"]["league"]["players"]["player"][
            "player_stats"
        ]["stats"]["stat"]:
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

    def getLeagueRequiredRoster(self):
        """
        Extracts the required roster positions from the league settings.
        Returns a list of positions based on the league's roster configuration.
        """
        # Extract roster positions from the league settings
        roster_positions = self.getLeagueSettings()["fantasy_content"]["league"][
            "settings"
        ]["roster_positions"]["roster_position"]

        # Create a list to hold the full lineup based on the league settings
        full_lineup = []

        # Iterate over each position and add it to the full lineup list based on its count
        for position in roster_positions:
            position_name = position["position"]
            count = int(position["count"])
            full_lineup.extend([position_name] * count)

        return full_lineup
