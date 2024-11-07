import requests
from lxml import html
import logging


class FantasyHockeyProjectionScraper:
    def __init__(self, url):
        self.url = url
        self.response = None
        self.tree = None
        self.header_mappings = {
            "Fantasy": "nf active",
            "Games": "gp",
            "TOI": "toi",
            "AVG TOI": "atoi",
            "PIM": "pim",
            "Shots": "s",
            "G": "g",
            "A": "a",
            "Pts": "pts",
            "+/-": "plus_minus",
            "PPG": "ppg",
            "PPA": "ppa",
        }
        self.logger = logging.getLogger(__name__)  # G det the root logger set in main.py

    def fetch_data(self):
        """
        Fetches data from the URL and parses it into an HTML tree.
        Also initializes the headers dictionary.
        """
        self.response = requests.get(self.url)
        if self.response.status_code == 200:
            self.tree = html.fromstring(self.response.content)
        else:
            self.logger.info(f"Failed to retrieve data: Status code {self.response.status_code}")
            self.tree = None

    def get_player_row_index(self, player_name):
        """
        Returns the data-row-index attribute for the specified player's name.
        """
        if self.tree is not None:
            try:
                player_xpath = f"//span[contains(text(), '{player_name}')]/ancestor::tr"
                player_element = self.tree.xpath(player_xpath)
                if player_element:
                    return player_element[0].get("data-row-index")
                else:
                    self.logger.info(f"No data found for player: {player_name}")
                    return None
            except Exception as e:
                self.logger.info(f"An error occurred: {e}")
                return None
        else:
            self.logger.info("No HTML tree to search.")
            return None

    def fetch_player(self, player_name):
        """
        Fetches all relevant stats for the specified player's name and stores them in a dictionary.
        """
        player_stats = {}
        if self.tree is not None:
            player_xpath = f"//span[contains(text(), '{player_name}')]/ancestor::tr"
            player_row = self.tree.xpath(player_xpath)
            if player_row:
                player_stats = {"name": player_name}
                for header, class_name in self.header_mappings.items():
                    data = player_row[0].xpath(f"//tr//td[@class='{class_name}']")
                    if data:
                        player_stats[header] = data[0].text_content().strip()
                    else:
                        player_stats[header] = "Data not available"
                return player_stats
            else:
                self.logger.info(f"No data found for player: {player_name}")
                return None
        else:
            self.logger.info("No HTML tree to search.")
            return None

    def fetch_all_players(self):
        """
        Fetches stats for all players and stores them in a dictionary keyed by player name.
        """
        players_stats = {}
        if self.tree is not None:
            rows = self.tree.xpath("//tr[td[contains(@class, 'player')]]")
            self.logger.info(f"Number of rows found: {len(rows)}")
            for idx, row in enumerate(rows):
                player_name = row[0].text_content().strip().split("\n")[0]
                player_stats = {}
                for header, class_name in self.header_mappings.items():
                    data = row.xpath(f"//td[contains(@class, '{class_name}')]/text()")
                    if data:
                        player_stats[header] = data[idx].strip()
                    else:
                        player_stats[header] = "Data not available"
                players_stats[player_name] = player_stats

            return players_stats

        else:
            self.logger.info("No HTML tree to search.")
            return None


class FantasyHockeyGoalieScraper:
    def __init__(self):
        self.url = None
        self.time_urls = {
            "lastweek": "https://www.quanthockey.com/nhl/seasons/last-week-nhl-goalies-stats.html",
            "lasttwoweeks": "https://www.quanthockey.com/nhl/seasons/last-two-weeks-nhl-goalies-stats.html",
            "lastmonth": "https://www.quanthockey.com/nhl/seasons/last-month-nhl-goalies-stats.html",
            "season": "https://www.quanthockey.com/nhl/seasons/nhl-goalies-stats.html",
        }
        self.response = None
        self.tree = None
        self.goalie_header_mappings = {
            "GP": 1,
            "GAA": 2,
            "SV%": 3,
            "W": 4,
            "L": 5,
            "GA": 6,
            "SV": 7,
            "SOG": 8,
            "SO": 9,
            "TOI": 10,
        }
        self.logger = logging.getLogger(__name__)  # G det the root logger set in main.py

    def fetch_data(self):
        """
        Fetches data from the URL and parses it into an HTML tree.
        Also initializes the headers dictionary.
        """
        self.response = requests.get(self.url)
        if self.response.status_code == 200:
            self.tree = html.fromstring(self.response.content)
        else:
            self.logger.info(f"Failed to retrieve data: Status code {self.response.status_code}")
            self.tree = None

    def fetch_player(self, player_name):
        """
        Fetches all relevant stats for the specified player's name and stores them in a dictionary.
        """
        player_stats = {}
        if self.tree is not None:
            player_xpath = f"//span[contains(text(), '{player_name}')]/ancestor::tr"
            player_row = self.tree.xpath(player_xpath)
            if player_row:
                player_stats = {"name": player_name}
                for header, class_name in self.header_mappings.items():
                    data = player_row[0].xpath(f"//tr//td[@class='{class_name}']")
                    if data:
                        player_stats[header] = data[0].text_content().strip()
                    else:
                        player_stats[header] = "Data not available"
                return player_stats
            else:
                self.logger.info(f"No data found for player: {player_name}")
                return None
        else:
            self.logger.info("No HTML tree to search.")
            return None

    # //tr//td[@class="aligncenter"]/following-sibling::td[1]
    def fetch_all_players(self):
        """
        Fetches stats for all players and stores them in a dictionary keyed by player name.
        """

        players_stats = {}
        if self.tree is not None:
            rows = self.tree.xpath("//table[@id='statistics']//tbody//tr")

            self.logger.info(f"Number of rows found: {len(rows)}")
            for idx, row in enumerate(rows):
                player_name = "".join(c for c in row.xpath("//th[@role='rowheader']")[idx].text_content().strip() if c.isascii()).replace("'", "\\'")
                player_stats = {}

                for header, class_name in self.goalie_header_mappings.items():
                    data = row.xpath(f"//td[@class='aligncenter']/following-sibling::td[{class_name}]/text()")
                    if data:
                        player_stats[header] = data[idx].strip()
                    else:
                        player_stats[header] = "Data not available"
                players_stats[player_name] = player_stats
                # print(player_stats)
        return players_stats

    def fetch_all_time_periods(self):
        time_periods = ["lastweek", "lasttwoweeks", "lastmonth", "season"]
        all_players_stats = {}
        for time in time_periods:
            self.url = self.time_urls[time]
            self.fetch_data()
            players_stats = self.fetch_all_players()
            all_players_stats[time] = players_stats

        # print(all_players_stats)
        return all_players_stats


class StartingGoalieScraper:
    def __init__(self):
        self.url = "https://www.sportsgrid.com/nhl/starting-goalies"
        self.logger = logging.getLogger(__name__)  # Add logger
        self.tree = None
        self.response = None

    def fetch_data(self):
        """
        Fetches data from the URL and parses it into an HTML tree.
        Also initializes the headers dictionary.
        """
        print("init")
        self.response = requests.get(self.url)
        if self.response.status_code == 200:
            self.tree = html.fromstring(self.response.content)
        else:
            print(f"failed to retrieve data: Status code {self.response.content}")
            self.logger.info(f"Failed to retrieve data: Status code {self.response.status_code}")
            self.tree = None

    def get_starting_goalies(self, goalie_names):
        """
        Checks if given goalies are listed as starting.

        Args:
            goalie_names (list): List of goalie names to check

        Returns:
            dict: Dictionary with goalie names as keys and boolean values indicating if they're starting
        """
        self.fetch_data()  # Ensure we have fresh data
        results = {}
        if self.tree is None:
            self.logger.info("No HTML tree available. Call fetch_data() first.")
            return results

        for full_name in goalie_names:
            try:
                # Format name to "S. Lastname"
                first_name, last_name = full_name.split(" ", 1)
                formatted_name = f"{first_name[0]}.{last_name}"

                # Try different XPath approaches
                found = self.tree.xpath(f"//*[contains(text(), '{formatted_name}')]")  # Partial match
                results[full_name] = len(found) > 0
            except Exception as e:
                self.logger.error(f"Error searching for {full_name}: {e}")
                results[full_name] = False

        return results


# scraper = FantasyHockeyGoalieScraper()
# all_players_stats = scraper.fetch_all_time_periods()
# print(all_players_stats)
# Usage
# scraper = FantasyHockeyProjectionScraper()
# scraper.fetch_data()

# players_stats = scraper.fetch_all_players()
# print(players_stats)

# player_info = scraper.fetch_player("Victor Hedman")
# if player_info:
#     print("Player Info:")
#     for stat, value in player_info.items():
#         print(f"{stat}: {value}")
