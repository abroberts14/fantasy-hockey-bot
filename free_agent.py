class FreeAgentManager:
    def __init__(self, free_agents_skaters_raw, free_agents_goalies_raw, league_free_agents_ranked, moves_left):
        self.free_agents_skaters_raw = free_agents_skaters_raw
        self.free_agents_goalies_raw = free_agents_goalies_raw
        self.league_free_agents_ranked = league_free_agents_ranked
        self.moves_left = moves_left

    def find_best_free_agents(self):
        # Finds and returns the best available players
        pass

    def perform_free_agent_add_drop(self):
        # Manages the action of adding and dropping players from the free agent pool
        pass
