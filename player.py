import logging


class Player:
    def __init__(self, player, league):
        self.logger = logging.getLogger(__name__)
        self.league = league
        self.data = self.build_player_data(player)
        self.player_id = self.data.get("player_id", -1)
        self.name = self.data["name"]
        self.position = self.data.get("selected_position", None)
        self.position_type = self.data.get("position_type", None)
        self.eligible_positions = self.data.get("eligible_positions", [])
        self.status = self.data.get("status", None)
        self.percent_owned = self.data.get("percent_owned", 0)
        self.cant_cut = self.percent_owned >= 80
        self.must_start = self.percent_owned >= 93
        is_goalie = self.data.get("isGoalie", False)
        position_type = self.data.get("position_type", None)
        self.is_goalie = is_goalie or position_type == "G"
        self.position_type = "G" if self.is_goalie else "P"

        self.points = self.data.get("points", 0)
        self.team = self.data.get("team", None)

        self.game_today = self.league.nhl.teams_playing.get(self.team, False)

        self.starting_behind_net = False
        if self.is_goalie:
            if self.league.nhl.is_goalie_starting_behind_net(self.name):
                self.starting_behind_net = True

        self.has_inactive_position = any(pos in self.eligible_positions for pos in self.league.inactive_positions)

        self.is_inactive = self.status in self.league.not_playing_statuses
        self.is_rostered_as_inactive = self.position in self.league.inactive_positions

        self.location = ""
        self.stats = {}
        self.normalized_stats = {}
        self.rankings = {}
        self.unified_score = 0

    def build_player_data(self, player):
        """Get the extra attributes for a player"""
        player_data = player
        pc = player.get("percent_owned", 0)
        if pc == 0:
            fetch_pc = self.league.yahoo_api.league.percent_owned([player["player_id"]])
            if len(fetch_pc) > 0:
                pc = fetch_pc[0]["percent_owned"]
            else:
                pc = 0
        player_data["percent_owned"] = pc
        player_data["eligible_positions"] = player.get("eligible_positions", [])
        player_data["selected_position"] = player.get("selected_position", "")
        player_data["key"] = self.league.yahoo_api.credentials["game_key"] + ".p." + str(player["player_id"])
        player_data["player_id"] = player["player_id"]
        return player_data

    def evaluate_player(self, no_log=False):
        last_week_score = self.rankings[self.league.time_periods[0]]["weighted_score"]
        last_month_score = self.rankings[self.league.time_periods[1]]["weighted_score"]
        season_score = self.rankings[self.league.time_periods[2]]["weighted_score"]
        projected_rank = self.rankings[self.league.time_periods[2]]["projected_rank"]
        owned_percentage = self.percent_owned

        def calculate_score_from_percentile(player_score, percentiles):
            if player_score >= percentiles["90th"]:
                return 3
            elif player_score >= percentiles["80th"]:
                return 2.5
            elif player_score >= percentiles["70th"]:
                return 2
            elif player_score >= percentiles["60th"]:
                return 1
            elif player_score >= percentiles["50th"]:
                return 0.5
            elif player_score >= percentiles["40th"]:
                return -0.5
            elif player_score >= percentiles["30th"]:
                return -1
            elif player_score >= percentiles["20th"]:
                return -2
            elif player_score >= percentiles["10th"]:
                return -2.5
            elif player_score >= percentiles["5th"]:
                return -3
            else:
                return -3

        def calculate_score_from_ownership(ownership):
            if ownership >= 90:
                return 1
            elif ownership >= 80:
                return 0.5
            elif ownership >= 35:
                return 0.0
            elif ownership >= 20:
                return -1
            elif ownership >= 10:
                return -1.5
            else:
                return -2

        def calculate_score_from_projections_vs_performance(last_week_score, season_score, projected_rank):
            percentile_score_last_week = calculate_score_from_percentile(
                last_week_score, self.league.average_weighted_scores[self.league.time_periods[0]]["percentiles"]
            )
            percentile_score_last_month = calculate_score_from_percentile(
                last_month_score, self.league.average_weighted_scores[self.league.time_periods[1]]["percentiles"]
            )

            # Calculate percentile scores for season and last week
            percentile_score_season = calculate_score_from_percentile(
                season_score, self.league.average_weighted_scores[self.league.time_periods[2]]["percentiles"]
            )
            # Combine the scores (can adjust weighting between season and last week if needed)
            combined_percentile_score = (percentile_score_season * 0.6 + percentile_score_last_week * 0.4 + percentile_score_last_month * 0.5) / 3
            self.logger.info(f"  - Combined Percentile Score: {combined_percentile_score:.2f}")
            if combined_percentile_score > 2.5:
                return 0

            # Evaluate based on projection rank
            if projected_rank < 40:  # Highly ranked players are expected to perform well
                if combined_percentile_score <= 1.5:  # Poor percentile performance
                    return -2.5
                elif combined_percentile_score <= 1.75:
                    return -2
                elif combined_percentile_score <= 2:
                    return -1.5
                elif combined_percentile_score <= 2.25:
                    return -1
                elif combined_percentile_score <= 2.5:
                    return -0.5
                else:
                    return 0  # Reward good percentile performance

            elif projected_rank < 70:  # Highly ranked players are expected to perform well
                if combined_percentile_score <= 1.5:  # Poor percentile performance
                    return -1.5
                elif combined_percentile_score <= 1.75:
                    return -1
                elif combined_percentile_score <= 2:
                    return -0.5
                else:
                    return 0  # Reward good percentile performance

            elif projected_rank < 100:  # Medium-ranked players
                if combined_percentile_score <= 1.5:  # Very poor performance
                    return -0.5
                else:
                    return 0
            else:  # Low-ranked players
                return 0  # No additional penalty for lower expectations

        if not no_log:
            self.logger.info(f"\nEvaluating {self.name}:")
        else:
            self.logger.debug(f"\nEvaluating {self.name}:")
            self.logger.debug(f"  Base Stats:")
            self.logger.debug(f"    - Last Week Score: {last_week_score:.2f}")
            self.logger.debug(f"    - Season Score: {season_score:.2f}")
        self.logger.debug(f"    - Projected Rank: {projected_rank}")
        self.logger.debug(f"    - Ownership: {owned_percentage}%")
        player_score = 0
        reasons = []
        self.logger.debug(f"  Factor 1 - Last Week:")
        last_week_score_from_percentile = calculate_score_from_percentile(
            last_week_score, self.league.average_weighted_scores[self.league.time_periods[0]]["percentiles"]
        )
        last_week_score_from_percentile *= self.league.last_week_weight
        player_score += last_week_score_from_percentile
        reasons.append(f"  - Last Week Score: {last_week_score_from_percentile:.2f}")

        self.logger.debug(f"  Factor 2 - Last Month:")
        last_month_score_from_percentile = calculate_score_from_percentile(
            last_month_score, self.league.average_weighted_scores[self.league.time_periods[1]]["percentiles"]
        )
        last_month_score_from_percentile *= self.league.last_month_weight
        player_score += last_month_score_from_percentile
        reasons.append(f"  - Last Month Score: {last_month_score_from_percentile:.2f}")

        self.logger.debug(f"  Factor 3 - Season:")
        season_score_from_percentile = calculate_score_from_percentile(
            season_score, self.league.average_weighted_scores[self.league.time_periods[2]]["percentiles"]
        )
        season_score_from_percentile *= self.league.season_weight
        reasons.append(f"  - Season Score: {season_score_from_percentile:.2f}")
        player_score += season_score_from_percentile

        self.logger.debug(f"  Factor 3 - Projected Rank Vs Performance:")
        projected_rank_vs_performance = calculate_score_from_projections_vs_performance(last_week_score, season_score, projected_rank)
        projected_rank_vs_performance *= self.league.projected_rank_weight
        player_score += projected_rank_vs_performance
        reasons.append(f"  - Projected Rank Vs Performance: {projected_rank_vs_performance:.2f}")

        self.logger.debug(f"  Factor 4 - Ownership Percentage:")
        ownership_score = calculate_score_from_ownership(owned_percentage)
        ownership_score *= self.league.percent_owned_weight
        player_score += ownership_score
        reasons.append(f"  - Ownership Percentage: {ownership_score:.2f}")
        self.logger.debug(f"  Factor 5 - Preseason Poor projections:")
        if projected_rank > 200:
            player_score -= 0.75
            reasons.append(f"❌ Extremely low projections ({projected_rank}): -0.75 point")
        elif projected_rank > 150:
            player_score -= 0.50
            reasons.append(f"❌ Extremely low projections ({projected_rank}): -0.50 point")
        elif projected_rank > 100:
            player_score -= 0.25
            reasons.append(f"❌ Low projections ({projected_rank}): -0.5 point")
        else:
            reasons.append(f"✅ Projected rank is acceptable")

        if self.is_inactive:
            player_score -= 1
            reasons.append(f"❌ Inactive status: -1 point")

        self.logger.debug(f"  Final Player Score: {player_score}")
        if not no_log:
            self.logger.info(f"Candidate: {self.name} [{player_score}]")

            for reason in reasons:
                self.logger.info(f"- {reason}")

        self.unified_score = player_score
        return player_score

    def __str__(self):
        game_today = "T" if self.game_today else "F"
        weighted_score = self.rankings.get(self.league.time_periods[2], {}).get("weighted_score", "N/A")
        team = self.team or "N/A"
        return f"{self.name} | {self.player_id} | {self.position} | {', '.join(self.eligible_positions)} | {self.percent_owned}% | {self.points} | {game_today} | {weighted_score} | {team}"

    def __repr__(self):
        return f"Player(name='{self.name}', position='{self.position}', eligible_positions='{self.eligible_positions}', status='{self.status}', percent_owned={self.percent_owned})"
