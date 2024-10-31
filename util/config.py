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
        self.token_path = os.path.join(directory_path, "tokenData.conf")
        self._load_credentials()

    def _load_credentials(self):
        credentials_path = os.path.join(self.directory_path, "credentials.json")
        logging.info(f"Credentials path: {credentials_path}")
        if os.path.exists(credentials_path):
            with open(credentials_path, "r") as file:
                credentials = json.load(file)

            self.consumerKey = credentials["CONSUMER_KEY"]
            self.consumerSecret = credentials["CONSUMER_SECRET"]
            self.gameKey = credentials["GAME_KEY"]
            self.leagueId = credentials["LEAGUE_ID"]
            self.teamId = credentials["TEAM_ID"]
        else:
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
        if "YAHOO_TOKEN" in os.environ:
            try:
                oauth = json.loads(os.environ["YAHOO_TOKEN"])
                tokenFile = open(self.token_path, "w")
                json.dump(oauth, tokenFile)
                tokenFile.close()

            except Exception as e:
                raise e
            self.hasToken = True

            # Check to see if the token data file is present
        try:
            self.logger.info("Token Path: %s" % self.token_path)
            open(self.token_path, "r")
            self.hasToken = True
        except IOError as e:
            if "No such file or directory" in e.strerror:
                self.hasToken = False
            else:
                logging.error("IO ERROR: [%d] %s" % (e.errno, e.strerror))
                sys.exit(1)
        except Exception as e:
            logging.error("ERROR: [%d] %s" % (e.errno, e.strerror))
            sys.exit(1)

        if not self.hasToken:
            self.logger.info("No token found, getting full authorization")
            oauth = self.getFullAuthorization()

    def getFullAuthorization(self):
        """
        Gets full authorization for the application to access Yahoo APIs and get User Data.

        Writes all relevant data to tokenData.conf
        """

        # Step 1: Get authorization from User to access their data
        authUrl = "%s?client_id=%s&redirect_uri=oob&response_type=code" % (
            REQUEST_AUTH_URL,
            self.consumerKey,
        )
        logging.debug(authUrl)
        print(
            "You need to authorize this application to access your data.\nPlease go to %s"
            % (authUrl)
        )
        authorized = "n"

        while authorized.lower() != "y":
            authorized = input("Have you authorized me? (y/n)")
            if authorized.lower() != "y":
                print("You need to authorize me to continue...")

        authCode = input("What is the code? ")

        # Step 2: Get Access Token to send requests to Yahoo APIs
        response = self.getAccessToken(authCode)
        oauth = self.parseToken(response)
        return oauth

    def readOAuthToken(self):
        """
        Reads the token data from file and returns a dictionary object
        """

        logging.debug("Reading token details from file...")

        try:
            tokenFile = open(self.token_path, "r")
            oauth = json.load(tokenFile)
            tokenFile.close()
        except Exception as e:
            raise e

        logging.debug("Reading complete!")
        return oauth

    def getAccessToken(self, verifier):
        """
        Gets the access token used to allow access to user data within Yahoo APIs

        Returns access token payload
        """

        logging.info("Getting access token...")

        response = requests.post(
            REQUEST_TOKEN_URL,
            data={
                "client_id": self.consumerKey,
                "client_secret": self.consumerSecret,
                "redirect_uri": "oob",
                "code": verifier,
                "grant_type": "authorization_code",
            },
        )

        if response.status_code == 200:
            logging.info("Success!")
            logging.debug(response.content)
            return response.content
        else:
            logging.error("Access Token Request returned a non 200 code")
            logging.error("---------DEBUG--------")
            logging.error("HTTP Code: %s" % response.status_code)
            logging.error("HTTP Response: \n%s" % response.content)
            logging.error("-------END DEBUG------")
            sys.exit(1)

    def refreshAccessToken(self, refreshToken):
        """
        Refreshes the access token as it expires every hour

        Returns access token payload
        """

        logging.info("Refreshing access token...")

        response = requests.post(
            REQUEST_TOKEN_URL,
            data={
                "client_id": self.consumerKey,
                "client_secret": self.consumerSecret,
                "redirect_uri": "oob",
                "refresh_token": refreshToken,
                "grant_type": "refresh_token",
            },
        )

        if response.status_code == 200:
            logging.info("Success!")
            logging.debug(response.content)
            oauth = self.parseToken(response.content)
            return oauth
        else:
            logging.error("Access Token Request returned a non 200 code")
            logging.error("---------DEBUG--------")
            logging.error("HTTP Code: %s" % response.status_code)
            logging.error("HTTP Response: \n%s" % response.content)
            logging.error("-------END DEBUG------")
            sys.exit(1)

    def parseToken(self, response):
        """
        Receives the token payload and breaks it up into a dictionary and saves it to tokenData.conf

        Returns a dictionary to be used for API calls
        """

        parsedResponse = json.loads(response)
        accessToken = parsedResponse["access_token"]
        refreshToken = parsedResponse["refresh_token"]

        oauth = {}

        oauth["token"] = accessToken
        oauth["refreshToken"] = refreshToken

        try:
            tokenFile = open(self.token_path, "w")
            json.dump(oauth, tokenFile)
            tokenFile.close()

            return oauth

        except Exception as e:
            raise e

    def getCredentials(self):
        res = {
            "consumerKey": self.consumerKey,
            "consumerSecret": self.consumerSecret,
            "gameKey": self.gameKey,
            "leagueId": self.leagueId,
            "teamId": self.teamId,
            "hasToken": self.hasToken,
        }
        return res
