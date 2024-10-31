#!/usr/bin/env python
import time
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


class TeamManager:
    def __init__(self, yApi, dry_run=False):
        self.yApi = yApi
        self.today = str(datetime.date.today())
        self.dry_run = dry_run
        self.previous_lineup = None
        self.lineup = None  # dict of roster, grouped by position
        self.lineup_changes = []
        self.roster = []  # list of all players, not grouped by position
        self.moves_left = 0
        self.active_players = []
        self.inactive_positions = ["IR+", "IL", "NA", "IR"]

    def get_team(self):
        roster = self.yApi.get_roster()
        lineups = {}
        team = []
        self.active_players = []
        for player in roster:
            position = player["selected_position"]
            player_data = self._build_player_data(player)
            player_data["percent_owned"] = self.yApi.league.percent_owned(
                [player["player_id"]]
            )[0]["percent_owned"]
            player_data["locked"] = int(player_data["percent_owned"]) >= 70

            team.append(player_data)
            if position not in lineups:
                lineups[position] = []
            lineups[position].append(player_data)
            # Add to active_players if not on IL/IR
            if position not in self.inactive_positions:
                self.active_players.append(player_data)
        if self.previous_lineup is None:
            self.previous_lineup = lineups
        self.lineup = lineups
        self.roster = team

        self.moves_left = int(self.yApi.max_moves) - int(
            self.yApi.team_data["roster_adds"]["value"]
        )
        logging.info(f"Moves left: {self.moves_left}")
        logging.info(f"Roster full: {self.is_roster_full()}")
        return team

    def is_roster_full(self):
        """Check if the roster meets or exceeds the league position requirements."""
        required_total = sum(
            int(pos_info["count"])
            for pos, pos_info in self.yApi.league_positions.items()
            if pos
            not in self.inactive_positions  # Exclude IR slots from the count
        )

        # Count active roster spots (excluding IR/IL)
        active_roster_count = len(self.active_players)

        logging.info(f"Required roster spots: {required_total}")
        logging.info(f"Current active players: {active_roster_count}")

        return active_roster_count >= required_total

    def _build_player_data(self, player):
        player_data = self.yApi.getPlayerData(
            self.yApi.credentials["game_key"] + ".p." + str(player["player_id"])
        )

        player_data["current_position"] = player["selected_position"]
        player_data["key"] = (
            self.yApi.credentials["game_key"] + ".p." + str(player["player_id"])
        )
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
                if player["next_game"] == self.today:
                    total_points += player["points"]
                used_players.add(player["key"])
        return lineup, total_points

    def set_best_lineup(self, roster):
        # roster is the response from get_players_by_position, already sorted by descending points
        self.previous_lineup = self.lineup
        # Step 1: Calculate the best lineup based on provided roster
        calculated_lineup = self.calculate_best_lineup(roster)
        completed_swaps = []
        logging.debug(f"Initial calculated lineup: {calculated_lineup}")

        # Step 2: Get league required roster and convert to a count of each position
        required_roster_list = self.yApi.league_positions

        # Track how many players we've filled for each position and ensure all entries are lists
        filled_positions_count = {
            position: 0 for position in required_roster_list.keys()
        }
        used_player_keys = set()
        for position, player in calculated_lineup.items():
            if not isinstance(player, list):
                calculated_lineup[position] = [player]
            filled_positions_count[position] += len(calculated_lineup[position])
            used_player_keys.update(
                p["key"] for p in calculated_lineup[position]
            )
        # Populate each position to meet the required count
        for position, required_count in required_roster_list.items():
            available_players = roster.get(position, [])
            filled_count = filled_positions_count[position]

            # Add players until we reach the required count
            while filled_count < required_count["count"] and available_players:
                next_player = available_players.pop(0)
                if next_player["key"] not in used_player_keys:
                    calculated_lineup[position].append(next_player)
                    used_player_keys.add(next_player["key"])
                    filled_count += 1

        logging.debug(f"Used player keys: {used_player_keys}")
        # Step 3: Add remaining players to the bench (BN)
        bench_players = []
        for position_players in self.lineup.values():
            for player in position_players:
                if player["key"] not in used_player_keys:
                    # Set the player's position to "BN" and add to the bench list
                    player["current_position"] = "BN"
                    logging.debug(f"Adding {player['name']} to the bench")
                    bench_players.append(player)
                else:
                    logging.debug(
                        f"Player {player['name']} already used at {player['current_position']}, skipping"
                    )
        # Add bench players to the calculated lineup under a "BN" key
        calculated_lineup["BN"] = bench_players

        # Log final calculated lineup with all required positions filled, including bench
        logging.debug(
            f"Final calculated lineup including bench: {calculated_lineup}"
        )
        self.lineup = calculated_lineup
        original_lineup_payload = self.get_roster_update_payload_on_lineup(
            self.previous_lineup
        )
        new_lineup_payload = self.get_roster_update_payload_on_lineup(
            calculated_lineup
        )
        # Sort both lists in place
        original_lineup_payload.sort(
            key=lambda x: (x["player_id"], x["selected_position"])
        )
        new_lineup_payload.sort(
            key=lambda x: (x["player_id"], x["selected_position"])
        )
        logging.info(f"Original lineup payload: {original_lineup_payload}")
        logging.info(f"New lineup payload: {new_lineup_payload}")
        if not self.dry_run:
            # self.yApi.roster_payload_manager.fill_roster(calculated_lineup)
            logging.info(f"Payload: {new_lineup_payload}")
            if (
                len(new_lineup_payload) > 0
                and new_lineup_payload != original_lineup_payload
            ):
                self.yApi.team.change_positions(
                    datetime.datetime.now(), new_lineup_payload
                )
                self.roster = self.get_team()
            else:
                logging.info("No changes to lineup")
        return completed_swaps

    def get_roster_update_payload_on_lineup(self, lineup):
        payload = []
        for position, players in lineup.items():
            for player in players:
                payload.append(
                    {
                        "player_id": player["key"].split(".")[2],
                        "selected_position": position,
                    }
                )
        return payload

    def get_players_by_position(self, roster):
        players_by_position = {}

        # Iterate through each player in the roster
        for player in roster:
            for position in player["available_positions"]:
                # Add player to the list for each eligible position
                if position not in players_by_position:
                    players_by_position[position] = []
                players_by_position[position].append(player)
        logging.debug(f"Players by position: {players_by_position["LW"]}")
        # Sort each list of players by points in descending order and game today status
        for position, players in players_by_position.items():
            if position == "G":
                # For goalies, sort by game today first, then points, then timestamp

                players_by_position[position] = sorted(
                    players,
                    key=lambda x: (
                        x["next_game"] != self.today,  # Game status now first
                        -x["points"],
                        (
                            int(time.time())
                            - int(x.get("new_notes_timestamp", 0))
                        )
                        / 3600,
                    ),
                )
            else:
                players_by_position[position] = sorted(
                    players,
                    key=lambda x: (
                        x["next_game"] != self.today,  # Game status now first
                        -x["points"],
                    ),
                )
        logging.debug(f"Players by position: {players_by_position["LW"]}")

        return players_by_position

    def get_lineup_changes(self):
        if self.previous_lineup is None or self.lineup is None:
            print("One of the lineups is not set.")
            return
        self.lineup_changes = []
        # Create comprehensive maps of previous and current lineups by player names
        previous_map = {
            player["name"]: {"position": pos, "player": player}
            for pos, players in self.previous_lineup.items()
            for player in players
        }
        current_map = {
            player["name"]: {"position": pos, "player": player}
            for pos, players in self.lineup.items()
            for player in players
        }

        # Track moves and status changes
        moved = {}
        started = {}
        benched = {}

        # Identify changes
        for name, curr_info in current_map.items():
            prev_info = previous_map.get(name)
            if prev_info:
                if prev_info["position"] != curr_info["position"]:
                    moved[name] = (prev_info["position"], curr_info["position"])
            else:
                started[name] = curr_info["position"]

        for name, prev_info in previous_map.items():
            if name not in current_map:
                benched[name] = prev_info["position"]

        # Generate user-friendly change descriptions
        self.process_changes(moved, benched)
        return self.lineup_changes

    def process_changes(self, moved, benched):
        # Track started and benched players by position
        position_changes = {}  # {position: {'started': [], 'benched': []}}

        # First pass: Organize all changes by position
        for name, (old_pos, new_pos) in moved.items():
            if old_pos == "BN":
                # Player was started
                if new_pos not in position_changes:
                    position_changes[new_pos] = {
                        "started": [],
                        "benched": [],
                        "moved": [],
                    }
                position_changes[new_pos]["started"].append(name)
            elif new_pos == "BN":
                # Player was benched
                if old_pos not in position_changes:
                    position_changes[old_pos] = {
                        "started": [],
                        "benched": [],
                        "moved": [],
                    }
                position_changes[old_pos]["benched"].append(name)
            else:
                if old_pos not in position_changes:
                    position_changes[old_pos] = {
                        "started": [],
                        "benched": [],
                        "moved": [],
                    }
                position_changes[old_pos]["moved"].append(name)

        # Add benched players not in moves
        for name, old_pos in benched.items():
            if old_pos != "BN" and name not in moved:
                if old_pos not in position_changes:
                    position_changes[old_pos] = {
                        "started": [],
                        "benched": [],
                        "moved": [],
                    }
                position_changes[old_pos]["benched"].append(name)

        # Generate change messages
        for position, changes in position_changes.items():
            started = changes["started"]
            benched = changes["benched"]
            moved_players = changes["moved"]
            # If we have both started and benched players for a position
            if moved_players:
                for m in moved_players:
                    _, new_pos = moved[m]
                    self.lineup_changes.append(
                        f"Moved {m} from {position} to {new_pos}"
                    )
            if started and benched:
                for s, b in zip(started, benched):
                    self.lineup_changes.append(
                        f"Started {s} at {position}, benching {b}"
                    )
                # Handle any remaining players if lists are uneven
                for s in started[len(benched) :]:
                    self.lineup_changes.append(f"Started {s} at {position}")
                for b in benched[len(started) :]:
                    self.lineup_changes.append(f"Benched {b} from {position}")

            else:
                # Handle cases where we only have starts or only have benchings
                for s in started:
                    self.lineup_changes.append(f"Started {s} at {position}")
                for b in benched:
                    self.lineup_changes.append(f"Benched {b} from {position}")

    def log_lineup(self):
        if not self.lineup:
            logging.info("Lineup is not set.")
            return

        logging.info("Current Lineup Details:")
        for position, players in self.lineup.items():
            for player in players:
                logging.info(
                    f"{position}: {player['name']} (Avail Pos: {', '.join(player['available_positions'])}) "
                    f"- {player['points']} points - Game Today: {player['next_game'] == self.today}"
                )

        logging.info(f"Lineup changes: {self.get_lineup_changes()}")


if __name__ == "__main__":
    yApi = api.YahooApi(os.path.dirname(os.path.realpath(__file__)))
    manager = TeamManager(yApi, False)
    # player_details = manager.yApi.league.player_details(3341)
    # sorted_goalies = manager.get_players_by_position(test_roster)
    # for i in sorted_goalies["G"]:
    #     print(i)
    team = manager.get_team()
    players_by_position = manager.get_players_by_position(team)
    swaps = manager.set_best_lineup(players_by_position)
    manager.log_lineup()
