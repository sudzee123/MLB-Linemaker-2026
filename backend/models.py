"""
Pydantic models for API request/response shapes.
"""

from pydantic import BaseModel


class PitcherInfo(BaseModel):
    id: int | None
    name: str
    gs: int
    era: float
    ip_per_gs: float
    bp_era: float
    recalc_ra: float


class TeamAnalysis(BaseModel):
    team_id: int
    team_name: str
    abbrev: str
    rs_pg: float
    pitcher: PitcherInfo
    exp_r: float
    win_prob: float
    fair_ml: int
    book_ml: int | None
    book_name: str
    book_implied_prob: float | None
    edge: float | None
    edge_pct: str
    has_edge: bool


class GameAnalysis(BaseModel):
    game_id: int
    date: str
    game_time_ct: str
    game_time_utc: str
    away: TeamAnalysis
    home: TeamAnalysis
    num_books: int
    league_home_rs_pg: float
    league_away_rs_pg: float


class RefreshResponse(BaseModel):
    through_date: str
    games_analyzed: int
    message: str


class PlayResultIn(BaseModel):
    game_date: str
    game_id: int
    team_abbrev: str
    opponent_abbrev: str
    book_ml: int
    edge_pct: str
    result: str   # 'W' or 'L'
    window: str = 'season'


class PlayResultUpdate(BaseModel):
    result: str   # 'W' or 'L'
    book_ml: int
    edge_pct: str


class SettleGroupIn(BaseModel):
    game_id: int
    team_abbrev: str
    result: str   # 'W' or 'L'
