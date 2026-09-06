import os
from dotenv import load_dotenv

load_dotenv()

ODDS_API_KEY = os.getenv("ODDS_API_KEY", "")
ODDS_API_BASE = "https://api.the-odds-api.com/v4"

MLB_API_BASE = "https://statsapi.mlb.com/api/v1"

SEASON = 2026
TIMEZONE = "America/Chicago"
