#!/usr/bin/env python


import logging
from league import League
import yahoo.api as api
import os
from roster import Roster
from nhl import NHL
import cache
from stats import LeagueStatistics
import datetime

logging.basicConfig(
    level=logging.INFO,
    # format="%(asctime)s - %(levelname)s: %(message)s",
    format="%(levelname)s: %(message)s",
    datefmt="%m/%d/%Y %I:%M:%S %p",
)


class Manager:
    def __init__(self, yahoo_api):
        self.cache = True
        # os.environ["CACHE_ENABLED"] = str(self.cache)

        self.logger = logging.getLogger(__name__)
        self.yahoo_api = yahoo_api
        league = self.yahoo_api.league
        league_key = self.yahoo_api.league_key
        team_key = self.yahoo_api.team_key

        if self.cache:
            self.logger.info("Loading or fetching NHL objects...")
            nhl = cache.load_object("nhl") or NHL()
            cache.save_object(nhl, "nhl")

            self.league = cache.load_object("league") or League(self.yahoo_api, league_key, team_key, nhl)
            self.roster = cache.load_object("roster") or Roster(self.yahoo_api, self.league)

            league_player_statistics = LeagueStatistics(self.yahoo_api, league_key, team_key, self.league.nhl, self.roster)
            self.league.player_statistics = league_player_statistics

        else:
            nhl = NHL()
            self.league = League(self.yahoo_api, league_key, team_key, nhl)
            self.roster = Roster(self.yahoo_api, self.league)
            league_player_statistics = LeagueStatistics(self.yahoo_api, league_key, team_key, self.league.nhl, self.roster)
            self.league.player_statistics = league_player_statistics

        for time_period in self.league.time_periods:
            self.league.average_weighted_scores[time_period] = self.league.player_statistics.master_player_rankings.get_weighted_score_statistics(time_period)

        self.sync_roster_and_league()
        self.league.player_statistics.master_player_rankings.evaluate_all_players()

        self.logger.info(f"Taken Players: {len(self.league.players['taken'])}")
        self.league.update_player_rankings(self.roster.players, evaluate=True)
        self.league.update_player_rankings(self.league.players["taken"])
        self.league.update_player_rankings(self.league.players["free_agents"])
        self.logger.info(f"Average Weighted Scores: {self.league.average_weighted_scores}")
        for index, player in enumerate(self.league.players["taken"]):
            self.logger.info(f"{player}")
            if index > 3:
                break
        self.logger.info(f"Free Agents: {len(self.league.players['free_agents'])}")
        for index, player in enumerate(self.league.players["free_agents"]):
            self.logger.info(f"{player}")
            if index > 3:
                break
        self.logger.info(f"Rostered: {len(self.roster.players)}")
        for index, player in enumerate(self.roster.players):
            self.logger.info(f"{player}")
            if index > 3:
                break

        # cache.save_object(self.league, "league")
        # cache.save_object(self.roster, "roster")

        # self.roster.set_lineup()

        self.roster.move_player_to_bench_from_inactive()
        self.roster.move_injured_players_to_inactive()

        self.roster.set_lineup()
        # if len(self.roster.change_position_payload) > 0:
        #     self.logger.info(f"Applying lineup changes for injured players: {len(self.roster.change_position_payload)}")
        #     self.roster.apply_lineup_changes()
        #     self.roster.get_roster()

        # self.roster.set_lineup()

        # free_agents = self.roster.find_free_agents_by_positions(["C", "LW", "RW", "D"])
        # self.logger.info(f"Free Agents: {len(free_agents)}")
        # for player in free_agents:
        #     self.logger.info(f"{player}")

        # potential_players_to_drop = self.roster.find_potential_players_to_drop()
        # self.logger.info(f"Potential Players to Drop: {len(potential_players_to_drop)}")
        # transactions = []
        # if self.enough_moves_left():
        #     for player, score in potential_players_to_drop:
        #         self.logger.info(f"Looking for potential replacements for {player}")
        #         fa = self.roster.find_replacement_players(player)
        #         if fa:
        #             for free_agent, free_agent_score in fa:
        #                 transactions.append({"drop": player, "add": free_agent, "score": score - free_agent_score})

        #     sorted_transactions = sorted(transactions, key=lambda x: x["score"], reverse=True)

        #     suggested_moves = self.get_required_moves_based_on_day()

        #     for transaction in sorted_transactions:
        #         suggested_thershold = transaction["score"] + suggested_moves
        #         if suggested_thershold >= 4:
        #             self.logger.info(f"Adding {transaction['add']} and dropping {transaction['drop']} - Current Moves Left: {self.roster.moves_left}")
        #             self.logger.info(f"{transaction}")

        #             self.roster.add_and_drop_player(transaction["add"], transaction["drop"])
        #             self.sync_roster()
        #             self.logger.info(f"Successfully added and dropped players. Current Moves Left: {self.roster.moves_left}")

        #             break

        # lineup = RosterLineup(self.league)
        # lineup.calculate_best_lineup()
        # lineup.log_lineup()
        # self.roster.lineup = lineup.lineup

    def get_best_lineup(self):
        self.roster.lineup.calculate_best_lineup()

    def add_free_agents_if_roster_spot_available(self):
        free_agents = self.roster.find_free_agents_by_positions(["C", "LW", "RW", "D"])
        self.logger.info(f"Free Agents: {len(free_agents)}")
        for player in free_agents:
            self.logger.info(f"{player}")

    def enough_moves_left(self):
        return self.roster.moves_left >= self.get_required_moves_based_on_day()

    def get_required_moves_based_on_day(self):
        day_thresholds = {"Monday": 3, "Tuesday": 3, "Wednesday": 2, "Thursday": 2, "Friday": 1, "Saturday": 1, "Sunday": 1}
        current_day = datetime.datetime.now().strftime("%A")
        required_moves = day_thresholds[current_day]
        return required_moves

    def sync_roster(self):
        self.logger.info(f"Syncing roster. Current Moves Left: {self.roster.moves_left}")
        self.roster = Roster(self.yahoo_api, self.league)
        if self.cache:
            cache.save_object(self.roster, "roster")
        self.logger.info(f"Synced roster. Current Moves Left: {self.roster.moves_left}")

    def sync_roster_and_league(self):
        """Update all player objects with the current league reference"""
        for player in self.roster.players:
            player.league = self.league
        for player in self.league.players["taken"]:
            player.league = self.league
        for player in self.league.players["free_agents"]:
            player.league = self.league
        for player in self.league.player_statistics.master_player_rankings.players:
            player.league = self.league
        self.roster.league = self.league


if __name__ == "__main__":
    yahoo_api = api.YahooApi(os.path.dirname(os.path.realpath(__file__)))
    manager = Manager(yahoo_api)
