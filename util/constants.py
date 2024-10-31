import os

# Global Variables
REQUEST_TOKEN_URL = "https://api.login.yahoo.com/oauth/v2/get_request_token"
REQUEST_AUTH_URL = "https://api.login.yahoo.com/oauth2/request_auth"
REQUEST_TOKEN_URL = "https://api.login.yahoo.com/oauth2/get_token"
BASE_YAHOO_API_URL = "https://fantasysports.yahooapis.com/fantasy/v2/"
NEXT_GAME_URL = "https://api-web.nhle.com/v1/club-schedule/%s/week/now"
DIRECTORY_PATH = os.path.dirname(os.path.realpath(__file__))
TOKEN_PATH = DIRECTORY_PATH + "/tokens/secrets.json"

NHL_TEAM_ID = {
    "New Jersey Devils": "NJD",
    "New York Islanders": "NYI",
    "New York Rangers": "NYR",
    "Philadelphia Flyers": "PHI",
    "Pittsburgh Penguins": "PIT",
    "Boston Bruins": "BOS",
    "Buffalo Sabres": "BUF",
    "Montreal Canadiens": "MTL",
    "Ottawa Senators": "OTT",
    "Toronto Maple Leafs": "TOR",
    "Carolina Hurricanes": "CAR",
    "Florida Panthers": "FLA",
    "Tampa Bay Lightning": "TBL",
    "Washington Capitals": "WSH",
    "Chicago Blackhawks": "CHI",
    "Detroit Red Wings": "DET",
    "Nashville Predators": "NSH",
    "St. Louis Blues": "STL",
    "Calgary Flames": "CGY",
    "Colorado Avalanche": "COL",
    "Edmonton Oilers": "EDM",
    "Vancouver Canucks": "VAN",
    "Anaheim Ducks": "ANA",
    "Dallas Stars": "DAL",
    "Los Angeles Kings": "LAK",
    "San Jose Sharks": "SJS",
    "Columbus Blue Jackets": "CBJ",
    "Minnesota Wild": "MIN",
    "Winnipeg Jets": "WPG",
    "Arizona Coyotes": "ARI",
    "Vegas Golden Knights": "VGK",
    "Seattle Kraken": "SEA",
    "Utah Hockey Club": "UTA",
}
