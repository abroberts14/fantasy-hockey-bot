#!/usr/bin/env python
import time
import datetime
import logging
from collections import OrderedDict
from itertools import product
import os
import json
import math
import yahoo.api as api
from util.parse import FantasyHockeyProjectionScraper

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
    def __init__(self, yApi, dry_run=False, cache=False):
        self.yApi = yApi
        self.cache = cache
        self.today = str(datetime.date.today())
        self.stats_dir = os.path.join(os.path.dirname(__file__), "stored_stats")
        self.dry_run = dry_run
        self.previous_lineup = None
        self.lineup = None  # dict of roster, grouped by position
        self.lineup_changes = []
        self.roster = []  # list of all players, not grouped by position

        self.league_statistics = {}
        self.league_normalized_stats = {}
        self.league_rankings = {}

        self.player_score_weight = 0.8
        self.advanced_score_weight = 0.1
        self.projection_weight = 0.2
        self.ownership_weight = 0.3

        self.roster_ranked = {}  # dict of player name and ranked total points by time period
        self.league_taken_ranked = {}  # dict of player name and ranked total points by time period
        self.league_free_agents_ranked = {}  # dict of player name and ranked total points by time period
        self.normalized_roster_stats = {}
        self.normalized_league_taken_stats = {}
        self.normalized_league_free_agents_stats = {}  # dict of player name and ranked total points by time period

        self.time_periods = ["lastweek", "lastmonth", "season"]
        self.skater_categories = ["G", "A", "P", "+/-", "PIM", "PPP", "SOG", "FW", "HIT", "BLK"]
        self.ranked_players = []  # list of players ranked worst to best based on total points through diff time periods
        self.moves_left = 0
        self.active_players = []
        self.open_roster_spots = 0
        self.inactive_positions = ["IR+", "IL", "NA", "IR", "IR-LT"]
        self.not_playing_statuses = ["DTD", "O", "IR-LT"]

        self.taken_players_raw = []
        self.free_agents_skaters_raw = []
        self.free_agents_goalies_raw = []
        self.league_average_goalie_stats = {}
        self.league_average_skater_stats = {}

    def get_team(self, force_refetch=False):
        team = self._load_or_fetch("team", None)
        if force_refetch:
            team = None
        if team is not None:
            self.roster = team
            lineup = self._load_or_fetch("lineup", None)
            active_players = self._load_or_fetch("active_players", None)
            moves_left = self._load_or_fetch("moves_left", None)

            self.lineup = lineup
            self.previous_lineup = lineup
            self.active_players = active_players
            self.moves_left = moves_left

            if self.roster is None or self.lineup is None or self.active_players is None or self.moves_left is None:
                logging.info("Error loading roster or lineup not found, fetching from Yahoo API")
                self.roster = []
                self.lineup = {}
                self.active_players = []
                self.moves_left = 0
            else:
                required_total, active_roster_count = self.get_required_and_active_roster_spots()
                self.open_roster_spots = required_total - active_roster_count
                logging.info(f"Moves left: {self.moves_left}")
                logging.info(f"Roster full: {self.is_roster_full()}")
                logging.info(f"Open roster spots: {self.open_roster_spots}")

                return team
        else:
            logging.info("No cached team or lineup found, fetching from Yahoo API")
        roster = self.yApi.get_roster()
        lineups = {}
        team = []
        self.active_players = []

        for player in roster:
            position = player["selected_position"]
            player_data = self._build_player_data(player)
            player_data["percent_owned"] = self.yApi.league.percent_owned([player["player_id"]])[0]["percent_owned"]

            player_data["locked"] = int(player_data["percent_owned"]) >= 80

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

        self.moves_left = int(self.yApi.max_moves) - int(self.yApi.team_data["roster_adds"]["value"])
        logging.info(f"Moves left: {self.moves_left}")
        logging.info(f"Roster full: {self.is_roster_full()}")

        if self.cache:
            with open(os.path.join(self.stats_dir, f"{self.today}_team.json"), "w") as f:
                json.dump(self.roster, f)
            with open(os.path.join(self.stats_dir, f"{self.today}_lineup.json"), "w") as f:
                json.dump(self.lineup, f)
            with open(os.path.join(self.stats_dir, f"{self.today}_active_players.json"), "w") as f:
                json.dump(self.active_players, f)
            with open(os.path.join(self.stats_dir, f"{self.today}_moves_left.json"), "w") as f:
                json.dump(self.moves_left, f)
        return team

    def get_roster(self):
        return self.roster

    def is_roster_full(self):
        """Check if the roster meets or exceeds the league position requirements."""
        required_total, active_roster_count = self.get_required_and_active_roster_spots()

        return active_roster_count >= required_total

    def get_required_and_active_roster_spots(self):
        required_total = sum(
            int(pos_info["count"])
            for pos, pos_info in self.yApi.league_positions.items()
            if pos not in self.inactive_positions  # Exclude IR slots from the count
        )

        # Count active roster spots (excluding IR/IL)
        active_roster_count = len(self.active_players)

        logging.info(f"Required roster spots: {required_total}")
        logging.info(f"Current active players: {active_roster_count}")
        return required_total, active_roster_count

    def _build_player_data(self, player):
        player_data = self.yApi.getPlayerData(self.yApi.credentials["game_key"] + ".p." + str(player["player_id"]))

        player_data["current_position"] = player["selected_position"]
        player_data["key"] = self.yApi.credentials["game_key"] + ".p." + str(player["player_id"])
        player_data["id"] = player["player_id"]
        return player_data

    def calculate_best_lineup(self, optimized_replacements):
        best_lineup = {}
        max_points = 0
        position_options = {position: candidates for position, candidates in optimized_replacements.items()}

        if any(not candidates for candidates in position_options.values()):
            logging.info("One or more positions have no candidates available.")
            return best_lineup

        for combination in product(*position_options.values()):
            lineup, total_points = self._evaluate_combination(position_options.keys(), combination)
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

    def put_injured_players_on_il(self):
        logging.info("Checking for inactive or injured players to put on IL")
        players_to_put_on_il = []

        for player in self.roster:
            player_name = player["name"]
            player_status = player["status"]
            player_current_position = player["current_position"]
            player_available_positions = player["available_positions"]
            has_inactive_status = player_status in self.not_playing_statuses

            find_inactive_position_in_available_positions = next((pos for pos in self.inactive_positions if pos in player_available_positions), None)
            is_currently_in_inactive_position = player_current_position in self.inactive_positions

            if has_inactive_status:
                logging.info(f"Player {player_name} is {player_status}")
                if find_inactive_position_in_available_positions:
                    logging.debug(f"Player is eligible for inactive position {find_inactive_position_in_available_positions}")

                    if is_currently_in_inactive_position:
                        logging.debug(f"Player {player_name} already positioned on {find_inactive_position_in_available_positions}, no need to put on IL")
                    else:
                        logging.info(f"Putting {player_name} on IL")
                        players_to_put_on_il.append(
                            {"player_id": player["key"].split(".")[2], "selected_position": find_inactive_position_in_available_positions}
                        )
                else:
                    logging.debug(f"Player {player_name} is not eligible for IL")
        logging.info(f"Players to put on IL: {players_to_put_on_il}")
        if players_to_put_on_il:
            if not self.dry_run:
                self.yApi.team.change_positions(datetime.datetime.now(), players_to_put_on_il)
                self.get_team(True)

    def put_players_on_bench_from_inactive(self):
        logging.info("Starting to check for players that are no longer inactive/injured to put on bench")
        players_to_bench = []

        for player in self.roster:
            player_name = player["name"]
            player_status = player["status"]
            player_current_position = player["current_position"]
            # logging.info(f"Player status: {player_status} - Current position: {player_current_position}")
            has_inactive_status = player_status in self.not_playing_statuses
            is_in_inactive_position = player_current_position in self.inactive_positions

            if not has_inactive_status and is_in_inactive_position:
                if self.is_roster_full():
                    logging.debug(f"Roster is full, unable move to bench for {player_name}")
                else:
                    logging.info(f"Player {player_name} is no longer inactive and is currently in an inactive position.")
                    player["current_position"] = "BN"
                    logging.info(f"Moving {player_name} from {player_current_position} to BN")
                    players_to_bench.append({"player_id": player["key"].split(".")[2], "new_position": "BN"})
            else:
                if has_inactive_status and is_in_inactive_position:
                    logging.debug(f"Player {player_name} is still inactive and listed as inactive. No change needed.")

        logging.info(f"Total players moved to bench from IL: {len(players_to_bench)}")
        if players_to_bench:
            if not self.dry_run:
                self.yApi.team.change_positions(datetime.datetime.now(), players_to_bench)
                self.get_team(True)

    def get_least_owned_players_sorted(self):
        logging.info("Starting to sort the roster by ascending ownership percentage, excluding locked players")

        # Filter out players who are locked
        unlocked_players = [player for player in self.roster if not player.get("locked", False)]

        # Sorting the unlocked players by the 'percent_owned' field in ascending order
        sorted_roster = sorted(unlocked_players, key=lambda player: player["percent_owned"])
        return sorted_roster

    def get_stats_for_league(self, location="taken", position=None):
        id_key = "player_id"
        if location == "taken":
            player_list = self.taken_players_raw
        elif location == "free_agents":
            if position == "G":
                player_list = self.free_agents_goalies_raw
            else:
                player_list = self.free_agents_skaters_raw
        elif location == "roster":
            player_list = self.roster
            id_key = "id"
        else:
            logging.error(f"Invalid location to get stats for: {location}")
            return {}
        valid_time_frames = ["lastweek", "lastmonth", "season", "average_season"]
        logging.info("Starting to fetch stats for all valid time frames.")

        # Collect player IDs for the API call
        player_ids = [player[id_key] for player in player_list]

        positions = "available_positions" if location == "roster" else "eligible_positions"
        # Dictionary to hold stats per time frame
        stat_roster_list = {}
        # Loop through each time frame and fetch stats
        for player in player_list:
            stat_roster_list[player["name"]] = {"percent_owned": player["percent_owned"], "available_positions": player[positions]}
        for time_frame in valid_time_frames:
            # Fetch the stats from the league API
            player_stats = self.yApi.league.player_stats(player_ids, req_type=time_frame)
            # Store stats in the dictionary under their respective time frame
            # for player in self.roster:
            #     stat_roster_list[player["name"]][time_frame] = {}
            # Log the fetched stats
            for stat in player_stats:
                cleaned_stats = {k: v for k, v in stat.items() if k != "player_id" and k != "name"}
                logging.debug(f"Stats for Player ID {stat['player_id']} during {time_frame}: {cleaned_stats}")
                # player = {"name": stat["name"], "id": stat["player_id"], "stats": {time_frame: cleaned_stats}}
                stat_roster_list[stat["name"]][time_frame] = cleaned_stats

        logging.info("Player stats for all time frames updated successfully in self.league_stats")
        logging.debug(f"League stats: {stat_roster_list}")
        return stat_roster_list

    def get_league_average_goalie_stats(self):
        for time_period in self.time_periods:
            average_goalie_stats = self.get_average_goalie_stats_for_time_period(time_period)
            self.league_average_goalie_stats[time_period] = average_goalie_stats
        return self.league_average_goalie_stats

    def get_league_average_skater_stats(self):
        for time_period in self.time_periods:
            average_skater_stats = self.get_average_skater_stats_for_time_period(time_period)
            self.league_average_skater_stats[time_period] = average_skater_stats
        return self.league_average_skater_stats

    def get_average_goalie_stats_for_time_period(self, time_period):
        # Fetch all players taken by teams in the league
        taken_players = self.taken_players_raw
        logging.info(f"Total players taken: {len(taken_players)}")

        # Filter out goalies
        goalies = [player for player in taken_players if "G" in player["eligible_positions"]]
        logging.info(f"Total goalies taken: {len(goalies)}")

        # Initialize sums and counts for averaging
        goalie_stats = {}
        count = {}

        # Prepare list of goalie player IDs
        goalie_ids = [goalie["player_id"] for goalie in goalies]
        logging.info(f"Goalie IDs collected: {goalie_ids}")

        # Fetch stats for all goalies for the specified time period using the league API
        goalie_player_stats = self.yApi.league.player_stats(goalie_ids, req_type=time_period)
        logging.debug(f"Fetched goalie stats for time period {time_period}: {goalie_player_stats}")

        # Sum up stats for all goalies
        for stat in goalie_player_stats:
            for key, value in stat.items():
                if key not in ["player_id", "name", "position_type"]:
                    # Convert value to float to ensure correct data type for arithmetic operations
                    float_value = float(value) if isinstance(value, (int, float, str)) and str(value).replace(".", "", 1).isdigit() else 0
                    if key in goalie_stats:
                        goalie_stats[key] += float_value
                        count[key] += 1
                    else:
                        goalie_stats[key] = float_value
                        count[key] = 1
        # Calculate averages
        average_stats = {key: goalie_stats[key] / count[key] for key in goalie_stats if count[key] > 0}

        logging.debug(f"Average stats for goalies for {time_period}: {average_stats}")
        return average_stats

    def get_average_skater_stats_for_time_period(self, time_period):
        # Fetch all players taken by teams in the league
        taken_players = self.taken_players_raw
        logging.info(f"Total players taken: {len(taken_players)}")

        # Filter out skaters
        skaters = [player for player in taken_players if "G" not in player["eligible_positions"]]
        logging.info(f"Total skaters taken: {len(skaters)}")

        # Initialize sums and counts for averaging
        skater_stats = {}
        count = {}

        # Prepare list of skater player IDs
        skater_ids = [skater["player_id"] for skater in skaters]
        logging.debug(f"Skater IDs collected: {skater_ids}")

        # Fetch stats for all goalies for the specified time period using the league API
        skater_player_stats = self.yApi.league.player_stats(skater_ids, req_type=time_period)
        logging.debug(f"Fetched skater stats for time period {time_period}: {skater_player_stats}")

        # Sum up stats for all skaters
        for stat in skater_player_stats:
            for key, value in stat.items():
                if key not in ["player_id", "name", "position_type"]:
                    # Convert value to float to ensure correct data type for arithmetic operations
                    float_value = float(value) if isinstance(value, (int, float, str)) and str(value).replace(".", "", 1).isdigit() else 0
                    if key in skater_stats:
                        skater_stats[key] += float_value
                        count[key] += 1
                    else:
                        skater_stats[key] = float_value
                        count[key] = 1

        # Calculate averages
        average_stats = {key: skater_stats[key] / count[key] for key in skater_stats if count[key] > 0}

        logging.debug(f"Average stats for skaters for {time_period}: {average_stats}")
        return average_stats

    def normalize_stats(self, stats_dict):
        # Initialize the normalized stats dictionary
        # logging.info(f"Stats dict: {stats_dict}")
        normalized_roster_stats = {name: {} for name in stats_dict}

        # Iterate over each time frame to normalize stats
        for time_frame in self.time_periods:
            # Extract all player stats for this time frame
            time_frame_stats = {name: player_stats.get(time_frame, {}) for name, player_stats in stats_dict.items()}
            # logging.info(f"Time frame stats: {time_frame_stats}")
            # Find the max and min values for each stat in this time frame
            stat_max = {}
            stat_min = {}
            for name, stats in time_frame_stats.items():
                for stat, value in stats.items():
                    if stat != "position_type":  # Skip non-numeric stats like position
                        # Ensure value is a float for accurate comparisons and arithmetic operations
                        if isinstance(value, str):
                            value = float(value) if value.replace(".", "", 1).isdigit() else 0
                        if stats["position_type"] == "G" and stat in self.league_average_goalie_stats[time_frame]:
                            # Normalize goalie stats against league average
                            value = value / self.league_average_goalie_stats[time_frame][stat] if self.league_average_goalie_stats[time_frame][stat] else 0
                        elif stats["position_type"] != "G" and stat in self.league_average_skater_stats[time_frame]:
                            value = value / self.league_average_skater_stats[time_frame][stat] if self.league_average_skater_stats[time_frame][stat] else 0
                        # Update max and min
                        if stat in stat_max:
                            stat_max[stat] = max(stat_max[stat], value)
                            stat_min[stat] = min(stat_min[stat], value)
                        else:
                            stat_max[stat] = value
                            stat_min[stat] = value

            # Normalize stats between 0 and 1
            for player, stats in time_frame_stats.items():
                normalized_roster_stats[player]["percent_owned"] = stats_dict[player]["percent_owned"]
                normalized_roster_stats[player]["available_positions"] = stats_dict[player]["available_positions"]
                normalized_roster_stats[player][time_frame] = {}
                for stat, value in stats.items():
                    if stat == "position_type":
                        normalized_roster_stats[player][time_frame][stat] = value
                    else:
                        if isinstance(value, str):
                            value = float(value) if value.replace(".", "", 1).isdigit() else 0
                        if stats["position_type"] == "G" and stat in self.league_average_goalie_stats[time_frame]:
                            # Use the adjusted value for normalization
                            value = value / self.league_average_goalie_stats[time_frame][stat] if self.league_average_goalie_stats[time_frame][stat] else 0
                        elif stats["position_type"] != "G" and stat in self.league_average_skater_stats[time_frame]:
                            value = value / self.league_average_skater_stats[time_frame][stat] if self.league_average_skater_stats[time_frame][stat] else 0
                        # Normalize using max and min values
                        if stat_max[stat] - stat_min[stat] > 0:  # Prevent division by zero
                            normalized_value = (value - stat_min[stat]) / (stat_max[stat] - stat_min[stat])
                            normalized_roster_stats[player][time_frame][stat] = round(normalized_value, 2)
                        else:
                            normalized_roster_stats[player][time_frame][stat] = 0.0

        logging.debug("Normalized roster stats:")
        logging.debug("--------------------------------")
        for player, stats in normalized_roster_stats.items():
            logging.debug(f"{player}: {stats}")
        return normalized_roster_stats

    def ownership_to_projected_points(self, percent_owned):
        """
        Convert ownership percentage to a points value based on specified thresholds.
        """
        if percent_owned >= 100:
            return 10
        elif percent_owned >= 30:
            return (percent_owned - 30) / 70 * 8 + 2  # Scale between 2 and 10
        elif percent_owned >= 20:
            return (percent_owned - 20) / 10 * 1 + 1  # Scale between 1 and 2
        else:
            return (percent_owned - 20) / 20  # Negative values below 20%

    def rank_players_by_time_period(self, time_period, stats_dict):
        # Dictionary to hold total scores and position type for each player
        player_scores = {}
        score_weight = self.player_score_weight
        advanced_weight = self.advanced_score_weight
        projection_weight = self.projection_weight
        ownership_weight = self.ownership_weight

        # score_weight = self.player_score_weight
        # advanced_weight = self.advanced_score_weight
        # projection_weight = self.projections_weight
        # ownership_weight = self.ownership_weight
        # Loop through each player and sum their scores for the given time period
        for player, periods in stats_dict.items():
            if time_period in periods:
                # Get position type and calculate score
                position_type = periods[time_period].get("position_type", "Unknown")
                available_positions = stats_dict[player]["available_positions"]
                cats = self.yApi.skater_categories if position_type == "P" else self.yApi.goalie_categories
                category_score = sum(value for stat, value in periods[time_period].items() if stat in cats)
                advanced_stats = {stat: value for stat, value in periods["season"].items() if stat != "position_type" and stat not in cats}
                advanced_score = sum(advanced_stats.values())
                on_current_roster = player in [p["name"] for p in self.roster]
                percent_owned = stats_dict[player]["percent_owned"]
                scaled_percent_owned = (percent_owned / 100) * ownership_weight  # Apply weight to ownership
                projections = self.get_player_projections(player)
                if projections:
                    projections_score = float(projections["Fantasy"])
                    weighted_score = (
                        (category_score * score_weight) + (advanced_score * advanced_weight) + (projections_score * projection_weight) + scaled_percent_owned
                    )
                else:
                    projections_score = self.ownership_to_projected_points(percent_owned)
                    # Apply a 0.8 penalty multiplier when projections are missing
                    weighted_score = (
                        (category_score * score_weight) + (advanced_score * advanced_weight) + (projections_score * projection_weight) + scaled_percent_owned
                    )

                player_scores[player] = {
                    "available_positions": available_positions,
                    "score": category_score,
                    "advanced_score": advanced_score,
                    "weighted_score": weighted_score,
                    "position_type": position_type,
                    "on_current_roster": on_current_roster,
                    "percent_owned": percent_owned,
                    "projections_score": projections_score,
                }

        # Sort players by their total scores in descending order
        sorted_players = sorted(player_scores.items(), key=lambda item: item[1]["weighted_score"], reverse=True)

        # Assign rank to each player and store them in an OrderedDict
        ranked_players = OrderedDict()
        rank = 1
        for player, details in sorted_players:
            details["rank"] = rank
            ranked_players[player] = details
            rank += 1

        # Log the ranked players
        logging.debug(f"Players ranked for time period {time_period}: {list(ranked_players.items())}")

        return list(ranked_players.items())

    def sort_and_rank_players(self, player_scores):
        sorted_players = sorted(player_scores, key=lambda item: item[1]["weighted_score"], reverse=True)

        # Assign rank to each player and store them in an OrderedDict
        ranked_players = OrderedDict()
        rank = 1
        for player, details in sorted_players:
            details["rank"] = rank
            ranked_players[player] = details
            rank += 1
        return list(ranked_players.items())

    def sort_and_rank_projections(self, player_scores):
        sorted_players = sorted(player_scores, key=lambda item: item[1]["Fantasy"], reverse=True)

        # Assign rank to each player and store them in an OrderedDict
        ranked_players = OrderedDict()
        rank = 1
        for player, details in sorted_players:
            details["rank"] = rank
            ranked_players[player] = details
            rank += 1
        return list(ranked_players.items())

    def get_player_projections(self, player_name):
        # make this safe for unknown players
        return self.player_projections.get(player_name, {})

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
        filled_positions_count = {position: 0 for position in required_roster_list.keys()}
        used_player_keys = set()
        for position, player in calculated_lineup.items():
            if not isinstance(player, list):
                calculated_lineup[position] = [player]
            filled_positions_count[position] += len(calculated_lineup[position])
            used_player_keys.update(p["key"] for p in calculated_lineup[position])
        # Populate each position to meet the required count
        for position, required_count in required_roster_list.items():
            available_players = roster.get(position, [])
            filled_count = filled_positions_count[position]

            # Add players until we reach the required count
            while filled_count < required_count["count"] and available_players:
                next_player = available_players.pop(0)
                if next_player["key"] not in used_player_keys:
                    logging.debug(f"Adding {next_player['name']} to {position}")
                    if position not in calculated_lineup:
                        calculated_lineup[position] = []
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
                    logging.debug(f"Player {player['name']} already used at {player['current_position']}, skipping")
        # Add bench players to the calculated lineup under a "BN" key
        calculated_lineup["BN"] = bench_players

        # Log final calculated lineup with all required positions filled, including bench
        logging.debug(f"Final calculated lineup including bench: {calculated_lineup}")
        self.lineup = calculated_lineup
        original_lineup_payload = self.get_roster_update_payload_on_lineup(self.previous_lineup)
        new_lineup_payload = self.get_roster_update_payload_on_lineup(calculated_lineup)
        # Sort both lists in place
        original_lineup_payload.sort(key=lambda x: (x["player_id"], x["selected_position"]))
        new_lineup_payload.sort(key=lambda x: (x["player_id"], x["selected_position"]))

        if not self.dry_run:
            # self.yApi.roster_payload_manager.fill_roster(calculated_lineup)
            logging.debug(f"Payload: {new_lineup_payload}")
            if len(new_lineup_payload) > 0 and new_lineup_payload != original_lineup_payload:
                self.yApi.team.change_positions(datetime.datetime.now(), new_lineup_payload)
                logging.info("Lineup changed")
                self.get_team(True)
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
                        (int(time.time()) - int(x.get("new_notes_timestamp", 0))) / 3600,
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
            logging.info("One of the lineups is not set.")
            return
        self.lineup_changes = []
        # Create comprehensive maps of previous and current lineups by player names
        previous_map = {player["name"]: {"position": pos, "player": player} for pos, players in self.previous_lineup.items() for player in players}
        current_map = {player["name"]: {"position": pos, "player": player} for pos, players in self.lineup.items() for player in players}

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
                    self.lineup_changes.append(f"Moved {m} from {position} to {new_pos}")
            if started and benched:
                for s, b in zip(started, benched):
                    self.lineup_changes.append(f"Started {s} at {position}, benching {b}")
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

    def get_player_positions(self, player_id):
        player_details = self.yApi.league.player_details(player_id)
        return player_details[0]["eligible_positions"]

    def fetch_players_stats(self):
        def scrape():
            scraper_skaters = FantasyHockeyProjectionScraper(url="https://www.numberfire.com/nhl/fantasy/remaining-projections/skaters")
            scraper_skaters.fetch_data()
            scraper_goalies = FantasyHockeyProjectionScraper(url="https://www.numberfire.com/nhl/fantasy/remaining-projections/goalies")
            scraper_goalies.fetch_data()
            skaters = scraper_skaters.fetch_all_players()
            goalies = scraper_goalies.fetch_all_players()
            self.player_projections = {**skaters, **goalies}
            if self.cache:
                with open(os.path.join(self.stats_dir, f"{self.today}_player_projections.json"), "w") as f:
                    json.dump(self.player_projections, f)
            return self.player_projections

        self.player_projections = self._load_or_fetch("player_projections", scrape)
        logging.info(f"Player projections length: {len(self.player_projections) }")
        # Fetch or load each dataset
        self.taken_players_raw = self._load_or_fetch("taken_players_raw", self.yApi.league.taken_players)
        self.free_agents_skaters_raw = self._load_or_fetch("free_agents_skaters_raw", self.yApi.league.free_agents, position="P")
        self.free_agents_goalies_raw = self._load_or_fetch("free_agents_goalies_raw", self.yApi.league.free_agents, position="G")

        self.league_average_goalie_stats = self._load_or_fetch("league_average_goalie_stats", self.get_league_average_goalie_stats)
        self.league_average_skater_stats = self._load_or_fetch("league_average_skater_stats", self.get_league_average_skater_stats)

        try:
            self.league_statistics = {}
            if self.cache:
                with open(os.path.join(self.stats_dir, f"{self.today}_league_statistics.json"), "r") as f:
                    self.league_statistics = json.load(f)
        except FileNotFoundError:
            logging.info("No cached league statistics found, fetching fresh data")
        if not self.league_statistics:
            self.league_statistics["taken"] = self.get_stats_for_league(location="taken")
            self.league_statistics["free_agents_skaters"] = self.get_stats_for_league(location="free_agents", position="P")
            self.league_statistics["free_agents_goalies"] = self.get_stats_for_league(location="free_agents", position="G")
            self.league_statistics["roster"] = self.get_stats_for_league(location="roster")
            if self.cache:
                with open(os.path.join(self.stats_dir, f"{self.today}_league_statistics.json"), "w") as f:
                    json.dump(self.league_statistics, f)
        try:
            self.league_normalized_stats = {}
            if self.cache:
                with open(os.path.join(self.stats_dir, f"{self.today}_league_normalized_stats.json"), "r") as f:
                    self.league_normalized_stats = json.load(f)
        except FileNotFoundError:
            logging.info("No cached league normalized stats found, fetching fresh data")
        if not self.league_normalized_stats:
            self.league_normalized_stats["taken"] = self.normalize_stats(self.league_statistics["taken"])
            self.league_normalized_stats["free_agents_skaters"] = self.normalize_stats(self.league_statistics["free_agents_skaters"])
            self.league_normalized_stats["free_agents_goalies"] = self.normalize_stats(self.league_statistics["free_agents_goalies"])
            self.league_normalized_stats["roster"] = self.normalize_stats(self.league_statistics["roster"])

        if self.cache:
            with open(os.path.join(self.stats_dir, f"{self.today}_league_normalized_stats.json"), "w") as f:
                json.dump(self.league_normalized_stats, f)
            with open(os.path.join(self.stats_dir, f"{self.today}_league_average_goalie_stats.json"), "w") as f:
                json.dump(self.league_average_goalie_stats, f)
            with open(os.path.join(self.stats_dir, f"{self.today}_league_average_skater_stats.json"), "w") as f:
                json.dump(self.league_average_skater_stats, f)

    def set_league_rankings(self):
        locations = ["taken", "free_agents", "roster"]
        try:
            with open(os.path.join(self.stats_dir, f"{self.today}_league_rankings.json"), "r") as f:
                self.league_rankings = json.load(f)
        except FileNotFoundError:
            for location in locations:
                self.league_rankings[location] = {}
                for time_frame in self.time_periods:
                    if location == "free_agents":
                        skater_ranks = self.rank_players_by_time_period(time_frame, self.league_normalized_stats["free_agents_skaters"])
                        goalie_ranks = self.rank_players_by_time_period(time_frame, self.league_normalized_stats["free_agents_goalies"])
                        fa_ranks_unsorted = skater_ranks + goalie_ranks
                        self.league_rankings[location][time_frame] = self.sort_and_rank_players(fa_ranks_unsorted)

                    else:
                        self.league_rankings[location][time_frame] = self.rank_players_by_time_period(time_frame, self.league_normalized_stats[location])

        # with open(os.path.join(self.stats_dir, f"{self.today}_league_rankings.json"), "w") as f:
        #     json.dump(self.league_rankings, f)

    def find_player_in_roster(self, player_name):
        for player in self.roster:
            name = player["name"]
            if name == player_name:
                return player
        return None

    def is_player_injured(self, player_name):
        player = self.find_player_in_roster(player_name)
        if player:
            player_status = player["status"]
            player_current_position = player["current_position"]
            has_inactive_status = player_status in self.not_playing_statuses
            is_currently_in_inactive_position = player_current_position in self.inactive_positions
            if has_inactive_status or is_currently_in_inactive_position:
                return True
            else:
                return False

    def compare_roster_to_free_agents(self, potential_free_agents):
        current_roster_skaters = self.get_league_ranks_by_time_period("lastweek", "roster", roster_only=True, position_type="P")
        current_roster_goalies = self.get_league_ranks_by_time_period("lastmonth", "roster", roster_only=True, position_type="G")
        combined_current_roster = current_roster_skaters + current_roster_goalies
        current_roster = self.sort_and_rank_players(combined_current_roster)
        free_agents_lastweek = potential_free_agents["lastweek"]

        combined = current_roster + free_agents_lastweek
        sorted_combined = self.sort_and_rank_players(combined)
        required_total, active_roster_count = self.get_required_and_active_roster_spots()

        suggested_replacements = []

        worst_rostered_players = list(reversed(current_roster))
        for name, data in worst_rostered_players:
            player = self.find_player_in_roster(name)
            if self.is_player_injured(name):
                continue

            logging.debug(f"\nRostered Player: {name}")
            logging.debug(f"Score: projections {data['projections_score']:.2f} | weighted {data['weighted_score']:.2f} | Owned: {data['percent_owned']}%")
            if player["locked"]:
                logging.debug(f"{name} is locked, skipping")
                continue
            # Find potential upgrades among free agents
            for fa_name, fa_data in free_agents_lastweek:
                score_difference = fa_data["weighted_score"] - data["weighted_score"]
                can_play_position = next((pos for pos in fa_data.get("available_positions", []) if pos in data.get("available_positions", [])), None)

                if can_play_position:
                    logging.debug(f"Found matching position: {can_play_position}")
                else:
                    logging.debug("No matching positions found")
                score_threshold = 2
                if can_play_position == "Util":
                    score_threshold = score_threshold + 1
                close_replacements = []
                if score_difference > score_threshold and can_play_position and can_play_position != "Util":
                    logging.info(f"Potential Upgrade: {fa_name}")
                    logging.info(f"Score: {fa_data['weighted_score']:.2f} | Owned: {fa_data['percent_owned']}%")
                    logging.info(f"Improvement: {score_difference:.2f} points")

                    suggested_replacements.append(
                        {
                            "drop": name,
                            "add": fa_name,
                            "improvement": score_difference,
                            "drop_score": data["weighted_score"],
                            "add_score": fa_data["weighted_score"],
                        }
                    )
                else:
                    if score_difference > 0:
                        logging.info(f"FA {fa_name} almost a match over {name}: {score_difference:.2f} points | {can_play_position}")
                        if can_play_position:
                            close_replacements.append(
                                {
                                    "drop": name,
                                    "add": fa_name,
                                    "improvement": score_difference,
                                    "drop_score": data["weighted_score"],
                                    "add_score": fa_data["weighted_score"],
                                }
                            )

        for name, data in sorted_combined:
            logging.debug(
                f"{name} - Weighted Score: {data['weighted_score']:.2f} | Projections Score: {data['projections_score']:.2f} | Ownership: {data['percent_owned']}%"
            )

        return suggested_replacements, close_replacements

    def find_best_free_agents(self, position_type="P"):
        free_agent_skaters_by_period = {}
        free_agent_skaters = self.get_league_ranks_by_time_period("season", "free_agents", roster_only=False, position_type=position_type)

        for time_period in self.time_periods:
            free_agent_skaters = self.get_league_ranks_by_time_period(time_period, "free_agents", roster_only=False, position_type=position_type)
            free_agent_skaters_by_period[time_period] = free_agent_skaters[:30]  # Get top 30 skaters for the period
        season_players = {player[0] for player in free_agent_skaters_by_period.get("season", [])}
        logging.info(f"Unique season players: {len(season_players)}")
        total_percent = []
        skaters = free_agent_skaters_by_period.get("season", [])

        for name, data in skaters:
            if data["rank"] > 25:
                break
            total_percent.append(data["percent_owned"])
            logging.debug(
                f"{name} - Score: {data["score"]} | Advanced Score: {data["advanced_score"]} | Weighted Score: {data["weighted_score"]} | Projection Score: {data["projections_score"]} | Percent: {data["percent_owned"]} "
            )
        # calculate average percent owned
        avg_percent_owned = sum(total_percent) / len(total_percent)
        logging.info(f"Average percent owned: %{avg_percent_owned}")

        last_month_players = {player[0] for player in free_agent_skaters_by_period.get("lastmonth", [])}
        logging.debug(f"Unique last month players: {len(last_month_players)}")

        last_week_players = {player[0] for player in free_agent_skaters_by_period.get("lastweek", [])}
        logging.debug(f"Unique last week players: {len(last_week_players)}")

        # Find common players in all periods
        common_players = season_players.intersection(last_month_players, last_week_players)
        logging.info(f"Players common in all periods: {len(common_players)}")
        # Filter lists to include only common players
        for period in free_agent_skaters_by_period:
            free_agent_skaters_by_period[period] = [player for player in free_agent_skaters_by_period[period] if player[0] in common_players]

        return free_agent_skaters_by_period

    def perform_free_agent_add_drop(self, player_to_add, player_to_drop):
        if self.moves_left <= 0:
            logging.info("Cannot add player due to lack of moves")
            return
        shortages = self.identify_positional_shortages()

        name = player_to_add
        # Format player name
        formatted_name = " ".join([part for part in name.split() if "'" not in part])
        logging.info(f"Formatted name: {formatted_name}")

        # Get player details
        try:
            player_details = self.yApi.league.player_details(formatted_name)
        except Exception as e:
            logging.warning(f"Failed to get player details for {name}: {e}")
            return

        # Select the appropriate player from details
        selected_player = None
        if len(player_details) > 1:
            selected_player = next((p for p in player_details if p["name"]["full"] == name), None)
        elif player_details:
            selected_player = player_details[0]

        if not selected_player:
            logging.warning(f"No player details found for {name}")
            return

        # Determine position to fill
        player_eligible_positions = selected_player["eligible_positions"]
        position_to_fill = None
        for pos in player_eligible_positions:
            position_to_fill = next((p for p in shortages if p[0] == pos), None)
            if position_to_fill:
                break

        # Add player if a position can be filled
        if position_to_fill or not shortages:
            logging.info(f"Adding {name} for position {position_to_fill if position_to_fill else player_eligible_positions} to the lineup")
            if player_to_drop:
                try:
                    player_to_drop_details = self.yApi.league.player_details(player_to_drop)
                except Exception as e:
                    logging.warning(f"Failed to get player details for {player_to_drop}: {e}")
                    return
                logging.info(f"Dropping {player_to_drop} id {player_to_drop_details[0]['player_id']}")
                logging.info(f"Adding {name}")
                self.yApi.team.add_and_drop_players(selected_player["player_id"], player_to_drop_details[0]["player_id"])
                self.get_team(True)
            else:
                self.yApi.team.add_player(selected_player["player_id"])
                self.get_team(True)
        else:
            logging.info(f"Cannot add {name} due to unmet positional needs")

    def handle_necessary_adds(self):
        # Check if there are available moves or open roster spots
        if self.moves_left == 0:
            logging.info("No moves left, cannot add any players")
            return
        if self.open_roster_spots == 0:
            logging.info("No open roster spots, cannot add any players")
            return

        # Identify positional shortages
        shortages = self.identify_positional_shortages()
        for shortage in shortages:
            logging.info(shortage)

        # Log free agent skaters data
        fa_skaters = self.find_best_free_agents("P")
        fa_goalies = self.find_best_free_agents("G")
        for period in reversed(self.time_periods):
            logging.info(f"--------- {period.upper()} ---------")

            for name, data in fa_skaters[period]:
                logging.info(f"{name} - {data['rank']} - {data['on_current_roster']}")

        players_to_add = []
        free_agents = fa_skaters["lastweek"] + fa_goalies["lastweek"]
        # Iterate through the best free agent skaters of the last week
        for name, data in free_agents:
            # Find player's data in last month rankings
            # Find player's data in last month and season rankings
            last_month_data = next((player_data for player_name, player_data in fa_skaters["lastmonth"] if player_name == name), None)
            season_data = next((player_data for player_name, player_data in fa_skaters["season"] if player_name == name), None)

            last_month_rank = last_month_data["rank"] if last_month_data else "Not ranked"
            season_rank = season_data["rank"] if season_data else "Not ranked"

            logging.info(f"Evaluating {name}:  " f"Rank Among FA | Last week: {data['rank']} | Last Month: {last_month_rank} | Season: {season_rank}| ")
            if self.moves_left - len(players_to_add) <= 0 or self.open_roster_spots - len(players_to_add) <= 0:
                logging.info("Breaking free agent search due to lack of moves or open spots")
                break

            self.perform_free_agent_add_drop(name, None)
        # Summary logging
        logging.info("--------------------------------")
        logging.info(f"Total season: {len(fa_skaters['season'])}")
        logging.info(f"Total last month: {len(fa_skaters['lastmonth'])}")
        logging.info(f"Total last week: {len(fa_skaters['lastweek'])}")
        logging.info("--------------------------------")
        logging.info(f"Players to add: {len(players_to_add)}")

    def identify_positional_shortages(self):
        required_positions = self.yApi.league_positions
        roster_positions = {pos: 0 for pos in required_positions}
        shortages = []
        # Count players by position from roster
        for player in self.roster:
            for position in player["available_positions"]:
                if position in roster_positions:
                    roster_positions[position] += 1
                    logging.debug(f"Counted position {position} for {player['name']}")

        # Check if we meet position requirements
        for pos, pos_info in required_positions.items():
            if pos in self.inactive_positions:
                continue
            if pos == "BN":
                continue
            required_count = pos_info.get("count", 0)
            current_count = roster_positions[pos]
            logging.debug(f"Position {pos}: Have {current_count}, Need {required_count}")

            if current_count < required_count:
                shortages.append((pos, "Insufficient players", current_count, "Positional shortage"))
                logging.warning(f"Position shortage detected for {pos}")

        logging.info(f"Total shortages found: {len(shortages)}")
        return shortages
        # Helper function to load or fetch data

    def get_league_ranks_by_time_period(self, time_period, location, roster_only=False, position_type="both"):
        # Retrieve the list of players for the specified location and time period
        players = self.league_rankings[location][time_period]

        # Define a function to check if a player should be included based on the position type
        def is_correct_position(player):
            if position_type == "both":
                return True  # All players are included if we're looking for both positions
            return player[1]["position_type"] == position_type

        # Define a function to check roster status
        def is_on_roster(player):
            # Only check roster status if 'roster_only' is True
            return player[1].get("on_current_roster", False) if roster_only else True

        # Combine the filters and apply them
        filtered_rankings = [player for player in players if is_correct_position(player) and is_on_roster(player)]

        return filtered_rankings

    def _load_or_fetch(self, filename, fetch_func, **kwargs):
        if not self.cache:
            if fetch_func is not None:
                data = fetch_func(**kwargs)
                return data
            return None
        stats_dir = "stored_stats"

        # Ensure the stats directory exists
        os.makedirs(stats_dir, exist_ok=True)
        filepath = os.path.join(stats_dir, f"{self.today}_{filename}.json")

        if os.path.exists(filepath):
            with open(filepath, "r") as f:
                return json.load(f)

        logging.info(f"Fetching fresh data for {filename}")
        if fetch_func is not None:
            data = fetch_func(**kwargs)

            # Cache the results
            with open(filepath, "w") as f:
                json.dump(data, f)
        else:
            data = None
        return data


if __name__ == "__main__":
    yApi = api.YahooApi(os.path.dirname(os.path.realpath(__file__)))
    manager = TeamManager(yApi, dry_run=False, cache=False)
    transactions = []

    team = manager.get_team(True)

    logging.info("--------------------------------")

    manager.put_injured_players_on_il()
    manager.put_players_on_bench_from_inactive()

    logging.info("--------------------------------")

    players_by_position = manager.get_players_by_position(team)
    swaps = manager.set_best_lineup(players_by_position)

    changes = manager.get_lineup_changes()
    transactions.extend(changes)

    logging.info("--------------------------------")

    # Resync roster to latest
    team = manager.get_roster()

    manager.fetch_players_stats()
    manager.set_league_rankings()

    logging.info("--------------------------------")

    if not manager.is_roster_full():
        manager.handle_necessary_adds()
    else:
        logging.info("Roster is full, no need to add any players")

    logging.info("--------------------------------")

    # Resync roster to latest
    team = manager.get_roster()

    free_agents = manager.find_best_free_agents()
    logging.info(f"Potential free agents length: {len(free_agents['lastweek'])}")
    possible_adds, close_replacements = manager.compare_roster_to_free_agents(free_agents)
    for i in possible_adds:
        logging.info(f"{i['add']} - {i['drop']} - {i['improvement']:.2f} points")

        # manager.perform_free_agent_add_drop(i["add"], i["drop"])
        transactions.append(f"Added {i['add']} and dropped {i['drop']}")
        team = manager.get_roster()

    if len(possible_adds) > 0:
        players_by_position = manager.get_players_by_position(team)
        new_swaps = manager.set_best_lineup(players_by_position)
        changes = manager.get_lineup_changes()
        transactions.extend(changes)

    logging.info("--------------------------------")

    # Resync roster to latest
    team = manager.get_roster()

    manager.log_lineup()
    for transaction in transactions:
        logging.info(transaction)
