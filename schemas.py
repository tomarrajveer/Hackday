from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import date
from models import MatchFormat, MatchStatus

# User Schemas
class UserBase(BaseModel):
    username: str

class UserCreate(UserBase):
    password: str

class UserResponse(UserBase):
    id: int

    class Config:
        from_attributes = True

# Token Schemas
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

# Player Schemas
class PlayerBase(BaseModel):
    name: str
    role: str
    batting_style: str
    bowling_style: Optional[str] = None

class PlayerCreate(PlayerBase):
    pass

class PlayerResponse(PlayerBase):
    id: int
    team_id: int

    class Config:
        from_attributes = True

class PlayersAdd(BaseModel):
    players: List[PlayerCreate]

# Team Schemas
class TeamBase(BaseModel):
    name: str

class TeamCreate(TeamBase):
    players: List[PlayerCreate]

class TeamResponse(TeamBase):
    id: int
    match_id: int
    players: List[PlayerResponse] = []

    class Config:
        from_attributes = True

# Match Schemas
class MatchBase(BaseModel):
    format: MatchFormat
    venue: str
    date: date

class MatchCreate(MatchBase):
    team_a: TeamCreate
    team_b: TeamCreate

class MatchResponse(MatchBase):
    id: int
    status: MatchStatus
    teams: List[TeamResponse] = []

    class Config:
        from_attributes = True

class MatchStatusUpdate(BaseModel):
    status: MatchStatus
    player_of_match_id: Optional[int] = None

# Delivery Schemas
class DeliveryBase(BaseModel):
    match_id: int
    innings: int
    over_number: int
    ball_number: int
    bowler_id: int
    batsman_id: int
    non_striker_id: int
    runs: int = 0
    extras: int = 0
    extra_type: Optional[str] = None
    is_wicket: bool = False
    wicket_type: Optional[str] = None
    fielder_id: Optional[int] = None

class DeliveryCreate(DeliveryBase):
    pass

class DeliveryResponse(DeliveryBase):
    id: int
    match_id: int

    class Config:
        from_attributes = True
