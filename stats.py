import logging
from league import League
import cache
import pandas as pd
import os
from util import constants
from tqdm import tqdm
import numpy as np


class LeagueStatistics(League):
    def __init__(self, yahoo_api, league_key, team_key, nhl, roster):
        super().__init__(yahoo_api, league_key, team_key, nhl)

        self.logger = logging.getLogger(__name__)
        self.projection_weight = 0.3
        self.ownership_weight = 0.2
        self.score_weight = 0.7

        self.roster = roster
        self.taken = cache.load_object("league_taken_stats") or self.get_stats_for_league(location="taken")
        self.free_agents = cache.load_object("league_free_agents_stats") or self.get_stats_for_league(location="free_agents")
        self.rostered = cache.load_object("league_rostered_stats") or self.get_stats_for_league(location="roster")
        cache.save_object(self.rostered, "league_rostered_stats")
        cache.save_object(self.free_agents, "league_free_agents_stats")
        cache.save_object(self.taken, "league_taken_stats")
        # self.normalized_roster = self.normalize_stats(self.rostered)
        self.taken_averaged = self.get_average_stats(self.taken)
        self.normalize_stats(self.rostered)
        self.normalize_stats(self.free_agents)
        self.normalize_stats(self.taken)

        self.skater_projections = self.load_skater_projections()
        self.goalie_projections = self.load_goalie_projections()
        self.logger.debug(f"Skater Projections: {self.skater_projections.head()}")
        self.logger.debug(f"Goalie Projections: {self.goalie_projections.head()}")

        self.master_player_rankings = PlayerRankings()

        ranked_rostered = self.calculate_player_rankings(self.rostered)
        ranked_free_agents = self.calculate_player_rankings(self.free_agents)
        ranked_taken = self.calculate_player_rankings(self.taken)

        master_ranks = self.master_player_rankings.get_by_time_period(self.time_periods[2], location=constants.LOCATION_ROSTER)
        # master_ranks = self.master_player_rankings.get_rankings_by_position(["LW"], self.time_periods[0], location=constants.LOCATION_FREE_AGENT)
        for idx, player in enumerate(master_ranks):
            logging.info(f"{idx + 1}: {player.name} - {player.rankings[self.time_periods[0]]['weighted_score']}")
            if idx > 5:
                break
        logging.info("--------------------------------")

    def load_skater_projections(self):
        try:
            data = pd.read_csv(os.path.join(os.path.dirname(__file__), "projections/skater_projections.csv"))
            logging.info("Skater projections loaded successfully.")
            sorted_data = data.sort_values(by="Rank", ascending=True)
            return sorted_data
        except Exception as e:
            logging.error(f"An error occurred while loading the file: {e}")

    def load_goalie_projections(self):
        try:
            data = pd.read_csv(os.path.join(os.path.dirname(__file__), "projections/goalie_projections.csv"))
            logging.info("Goalie projections loaded successfully.")
            sorted_data = data.sort_values(by="Rank", ascending=True)
            return sorted_data
        except Exception as e:
            logging.error(f"An error occurred while loading the file: {e}")

    def get_average_stats(self, players_to_average):
        # Initialize dictionaries to store totals and counts
        totals = {role: {period: {} for period in self.time_periods} for role in ["goalies", "skaters"]}
        counts = {role: {period: {} for period in self.time_periods} for role in ["goalies", "skaters"]}

        # Iterate through each player to populate totals and counts
        for player in players_to_average.values():
            role = "goalies" if player.is_goalie else "skaters"
            categories = self.goalie_categories if role == "goalies" else self.skater_categories

            for period in self.time_periods:
                if period in player.stats:
                    for stat, value in player.stats[period].items():
                        if stat in categories:
                            if stat not in totals[role][period]:
                                totals[role][period][stat] = 0
                                counts[role][period][stat] = 0
                            try:
                                totals[role][period][stat] += value
                                counts[role][period][stat] += 1
                            except Exception as e:
                                logging.debug(f"Error adding {value} to {stat} for {player.name} in {period}: {e}")

        # Calculate averages
        averages = {role: {period: {} for period in self.time_periods} for role in ["goalies", "skaters"]}
        for role in totals:
            for period in totals[role]:
                for stat in totals[role][period]:
                    if counts[role][period][stat] > 0:  # Avoid division by zero
                        averages[role][period][stat] = totals[role][period][stat] / counts[role][period][stat]

        return averages

    def normalize_stats(self, players):
        # Initialize the normalized stats dictionary
        normalized_players = {}

        # Global stat max and min dictionaries
        global_thresholds = {period: {"max": {}, "min": {}} for period in self.time_periods}

        # Debugging: Check initial data stats
        for name, player in players.items():
            for time_frame in self.time_periods:
                time_frame_stats = player.stats.get(time_frame, {})

        # Iterate through each player and timeframe to update global max/min
        for name, player in self.taken.items():
            for time_frame, time_frame_stats in player.stats.items():
                for stat, value in time_frame_stats.items():
                    # Convert string numbers to floats if necessary
                    if isinstance(value, str):
                        value = float(value) if value.replace(".", "", 1).isdigit() else 0
                    # Initialize or update global max and min for each timeframe
                    if stat not in global_thresholds[time_frame]["max"] or value > global_thresholds[time_frame]["max"][stat]:
                        global_thresholds[time_frame]["max"][stat] = value
                    if stat not in global_thresholds[time_frame]["min"] or value < global_thresholds[time_frame]["min"][stat]:
                        global_thresholds[time_frame]["min"][stat] = value

        logging.debug(f"Global Thresholds: {global_thresholds}")
        # Normalize stats using global max and min
        for name, player in players.items():
            for time_frame in self.time_periods:
                player_normalized_stats = {}

                time_frame_stats = player.stats.get(time_frame, {})
                normalized_stats = {}
                for stat, value in time_frame_stats.items():
                    value = float(value) if isinstance(value, str) and value.replace(".", "", 1).isdigit() else 0
                    max_val = global_thresholds[time_frame]["max"][stat]
                    min_val = global_thresholds[time_frame]["min"][stat]
                    if max_val == min_val:
                        normalized_stats[stat] = 1  # Handle the case where all values are the same
                    else:
                        normalized_stats[stat] = (value - min_val) / (max_val - min_val)

            player_normalized_stats[time_frame] = normalized_stats

            normalized_players[name] = player_normalized_stats
        # Normalize each player's stats
        for name, player in players.items():
            normalized_players[name] = {}
            player.normalized_stats = {}
            for time_frame, stats in player.stats.items():
                player.normalized_stats[time_frame] = {}
                normalized_players[name][time_frame] = {}
                for stat, value in stats.items():
                    # Calculate normalized value
                    max_val = global_thresholds[time_frame]["max"][stat]
                    min_val = global_thresholds[time_frame]["min"][stat]
                    if isinstance(value, str):
                        value = float(value) if value.replace(".", "", 1).isdigit() else 0
                    if max_val > min_val:
                        normalized_value = round((value - min_val) / (max_val - min_val), 2)
                        if stat in self.inverse_league_stats and player.is_goalie:
                            normalized_value = 1 - normalized_value
                    else:
                        normalized_value = 0  # Avoid division by zero if max equals min
                    normalized_players[name][time_frame][stat] = normalized_value

                player.normalized_stats[time_frame] = normalized_players[name][time_frame]
            # Log the normalized stats for debugging
            logging.debug(f"Normalized Players: {normalized_players}")
        return normalized_players

    def get_stats_for_league(self, location="taken", position=None):
        location_details = location
        if location == "taken":
            player_list = self.players["taken"]
        elif location == "free_agents":
            if position == "G":
                player_list = [player for player in self.players["free_agents"] if player.is_goalie]
            else:
                player_list = [player for player in self.players["free_agents"] if not player.is_goalie]
        elif location == "roster":
            player_list = self.roster.players
        else:
            logging.error(f"Invalid location to get stats for: {location}")
            return {}
        logging.info("Starting to fetch stats for all valid time frames.")
        # Collect player IDs for the API call
        logging.debug(f"Player List: {player_list}")
        player_ids = [player.player_id for player in player_list]

        player_details = self.players_details[location_details]

        # Dictionary to hold stats per time frame
        player_stats_dict = {}
        # Loop through each time frame and fetch stats
        for player in tqdm(player_list, desc="Fetching player stats for each player.."):
            for i in player_details:
                fetched_player_id = str(i["player_id"])
                if fetched_player_id == str(player.player_id):
                    # Found the player, break out of the loop
                    break

            player_stats_dict[player.name] = player
        for time_frame in tqdm(self.time_periods, desc="Fetching player stats for each time frame.."):
            player_stats = self.league.player_stats(player_ids, req_type=time_frame)
            for stat in player_stats:
                cleaned_stats = {k: v for k, v in stat.items() if k != "player_id" and k != "name" and k != "position_type"}
                logging.debug(f"Stats for Player ID {stat['player_id']} during {time_frame}: {cleaned_stats}")
                player_stats_dict[stat["name"]].stats[time_frame] = cleaned_stats

        logging.info("Player stats for all time frames updated successfully in self.league_stats")
        logging.debug(f"League stats: {player_stats_dict}")
        return player_stats_dict

    def calculate_player_rankings(self, players):
        logging.info(f"Getting rankings for {len(players)} players")
        ranked_players = []
        for name, player in tqdm(players.items(), desc="Calculating player rankings.."):
            if player.is_goalie:
                player_rank = self.goalie_projections.loc[self.goalie_projections["player"] == name, "Rank"]
            else:
                player_rank = self.skater_projections.loc[self.skater_projections["Player"] == name, "Rank"]
            projected_rank = float("inf")
            if not player_rank.empty:
                projected_rank = int(player_rank.iloc[0])

            player.rankings = {period: {} for period in self.time_periods}
            for time_frame, stats in player.normalized_stats.items():
                categories = self.goalie_categories if player.is_goalie else self.skater_categories

                category_score = sum(value for stat, value in stats.items() if stat in categories)

                max_rank = len(self.skater_projections) if not player.is_goalie else len(self.goalie_projections)

                normalized_rank = 1 - (projected_rank / max_rank) if projected_rank != float("inf") else 0
                weighted_score = category_score * self.score_weight + normalized_rank * self.projection_weight
                player.rankings[time_frame] = {
                    "score": weighted_score,
                    "projected_rank": projected_rank,
                    "weighted_score": weighted_score,
                }
                ranked_players.append(player)
                self.master_player_rankings.add_player(player)

        return ranked_players


class PlayerRankings:
    def __init__(self):
        self.players = []

    def add_player(self, player):
        if player not in self.players:
            self.players.append(player)

    def evaluate_all_players(self):
        for player in self.players:
            player.evaluate_player(no_log=True)

    def get_by_time_period(self, time_frame, location="all"):
        filtered_players = self.players if location == "all" else [p for p in self.players if p.location == location]
        return sorted(filtered_players, key=lambda x: x.rankings[time_frame]["weighted_score"], reverse=True)

    def get_rankings_by_position(self, positions, time_frame, location="all"):
        filtered_players = [p for p in self.players if any(pos in p.eligible_positions for pos in positions) and (location == "all" or p.location == location)]
        return sorted(filtered_players, key=lambda x: x.rankings[time_frame]["weighted_score"], reverse=True)

    def get_average_weighted_score(self, time_frame):
        return sum(player.rankings[time_frame]["weighted_score"] for player in self.players) / len(self.players)

    def get_weighted_score_statistics(self, time_frame):
        scores = [player.rankings[time_frame]["weighted_score"] for player in self.players]

        # Calculate average
        average = sum(scores) / len(scores) if scores else 0

        # Calculate percentiles
        percentiles = {
            "95th": np.percentile(scores, 95),
            "90th": np.percentile(scores, 90),
            "80th": np.percentile(scores, 80),
            "70th": np.percentile(scores, 70),
            "60th": np.percentile(scores, 60),
            "50th": np.percentile(scores, 50),
            "40th": np.percentile(scores, 40),
            "30th": np.percentile(scores, 30),
            "20th": np.percentile(scores, 20),
            "10th": np.percentile(scores, 10),
            "5th": np.percentile(scores, 5),
        }

        return {"average": average, "percentiles": percentiles}
