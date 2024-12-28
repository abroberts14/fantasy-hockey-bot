import os
import cache
import logging
from datetime import datetime
from player import Player
from util import constants

from tqdm import tqdm


class League:
    def __init__(self, yahoo_api, league_key, team_key, nhl):
        self.logger = logging.getLogger(__name__)
        self.yahoo_api = yahoo_api
        self.league = self.yahoo_api.league
        self.today = datetime.now().date()
        self.league_key = league_key
        self.team_key = team_key
        self.league_positions = self.league.positions()
        self.league_settings = self.league.settings()
        self.max_moves = self.league_settings["max_weekly_adds"]
        self.league_categories = self.league.stat_categories()
        self.inverse_league_stats = ["L", "GA", "GAA"]
        self.nhl = nhl
        self.skater_categories = [cat["display_name"] for cat in self.league_categories if cat["position_type"] == "P"]
        self.goalie_categories = [cat["display_name"] for cat in self.league_categories if cat["position_type"] == "G"]
        self.average_weighted_scores = {}
        self.inactive_positions = ["IR+", "IL", "NA", "IR", "IR-LT"]
        self.not_playing_statuses = ["DTD", "O", "IR-LT"]

        self.time_periods = ["lastweek", "lastmonth", "season"]
        self.team_data = self.league.teams()[self.team_key]

        self.required_roster_spots = self.get_required_roster_spots()

        self.last_week_weight = 0.55
        self.last_month_weight = 0.5
        self.season_weight = 0.45
        self.projected_rank_weight = 0.35
        self.percent_owned_weight = 0.2
        self.player_statistics = None

        self.players_details = {"taken": [], "free_agents": [], "roster": []}
        self.players = {"taken": [], "free_agents": []}
        self.initialize_players()

        self.logger.info(f"Loaded {len(self.players['taken'])} taken players")
        self.logger.info(f"Loaded {len(self.players['free_agents'])} free agents")

    def initialize_players(self):
        if os.environ.get("CACHE_ENABLED", False) == "True":
            self.players["taken"] = cache.load_object("taken") or self.fetch_players_raw(location="taken")
            cache.save_object(self.players["taken"], "taken")
            fa_skaters = cache.load_object("free_agents_skaters") or self.fetch_players_raw(location="free_agents")
            fa_goalies = cache.load_object("free_agents_goalies") or self.fetch_players_raw(location="free_agents_goalies")
            cache.save_object(fa_skaters, "free_agents_skaters")
            cache.save_object(fa_goalies, "free_agents_goalies")

            self.players["free_agents"].extend(fa_skaters)
            self.players["free_agents"].extend(fa_goalies)
        else:
            self.players["taken"] = self.fetch_players_raw(location="taken")
            self.players["free_agents"].extend(self.fetch_players_raw(location="free_agents"))
            self.players["free_agents"].extend(self.fetch_players_raw(location="free_agents_goalies"))

    def fetch_players_raw(self, location="taken"):
        self.logger.info(f"Fetching {location} players from Yahoo API")
        players = []
        if location == "taken":
            raw_taken_players = self.league.taken_players()
            for index, p in enumerate(tqdm(raw_taken_players, desc="Fetching taken players..")):
                player = Player(p, self)
                player.location = constants.LOCATION_TAKEN
                players.append(player)
            self.players_details["taken"] = self.get_players_details(players)

            return players
        elif location == "free_agents":
            raw_free_agents = self.league.free_agents(position="P")
            for index, p in enumerate(tqdm(raw_free_agents, desc="Fetching free agents skaters..")):
                player = Player(p, self)
                player.location = constants.LOCATION_FREE_AGENT
                players.append(player)
            self.players_details["free_agents_skaters"] = self.get_players_details(players)
            return players
        elif location == "free_agents_goalies":
            raw_free_agents_goalies = self.league.free_agents(position="G")
            for index, p in enumerate(tqdm(raw_free_agents_goalies, desc="Fetching free agents goalies..")):
                player = Player(p, self)
                player.location = constants.LOCATION_FREE_AGENT
                players.append(player)
            self.players_details["free_agents_goalies"] = self.get_players_details(players)
            return players
        else:
            return []

    def get_players_details(self, players):
        player_ids = [player.player_id for player in players]
        roster_details = self.yahoo_api.league.player_details(player_ids)
        player_teams = {int(detail["player_id"]): detail["editorial_team_full_name"] for detail in roster_details}
        for player in tqdm(players, desc="Fetching additional player details.."):
            if player.player_id in player_teams:
                player.team = player_teams[player.player_id]
                player.game_today = self.nhl.teams_playing.get(player.team, False)
        return roster_details

    def update_player_rankings(self, players, evaluate=False):
        for player in tqdm(players, desc="Updating player rankings.."):
            p = next((p for p in self.player_statistics.master_player_rankings.players if p.name == player.name), None)
            if p:
                player.rankings = p.rankings
                if evaluate:
                    player.evaluate_player()

        pass

    def get_required_roster_spots(self):
        required_total = sum(
            int(pos_info["count"])
            for pos, pos_info in self.league_positions.items()
            if pos not in self.inactive_positions  # Exclude IR slots from the count
        )
        return required_total

    def rank_players_in_league(self):
        # Provides a ranking of all players in the league
        pass
