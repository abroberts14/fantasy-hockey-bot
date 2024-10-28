from collections import OrderedDict
import datetime
import logging
import xmltodict
import requests

BASE_YAHOO_API_URL = "https://fantasysports.yahooapis.com/fantasy/v2/"  # Example URL


class RosterPayloadManager:
    def __init__(self, credentials, config):
        self.credentials = credentials
        self.config = config

    def _construct_payload(self, players):
        """
        Constructs XML payload for roster operations.
        """
        dictPayload = {
            "fantasy_content": {
                "roster": {
                    "coverage_type": "date",
                    "date": str(datetime.date.today()),
                    "players": {"player": players},
                }
            }
        }
        return xmltodict.unparse(dictPayload, pretty=True)

    def _send_request(self, payload, log_message):
        """
        Sends the XML payload to Yahoo API and handles the response.
        """
        roster_url = (
            BASE_YAHOO_API_URL
            + "team/"
            + self.credentials["gameKey"]
            + ".l."
            + self.credentials["leagueId"]
            + ".t."
            + self.credentials["teamId"]
            + "/roster"
        )
        oauth = self.config.readOAuthToken()
        headers = {
            "Authorization": "Bearer " + oauth["token"],
            "Content-Type": "application/xml",
        }
        logging.info(f"Sending payload: {payload}")
        response = requests.put(roster_url, headers=headers, data=payload)

        if response.status_code == 200:
            logging.info(log_message)
            return True
        elif response.status_code == 401 and "token_expired" in response.content:
            logging.info("Token expired. Renewing...")
            oauth = self.config.refreshAccessToken(oauth["refreshToken"])
            return self._send_request(payload, log_message)
        else:
            logging.error("Failed to send request.")
            logging.info(f"Response Code: {response.status_code}")
            logging.info(f"Response Content: {response.content}")
            return False

    def fill_missing_positions(self, missing_positions_candidates):
        """
        Fills missing roster positions by selecting the highest-point bench players for each missing position.
        """
        if not missing_positions_candidates:
            logging.info("No missing positions to fill")
            return []

        added_players = []
        players_payload = []
        for position, candidates in missing_positions_candidates.items():
            if not candidates:
                continue  # Skip if no candidates for this position

            for candidate in candidates:
                logging.info(f"Candidate: {candidate}")
                logging.info(f"Assigning {candidate['name']} to position {position}")
                player_entry = OrderedDict(
                    [("player_key", candidate["key"]), ("position", position)]
                )
                players_payload.append(player_entry)
                added_players.append(candidate)

        if not added_players:
            return []

        payload = self._construct_payload(players_payload)
        success = self._send_request(
            payload, "Successfully updated roster with missing positions."
        )

        if success:
            logging.info(
                f"Added players: {', '.join([player['name'] for player in added_players])}"
            )
            return added_players
        return []

    def fill_roster(self, roster):
        """
        Fills missing roster positions by selecting the highest-point bench players for each missing position.
        """
        if not roster:
            logging.info("No missing positions to fill")
            return []

        added_players = []
        players_payload = []
        logging.info(f"Roster: {roster}")
        for position, candidates in roster.items():
            if not candidates:
                continue  # Skip if no candidates for this position

            for candidate in candidates:
                logging.info(f"Candidate: {candidate}")
                logging.info(f"Assigning {candidate['name']} to position {position}")
                player_entry = OrderedDict(
                    [("player_key", candidate["key"]), ("position", position)]
                )
                players_payload.append(player_entry)
                added_players.append(candidate)

        if not added_players:
            return []

        payload = self._construct_payload(players_payload)
        success = self._send_request(
            payload, "Successfully updated roster with missing positions."
        )

        if success:
            logging.info(
                f"Added players: {', '.join([player['name'] for player in added_players])}"
            )
            return added_players
        return []

    def swap_players(self, current_player, bench_player):
        """
        Swaps two players on the roster.
        """
        logging.info(f"Starting {bench_player['name']} over {current_player['name']}")

        players_payload = [
            OrderedDict(
                [
                    ("player_key", bench_player["key"]),
                    ("position", current_player["current_position"]),
                ]
            ),
            OrderedDict(
                [
                    ("player_key", current_player["key"]),
                    ("position", bench_player["current_position"]),
                ]
            ),
        ]

        payload = self._construct_payload(players_payload)
        success = self._send_request(
            payload,
            f"Successfully swapped {bench_player['name']} with {current_player['name']}",
        )

        return success
