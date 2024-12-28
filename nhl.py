import logging
from datetime import datetime
import requests
import json
from util.constants import NHL_TEAM_ID, NEXT_GAME_URL
from util.parse import FantasyHockeyProjectionScraper, FantasyHockeyGoalieScraper, StartingGoalieScraper
from tqdm import tqdm


class NHL:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.teams_playing = self.get_all_teams_next_games()
        scraper_skaters_scraper = FantasyHockeyProjectionScraper(url="https://www.numberfire.com/nhl/fantasy/remaining-projections/skaters")
        scraper_skaters_scraper.fetch_data()
        scraper_goalies_scraper = FantasyHockeyProjectionScraper(url="https://www.numberfire.com/nhl/fantasy/remaining-projections/goalies")
        scraper_goalies_scraper.fetch_data()
        self.skaters = scraper_skaters_scraper.fetch_all_players()
        self.goalies = scraper_goalies_scraper.fetch_all_players()
        self.player_projections = {**self.skaters, **self.goalies}
        scrape_goalies_extra_scraper = FantasyHockeyGoalieScraper()

        self.goalie_extra_stats = scrape_goalies_extra_scraper.fetch_all_time_periods()
        self.starting_goalie_scraper = StartingGoalieScraper()

    # Remove the starting_goalie_scraper from the state to avoid pickling it
    def __getstate__(self):
        # Get the current state of the instance
        state = self.__dict__.copy()
        # Remove the attribute you want to ignore
        if "starting_goalie_scraper" in state:
            state["starting_goalie_scraper"] = None
        return state

    def is_goalie_starting_behind_net(self, name):
        if not self.starting_goalie_scraper:
            self.starting_goalie_scraper = StartingGoalieScraper()
        starting_behind_net = self.starting_goalie_scraper.get_starting_goalies([name]).get(name, False)
        return starting_behind_net

    def get_all_teams_next_games(self):
        """
        Returns a dictionary of all NHL teams with boolean values indicating if they play today

        Returns:
            dict: Format {'Team Name': bool} where bool is True if team plays today
        """
        today = datetime.now().date()
        teams_playing = {}

        for team in tqdm(NHL_TEAM_ID.keys(), desc="Fetching NHL teams playing today..."):
            try:
                url = NEXT_GAME_URL % NHL_TEAM_ID[team]
                self.logger.debug("Next game url: %s" % url)
                response = requests.get(url)
                json_content = json.loads(response.content)

                # Find the first game with gameState FUT
                next_game_date = None
                games = json_content.get("games", [])

                for game in games:
                    if game.get("gameState") == "FUT":
                        next_game_date = game.get("gameDate")
                        break

                if next_game_date:
                    next_game_date = datetime.strptime(next_game_date, "%Y-%m-%d").date()
                    self.logger.debug(f"Comparing {next_game_date} to {today}: {next_game_date == today}")
                    teams_playing[team] = next_game_date == today
                else:
                    teams_playing[team] = False

            except Exception as e:
                self.logger.error(f"Error getting next game for {team}: {str(e)}")
                teams_playing[team] = False

        self.logger.debug(f"Teams playing today: {teams_playing}")
        return teams_playing
