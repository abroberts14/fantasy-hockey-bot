import logging
from itertools import combinations
import itertools
from tqdm import tqdm
from stats import LeagueStatistics


class RosterLineup:
    def __init__(self, league, players, lineup=None):
        self.logger = logging.getLogger(__name__)
        self.league = league
        self.roster = players
        self.lineup = {}

        if lineup is None:
            self.initialize_lineup()
        else:
            self.lineup = lineup

    def initialize_lineup(self):
        self.lineup = {}
        for player in tqdm(self.roster, desc="Initializing lineup.."):
            if player.position not in self.lineup:
                self.lineup[player.position] = []
            self.lineup[player.position].append(player)

    # TODO: Update this to use the player.roster
    # Use league_settings.required_roster_spots and  league_positions to find best lineup

    def calculate_best_lineup(self):
        logging.info(f"Calculating best lineup with {len(self.roster)} players")

        # Create a dictionary mapping positions to eligible players
        position_to_players = {}
        for pos, count in tqdm(self.league.league_positions.items(), desc="Fetching eligible players for each position.."):
            if pos in self.league.inactive_positions:
                continue
            eligible_players = [player for player in self.roster if pos in player.eligible_positions and player.position not in self.league.inactive_positions]
            if eligible_players:
                position_to_players[pos] = eligible_players
        logging.info(f"Position to players: {position_to_players}")

        # Generate all possible lineups based on position requirements
        best_lineup = None
        max_score = 0
        lineups_attempted = 0

        def generate_lineups():
            # Helper function to generate all valid combinations
            all_lineups = []
            for pos, info in tqdm(self.league.league_positions.items(), desc="Generating all valid combinations for a valid lineup.."):
                count = info["count"]

                if pos in position_to_players:
                    players = position_to_players[pos]
                    if count > 1:
                        # Generate combinations for positions requiring multiple players
                        all_lineups.append(list(combinations(players, count)))
                    else:
                        # Single player for this position
                        all_lineups.append([(player,) for player in players])
            return itertools.product(*all_lineups)

        for lineup in tqdm(generate_lineups(), desc="Finding the best possible lineup.."):
            # Flatten the lineup and calculate its score
            flat_lineup = [player for pos in lineup for player in pos]
            if len(set(flat_lineup)) != len(flat_lineup):
                # Skip invalid lineups with duplicate players
                continue

            score = 0
            for player in flat_lineup:
                if player.game_today:
                    if player.must_start:
                        # Use the higher of the two scores (season vs last week)
                        try:
                            weighted_score = max(
                                player.rankings[self.league.time_periods[2]]["weighted_score"],  # Season
                                player.rankings[self.league.time_periods[0]]["weighted_score"],  # Last week
                                player.unified_score,
                            )
                        except Exception as e:
                            weighted_score = 0.01
                    else:
                        # Default to season score
                        weighted_score = max(player.unified_score, 0.01)
                    score += weighted_score

            lineups_attempted += 1
            if score > max_score:
                max_score = score
                best_lineup = lineup

        logging.debug(f"Lineups attempted: {lineups_attempted}")
        logging.debug(f"Best lineup: {best_lineup}")

        # Format the best lineup for output
        formatted_lineup = {}
        temp_lineup = []

        if best_lineup is None:
            logging.error("No best lineup found")
            return

        for pos, players in tqdm(zip(self.league.league_positions.keys(), best_lineup), desc="Setting bench players.."):
            temp_lineup.extend(players)
            formatted_lineup[pos] = players
        formatted_lineup["BN"] = []
        for player in self.roster:
            if player not in temp_lineup:
                if player.position not in self.league.inactive_positions:
                    formatted_lineup["BN"].append(player)
                else:
                    logging.info(f"Skipping {player.name} because they are on the inactive list")
        self.lineup = formatted_lineup
        return formatted_lineup

    def log_lineup(self):
        if not self.lineup:
            logging.info("Lineup is not set.")
            return
        for position, players in self.lineup.items():
            for player in players:
                try:
                    weighted_score_lastweek = round(player.rankings[self.league.time_periods[0]]["weighted_score"], 4)
                    weighted_score_season = round(player.rankings[self.league.time_periods[2]]["weighted_score"], 4)

                except Exception as e:
                    logging.error(f"Error getting weighted score for {player.name}: {e}")
                    weighted_score_lastweek = -1
                    weighted_score_season = -1
                starred = "(*)" if player.must_start else ""
                if player.is_goalie:
                    logging.info(
                        f"{position}: {player.name} {starred} (Elig Pos: {', '.join(player.eligible_positions)}) "
                        f"- [Weighted Score: {weighted_score_lastweek} | {weighted_score_season}] [Score: {player.unified_score} ]  [Projected Rank: {player.rankings[self.league.time_periods[0]]['projected_rank']} | {player.rankings[self.league.time_periods[2]]['projected_rank']}] - Game Today: {player.game_today} | Starting Behind Net: {player.starting_behind_net}"
                    )
                else:
                    logging.info(
                        f"{position}: {player.name} {starred} (Elig Pos: {', '.join(player.eligible_positions)}) "
                        f"- [Weighted Score: {weighted_score_lastweek} | {weighted_score_season}] [Score: {player.unified_score} ]  [Projected Rank: {player.rankings[self.league.time_periods[0]]['projected_rank']} | {player.rankings[self.league.time_periods[2]]['projected_rank']}] - Game Today: {player.game_today}"
                    )

    def __repr__(self):
        return f"RosterLineup(lineup={self.lineup})"
