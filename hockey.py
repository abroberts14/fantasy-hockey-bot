#!/usr/bin/env python


import datetime
import logging
from itertools import product
import os
from util.config import Config
from collections import (
    Counter,
    OrderedDict,
)

import yahoo.api as api


logging.basicConfig(
    level=logging.INFO,
    # format="%(asctime)s - %(levelname)s: %(message)s",
    format="%(levelname)s: %(message)s",
    datefmt="%m/%d/%Y %I:%M:%S %p",
)
logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("yahoo_api").setLevel(logging.INFO)
logging.getLogger("config").setLevel(logging.INFO)


class RosterManager:
    def __init__(self, yApi):
        self.yApi = yApi
        self.today = str(datetime.date.today())

    def get_team(self):
        roster = self.yApi.getRoster()
        logging.info("Getting player data...")
        team = [
            self._build_player_data(player)
            for player in roster["fantasy_content"]["team"]["roster"]["players"][
                "player"
            ]
        ]
        return team

    def _build_player_data(self, player):
        player_data = self.yApi.getPlayerData(player["player_key"])
        player_data["current_position"] = player["selected_position"]["position"]
        player_data["key"] = player["player_key"]
        return player_data

    def calculate_best_lineup(self, optimized_replacements):
        best_lineup = {}
        max_points = 0
        position_options = {
            position: candidates
            for position, candidates in optimized_replacements.items()
        }

        if any(not candidates for candidates in position_options.values()):
            logging.info("One or more positions have no candidates available.")
            return best_lineup

        for combination in product(*position_options.values()):
            lineup, total_points = self._evaluate_combination(
                position_options.keys(), combination
            )
            if total_points > max_points:
                best_lineup = lineup
                max_points = total_points
        return best_lineup

    def _evaluate_combination(self, positions, combination):
        lineup = {}
        total_points = 0
        used_players = set()
        for position, player in zip(positions, combination):
            if player["key"] not in used_players:
                lineup[position] = player
                total_points += player["points"]
                used_players.add(player["key"])
        return lineup, total_points

    def set_best_lineup(self, roster):
        # roster is the response from get_players_by_position, already sorted by descending points

        # Step 1: Calculate the best lineup based on provided roster
        calculated_lineup = self.calculate_best_lineup(roster)
        completed_swaps = []
        logging.info(f"Initial calculated lineup: {calculated_lineup}")

        # Step 2: Get league required roster and convert to a count of each position
        required_roster_list = self.yApi.getLeagueRequiredRoster()
        required_roster = Counter(
            required_roster_list
        )  # Count occurrences of each position

        # Track how many players we've filled for each position and ensure all entries are lists
        filled_positions_count = {position: 0 for position in required_roster}
        used_player_keys = set()
        for position, player in calculated_lineup.items():
            if not isinstance(player, list):
                calculated_lineup[position] = [player]
            filled_positions_count[position] += len(calculated_lineup[position])
            used_player_keys.update(p["key"] for p in calculated_lineup[position])

        # Populate each position to meet the required count
        for position, required_count in required_roster.items():
            available_players = roster.get(position, [])
            filled_count = filled_positions_count[position]

            # Add players until we reach the required count
            while filled_count < required_count and available_players:
                next_player = available_players.pop(0)
                if next_player["key"] not in used_player_keys:
                    calculated_lineup[position].append(next_player)
                    used_player_keys.add(next_player["key"])
                    filled_count += 1

        # Step 3: Add remaining players to the bench (BN)
        bench_players = []
        for position_players in roster.values():
            for player in position_players:
                if player["key"] not in used_player_keys:
                    # Set the player's position to "BN" and add to the bench list
                    player["current_position"] = "BN"
                    bench_players.append(player)

        # Add bench players to the calculated lineup under a "BN" key
        calculated_lineup["BN"] = bench_players

        # Log final calculated lineup with all required positions filled, including bench
        logging.info(f"Final calculated lineup including bench: {calculated_lineup}")

        # Step 4: Send the fully populated lineup payload to Yahoo
        self.yApi.roster_payload_manager.fill_missing_positions(calculated_lineup)

        return completed_swaps

    def get_players_by_position(self, roster):

        players_by_position = {}

        # Iterate through each player in the roster
        for player in roster:
            for position in player["available_positions"]:
                # Add player to the list for each eligible position
                if position not in players_by_position:
                    players_by_position[position] = []
                players_by_position[position].append(player)

        # Sort each list of players by points in descending order and game today status
        for position, players in players_by_position.items():
            players_by_position[position] = sorted(
                players, key=lambda x: (-x["points"], x["next_game"] != self.today)
            )
        return players_by_position

    def output_sorted_roster(self, roster, completed_swaps=None, only_swaps=False):
        sorted_roster = self.sort_roster(roster)
        if not only_swaps:
            self.log_roster(sorted_roster, "Active players:", exclude_position="BN")
            self.log_roster(sorted_roster, "Bench players:", include_position="BN")
        if completed_swaps:
            self.log_completed_swaps(completed_swaps)

    @staticmethod
    def sort_roster(roster):
        position_order = {"C": 0, "LW": 1, "RW": 2, "D": 3, "Util": 4, "G": 5}
        return sorted(
            roster, key=lambda x: position_order.get(x["current_position"], 6)
        )

    @staticmethod
    def log_roster(roster, title, exclude_position=None, include_position=None):
        logging.info(title)
        for line in roster:
            if (exclude_position and line["current_position"] != exclude_position) or (
                include_position and line["current_position"] == include_position
            ):
                logging.info(
                    f"{line['current_position']}: {line['name']} (Avail Pos: {', '.join(line['available_positions'])})"
                    f" - {line['points']} - Game Today: {line['next_game'] == datetime.date.today()}"
                )

    @staticmethod
    def log_completed_swaps(completed_swaps):
        logging.info("Completed swaps:")
        for swap in completed_swaps:
            logging.info(
                f"{swap['new_starter']['name']} ({swap['new_starter']['current_position']}) replaced {swap['benched_starter']['name']}"
            )


if __name__ == "__main__":
    yApi = api.YahooApi(os.path.dirname(os.path.realpath(__file__)))
    manager = RosterManager(yApi)
    team = manager.get_team()
    manager.output_sorted_roster(team)
    players_by_position = manager.get_players_by_position(team)
    # logging.info(f"Players by position: {players_by_position}")
    swaps = manager.set_best_lineup(players_by_position)
    # swaps = manager.set_optimized_lineup(team)
    manager.output_sorted_roster(team, swaps)
    # mainNew()

    logging.info("Done!")
