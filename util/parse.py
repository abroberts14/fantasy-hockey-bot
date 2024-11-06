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