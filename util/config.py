import os
import json
import logging
from util.constants import REQUEST_AUTH_URL, REQUEST_TOKEN_URL, TOKEN_PATH
import sys
import requests


NEXT_GAME_URL = "https://api-web.nhle.com/v1/club-schedule/%s/week/now"
DIRECTORY_PATH = os.path.dirname(os.path.realpath(__file__))


class Config:
    def __init__(self, directory_path):
        self.logger = logging.getLogger(
            __name__
        )  # G det the root logger set in main.py

        self.logger.info("Initializing Config")
        self.consumerKey = None
        self.consumerSecret = None
        self.accessToken = None
        self.refreshToken = None
        self.gameKey = None
        self.leagueId = None
        self.teamId = None

        self.hasToken = False
        self.directory_path = directory_path
        self.token_path = os.path.join(directory_path, "tokens/secrets.json")

        self._load_credentials()

    def _load_credentials(self):
        try:
            self.consumerKey = os.environ["CONSUMER_KEY"]
            self.consumerSecret = os.environ["CONSUMER_SECRET"]
            self.gameKey = os.environ["GAME_KEY"]
            self.leagueId = os.environ["LEAGUE_ID"]
            self.teamId = os.environ["TEAM_ID"]
            self.accessToken = os.environ["ACCESS_TOKEN"]
            self.refreshToken = os.environ["REFRESH_TOKEN"]
            self.logger.info("Loaded credentials from environment variables")
            self.logger.info(f"Team ID: {self.teamId}")
            self.logger.info(f"League ID: {self.leagueId}")
            self.logger.info(f"Game Key: {self.gameKey}")
            with open(self.token_path, "w") as file:
                json.dump(
                    {
                        "consumer_key": self.consumerKey,
                        "consumer_secret": self.consumerSecret,
                        "access_token": self.accessToken,
                        "refresh_token": self.refreshToken,
                    },
                    file,
                )
        except Exception as e:
            logging.error(
                f"Error loading credentials from environment variables: {e}"
            )
            with open(self.token_path, "r") as file:
                credentials = json.load(file)

            self.consumerKey = credentials["consumer_key"]
            self.consumerSecret = credentials["consumer_secret"]
            self.gameKey = credentials["game_key"]
            self.leagueId = credentials["league_id"]
            self.teamId = credentials["team_id"]

    def getCredentials(self):
        res = {
            "access_token": self.accessToken,
            "refresh_token": self.refreshToken,
            "consumer_key": self.consumerKey,
            "consumer_ecret": self.consumerSecret,
            "game_key": self.gameKey,
            "league_id": self.leagueId,
            "team_id": self.teamId,
        }
        return res
