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
        self.consumer_key = None
        self.consumer_secret = None
        self.access_token = None
        self.refresh_token = None
        self.game_key = None
        self.league_id = None
        self.team_id = None

        self.hasToken = False
        self.directory_path = directory_path
        self.token_path = os.path.join(directory_path, "tokens", "secrets.json")
        self.credentials_path = os.path.join(
            directory_path, "tokens", "credentials.json"
        )
        self._load_credentials()

    def _load_credentials(self):
        try:
            self.consumer_key = os.environ["CONSUMER_KEY"]
            self.consumer_secret = os.environ["CONSUMER_SECRET"]
            self.game_key = os.environ["GAME_KEY"]
            self.league_id = os.environ["LEAGUE_ID"]
            self.team_id = os.environ["TEAM_ID"]
            self.access_token = os.environ["ACCESS_TOKEN"]
            self.refresh_token = os.environ["REFRESH_TOKEN"]
            self.logger.info("Loaded credentials from environment variables")
            self.logger.info(f"Team ID: {self.team_id}")
            self.logger.info(f"League ID: {self.league_id}")
            self.logger.info(f"Game Key: {self.game_key}")
            self.logger.info(
                "Dumping credentials to file located at %s", self.token_path
            )
            self.logger.info("Directory path: %s", self.directory_path)

        except Exception as e:
            logging.error(
                f"Error loading credentials from environment variables: {e}"
            )
            with open(self.credentials_path, "r") as file:
                credentials = json.load(file)

            self.consumer_key = credentials["consumer_key"]
            self.consumer_secret = credentials["consumer_secret"]
            self.game_key = credentials["game_key"]
            self.league_id = credentials["league_id"]
            self.team_id = credentials["team_id"]

    def getCredentials(self):
        res = {
            "consumer_key": self.consumer_key,
            "consumer_secret": self.consumer_secret,
            "game_key": self.game_key,
            "league_id": self.league_id,
            "team_id": self.team_id,
        }
        if self.access_token:
            res["access_token"] = self.access_token
        if self.refresh_token:
            res["refresh_token"] = self.refresh_token
        return res
