import os
import pickle
from datetime import datetime
import logging

CACHE_DIR = "cache"

logger = logging.getLogger(__name__)


def save_object(obj, object_name):
    """Save an object to a pickle file with a timestamped filename."""
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)

    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"{CACHE_DIR}/{date_str}_{object_name}.pkl"

    try:
        with open(filename, "wb") as f:
            pickle.dump(obj, f)
        logger.debug(f"Object saved successfully to {filename}")
    except Exception as e:
        logger.error(f"Error saving object: {e}")


def load_object(object_name):
    """Load the most recent object with the given name from the cache directory."""
    try:
        date_str = datetime.now().strftime("%Y-%m-%d")
        os.makedirs(CACHE_DIR, exist_ok=True)

        filepath = os.path.join(CACHE_DIR, f"{date_str}_{object_name}.pkl")
        if os.path.exists(filepath):
            with open(filepath, "rb") as f:
                return pickle.load(f)
        else:
            logger.debug(f"No cached files found for {object_name}.")
            return None

    except Exception as e:
        logger.error(f"Error loading object: {e}")
        return None
