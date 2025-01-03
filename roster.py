import logging
from lineup import RosterLineup
from player import Player
from util import constants
from stats import LeagueStatistics
from tqdm import tqdm
import datetime


class Roster:
    def __init__(self, yahoo_api, league):
        self.logger = logging.getLogger(__name__)
        self.yahoo_api = yahoo_api
        self.league = league
        self.players = None
        self.teams_playing = None
        self.moves_left = None
        self.change_position_payload = []

        self.get_roster()

    def update_roster_info(self):
        self.moves_left = int(self.league.max_moves) - int(self.league.team_data["roster_adds"]["value"])
        required_total = self.league.required_roster_spots
        number_of_active_players = len(self.get_active_players())
        self.logger.info(f"Required roster spots: {required_total}")
        self.logger.info(f"Number of active players: {number_of_active_players}")
        self.open_roster_spots = required_total - number_of_active_players
        self.logger.info(f"Moves left: {self.moves_left}")
        self.logger.info(f"Roster full: {self.is_full()}")
        self.logger.info(f"Open roster spots: {self.open_roster_spots}")

    def get_roster(self):
        lineups = {}
        team = []
        roster = self.yahoo_api.get_roster()

        for player in tqdm(roster, desc="Fetching current roster from yahoo.."):
            p = Player(player, self.league)
            p.location = constants.LOCATION_ROSTER
            team.append(p)
            if p.position not in lineups:
                lineups[p.position] = []
            lineups[p.position].append(p)

        self.league.players_details["roster"] = self.league.get_players_details(team)
        self.players = team

        self.update_roster_info()
        return team

    def get_active_players(self):
        """
        Returns a list of active players on the current roster
        """
        active_players = []
        for player in tqdm(self.players, desc="Determining active players on roster.."):
            if player.position not in self.league.inactive_positions:
                active_players.append(player)
        return active_players

    def is_full(self):
        """Check if the roster meets or exceeds the league position requirements."""
        return len(self.get_active_players()) >= self.league.required_roster_spots

    def set_lineup(self):
        self.lineup = RosterLineup(self.league, self.players)

        self.lineup.calculate_best_lineup()
        self.lineup.log_lineup()
        for position, players in self.lineup.lineup.items():
            for player in players:
                self.logger.info(f"{position} - {player.name}")
                self.add_lineup_change(player.player_id, position)
        if len(self.change_position_payload) > 0:
            self.logger.info(f"Applying lineup changes: {len(self.change_position_payload)}")
            self.apply_lineup_changes()
            self.lineup.log_lineup()

    def move_player_to_bench_from_inactive(self):
        """
        Moves any plays that are listed as active but are positioned as inactive to the bench from the inactive list
        """
        for player in self.players:
            if player.position in self.league.inactive_positions:
                self.logger.info(f"Player {player.name} is in the inactive list: {player.eligible_positions}")
                if not player.has_inactive_position:
                    if not self.is_full():
                        self.logger.info(f"Removing {player.name} from injured list and adding to bench")
                        self.add_roster_change(player.player_id, "BN")
                        self.lineup["BN"].append(player)
                    else:
                        self.logger.info(f"Roster is full, skipping {player.name}")

    def move_injured_players_to_inactive(self):
        """
        Moves any plays that are listed as inactive but are positioned on the active roster to the injured list
        """
        self.logger.info(f"Roster open spots: {self.open_roster_spots}")
        open_positions = self.get_open_roster_positions()
        self.logger.info(f"Open positions: {open_positions}")
        ir_spots = open_positions.get("IR", 0)
        ir_plus_spots = open_positions.get("IR+", 0)
        self.logger.info(f"Injured open spots: {ir_spots + ir_plus_spots}")
        if ir_spots + ir_plus_spots <= 0:
            self.logger.info("No IR or NA spots available, skipping")
            return

        for player in self.players:
            if player.has_inactive_position and player.status != "DTD":
                self.logger.info(f"Player {player.name} is in the inactive list: {player.eligible_positions}")
                if not player.is_rostered_as_inactive:
                    self.logger.info(f"Player {player.name} is not rostered as inactive: {player.is_rostered_as_inactive}")
                    get_inactive_position = next((pos for pos in self.league.inactive_positions if pos in player.eligible_positions), None)
                    self.logger.info(f"Getting inactive position: {get_inactive_position}")
                    open_ir_spots = open_positions.get(get_inactive_position, 0)
                    self.logger.info(f"Open IR spots: {open_ir_spots}")
                    if open_ir_spots > 0:
                        self.add_lineup_change(player.player_id, get_inactive_position)
                        open_positions[get_inactive_position] -= 1
                        self.logger.info(f"Open IR spots: {open_ir_spots}")
                    else:
                        self.logger.info(f"No {get_inactive_position} spots available, skipping {player.name}")
        self.logger.info(f"Payload: {self.change_position_payload}")
        self.apply_lineup_changes()

    def get_open_roster_positions(self):
        required_positions = self.league.league_positions
        logging.debug("Checking open roster positions...")
        self.logger.info(f"Required positions: {required_positions}")

        # Initialize required positions dictionary with all positions
        required_inactive_positions = {pos: data["count"] for pos, data in required_positions.items()}
        # Combine IR and IR+ counts
        if "IR" in required_inactive_positions and "IR+" in required_inactive_positions:
            required_inactive_positions["IR+"] += required_inactive_positions.pop("IR")

        # Initialize counts for all positions
        roster_positions = {pos: 0 for pos in required_inactive_positions}
        # Count current roster positions
        for player in self.players:
            position = player.position
            if position in roster_positions:
                roster_positions[position] += 1

        self.logger.info(f"Roster positions: {roster_positions}")
        # Calculate the remaining open positions
        open_positions = {pos: required_inactive_positions[pos] - count for pos, count in roster_positions.items()}

        return open_positions

    def add_lineup_change(self, player_id, position):
        self.change_position_payload.append({"player_id": player_id, "selected_position": position})

    def apply_lineup_changes(self):
        if len(self.change_position_payload) > 0:
            self.logger.info(f"Applying lineup changes: {self.change_position_payload}")
            self.yahoo_api.team.change_positions(datetime.datetime.now(), self.change_position_payload)
            self.change_position_payload = []
            self.get_roster()

    def add_and_drop_player(self, player_to_add, player_to_drop):
        if player_to_drop:
            self.yahoo_api.team.add_and_drop_players(player_to_add.player_id, player_to_drop.player_id)
        else:
            self.yahoo_api.team.add_player(player_to_add.player_id)
        self.get_roster()

    def find_free_agents_by_positions(self, positions, playing_today=False):
        free_agents = []
        for player in self.league.players["free_agents"]:
            if any(pos in player.eligible_positions for pos in positions):
                if player.percent_owned > 15:
                    free_agents.append(player)

        filtered_free_agents = []
        self.logger.info(f"Free agents: {len(free_agents)} for positions: {positions}")
        # sort by rankings for lastweek
        free_agents.sort(key=lambda x: x.rankings[self.league.time_periods[0]]["weighted_score"], reverse=True)
        for free_agent in free_agents:
            projected_rank = free_agent.rankings[self.league.time_periods[2]]["projected_rank"]
            projected_rank_adjusted = projected_rank / 1000
            last_week_adjusted = free_agent.rankings[self.league.time_periods[0]]["weighted_score"] - projected_rank_adjusted
            season_adjusted = free_agent.rankings[self.league.time_periods[2]]["weighted_score"] - projected_rank_adjusted
            is_goalie = "G" in free_agent.eligible_positions
            if playing_today or is_goalie:
                if is_goalie:
                    if free_agent.starting_behind_net:
                        filtered_free_agents.append(free_agent)
                else:
                    if free_agent.game_today:
                        filtered_free_agents.append(free_agent)
            else:
                filtered_free_agents.append(free_agent)
        return filtered_free_agents[:7]

    def find_replacement_players(self, player):
        potential_player_last_week_rank = player.rankings[self.league.time_periods[0]]["weighted_score"]
        potential_player_season_rank = player.rankings[self.league.time_periods[2]]["weighted_score"]
        potential_player_projected_rank = player.rankings[self.league.time_periods[2]]["projected_rank"]
        potential_player_rank_score = potential_player_last_week_rank + potential_player_season_rank
        self.logger.debug(
            f"Looking for replacement for [{player.name} - {potential_player_projected_rank}]  [{potential_player_last_week_rank} | {potential_player_season_rank}]"
        )
        positions_without_util = [pos for pos in player.eligible_positions if pos != "Util" and pos not in self.league.inactive_positions]
        free_agents = self.find_free_agents_by_positions(positions_without_util)
        res = []
        for free_agent in free_agents:
            fa_last_week_rank = free_agent.rankings[self.league.time_periods[0]]["weighted_score"]
            fa_season_rank = free_agent.rankings[self.league.time_periods[2]]["weighted_score"]
            fa_projected_rank = free_agent.rankings[self.league.time_periods[2]]["projected_rank"]
            fa_rank_score = fa_last_week_rank + fa_season_rank

            fa_rank_score_adjusted = fa_rank_score - fa_projected_rank / 1000
            potential_player_rank_score_adjusted = potential_player_rank_score - potential_player_projected_rank / 1000
            self.logger.debug(f"[{free_agent.name}] [{fa_last_week_rank} | {fa_season_rank}] - Proj: [{fa_projected_rank}]")

            if fa_rank_score > potential_player_rank_score:
                add_score = self.__evaluate_player__(free_agent, is_drop=False)
                self.logger.debug(f"Add Score: {add_score}")
                if add_score >= 0:
                    self.logger.info(
                        f"[{free_agent.name}] Last Week Score: {fa_last_week_rank} | Season Score: {fa_season_rank} | Projected Rank: {fa_projected_rank}"
                    )
                    self.logger.info(
                        f"[{player.name}] Last Week Score: {potential_player_last_week_rank} | Season Score: {potential_player_season_rank} | Projected Rank: {potential_player_projected_rank}"
                    )
                    self.logger.info(f"Potential replacement: {free_agent.name} and dropping {player.name} to lineup")
                    res.append((free_agent, add_score))

        return res
        # fa_projected_rank_adjusted = fa_projected_rank / 1000
        # fa_last_week_adjusted = fa_last_week_rank - fa_projected_rank_adjusted
        # fa_season_adjusted = fa_season_rank - fa_projected_rank_adjusted

    def find_potential_players_to_drop(self):
        res = []
        for player in self.players:
            if player.cant_cut:
                continue

            drop_score = self.__evaluate_player__(player)

            if drop_score >= 4:
                self.logger.info(f"Potential drop candidate: {player.name}")
                res.append((player, drop_score))

        # Sort by drop score, highest first
        res.sort(key=lambda x: x[1], reverse=True)
        return list(res)

    def add_best_free_agent(self):
        open_positions = self.get_open_roster_positions()
        find_players_playing_today = self.moves_left < 2
        # Check for specific position needs first
        position_priorities = ["G", "D"]
        free_agents = []
        for position in position_priorities:
            if open_positions.get(position, 0) > 0:
                self.logger.info(f"Adding best free agent for {position}")
                free_agents = self.find_free_agents_by_positions([position], find_players_playing_today)
                break

        # If no specific position needs, look for best available skater
        if len(free_agents) == 0:
            self.logger.info("Adding best free agent skater")
            free_agents = self.find_free_agents_by_positions(["C", "LW", "RW", "D"], find_players_playing_today)

        self.logger.info(f"Free Agents: {len(free_agents)}")
        for player in free_agents:
            self.add_and_drop_player(player, None)
            self.logger.info(f"{player.name} added to roster")
            return

    def __evaluate_player__(self, player, is_drop=True):
        last_week_score = player.rankings[self.league.time_periods[0]]["weighted_score"]
        season_score = player.rankings[self.league.time_periods[2]]["weighted_score"]
        projected_rank = player.rankings[self.league.time_periods[2]]["projected_rank"]
        owned_percentage = player.percent_owned

        self.logger.debug(f"\nEvaluating {player.name}:")
        self.logger.debug(f"  Base Stats:")
        self.logger.debug(f"    - Last Week Score: {last_week_score:.2f}")
        self.logger.debug(f"    - Season Score: {season_score:.2f}")
        self.logger.debug(f"    - Projected Rank: {projected_rank}")
        self.logger.debug(f"    - Ownership: {owned_percentage}%")
        player_score = 0
        reasons = []
        # Factor 1: Recent Performance vs Season Performance
        self.logger.debug(f"  Factor 1 - Recent vs Season Performance:")
        if last_week_score < (season_score * 0.7):
            player_score += 3
            reasons.append(f"❌ Recent performance ({last_week_score:.2f}) < 70% of season average ({season_score * 0.7:.2f}): +2 points")
        elif last_week_score < (season_score * 0.85):
            player_score += 1
            reasons.append(f"⚠️ Recent performance ({last_week_score:.2f}) < 85% of season average ({season_score * 0.85:.2f}): +1 point")
        else:
            if last_week_score > (season_score * 1.2) and season_score > 2:
                player_score -= 1
                reasons.append(f"🔥 Recent performance ({last_week_score:.2f}) > 120% of season average ({season_score * 1.2:.2f}): -1 point")
            else:
                reasons.append(f"✅ Recent performance stable")

        # Factor 2: Absolute (Recent) Performance Threshold
        self.logger.debug(f"  Factor 2 - Absolute (Recent) Performance:")
        if last_week_score < 1.5:
            player_score += 2
            reasons.append(f"❌ Very poor recent performance < 1.5: +2 points")
        elif last_week_score < 2.0:
            player_score += 1
            reasons.append(f"⚠️ Poor recent performance < 2.0: +1 point")
        else:
            if last_week_score > 2.5:
                player_score -= 1
                if not is_drop:
                    player_score -= 1
                reasons.append(f"🔥 Absolute (Recent) performance ({last_week_score:.2f}) > 2.75: -1 point")

            else:
                reasons.append(f"✅ Absolute (Recent) performance acceptable")

        # Factor 3: Absolute (Season) Performance Threshold
        self.logger.debug(f"  Factor 3 - Absolute (Season) Performance:")
        if season_score < 1.5:
            player_score += 2
            reasons.append(f"❌ Very poor season performance < 1.5: +2 points")
        elif season_score < 2.0:
            player_score += 1
            reasons.append(f"⚠️ Poor season performance < 2.0: +1 point")
        else:
            if season_score > 2.75:
                player_score -= 2
                reasons.append(f"🔥 Absolute (Season) performance ({season_score:.2f}) > 2.75: -1 point")
            elif season_score > 2.5:
                player_score -= 1
                reasons.append(f"🔥 Absolute (Season) performance ({season_score:.2f}) > 2.5: -1 point")
            else:
                reasons.append(f"✅ Absolute (Season) performance acceptable")

        # Factor 4: Ownership Percentage
        self.logger.debug(f"  Factor 4 - Ownership Percentage:")
        if owned_percentage < 20:
            player_score += 2
            reasons.append(f"❌ Very low ownership < 20%: +2 points")
        elif owned_percentage < 30:
            player_score += 1
            reasons.append(f"⚠️ Low ownership < 30%: +1 point")
        else:
            reasons.append(f"✅ Ownership acceptable")

        # Factor 5: Preseason Expectations vs Performance
        performance_vs_projection = (last_week_score + season_score) / 2
        self.logger.debug(f"  Factor 5 - Preseason Expectations Vs Performance:")
        self.logger.debug(f"    - Average Performance: {performance_vs_projection:.2f}")
        if projected_rank < 50:
            if performance_vs_projection < 2.3:
                player_score += 2
                reasons.append(f"❌ High draft pick ({projected_rank}) underperforming: +2 points")
            else:
                player_score -= 2
                reasons.append(f"🔥 High draft pick ({projected_rank}) meeting expectations: -2 points")
        elif projected_rank < 100:
            if performance_vs_projection < 2.3:
                player_score += 1
                reasons.append(f"⚠️ Medium draft pick ({projected_rank}) underperforming: +1 point")
            else:
                player_score -= 1
                reasons.append(f"🔥 Medium draft pick ({projected_rank}) meeting expectations: -1 point")
        else:
            reasons.append(f"✅ Meeting expectations or low draft pick")

        self.logger.debug(f"  Factor 6 - Preseason Projection:")
        if projected_rank > 200:
            player_score += 1
            reasons.append(f"❌ Extremely low projections ({projected_rank}): +1 point")
        else:
            reasons.append(f"✅ Projected rank is acceptable")

        self.logger.debug(f"  Final Player Score: {player_score}")
        if not is_drop:
            player_score = player_score * -1

        threshold = 4 if is_drop else 0
        if player_score >= threshold:
            self.logger.info(f"Candidate: {player.name} [{player_score}]")
            for reason in reasons:
                self.logger.info(f"- {reason}")
        return player_score

    def __repr__(self):
        return f"Roster(players={self.players})"
