from sqlalchemy import Column, Integer, String, Enum, ForeignKey, Date, Boolean
from sqlalchemy.orm import relationship
import enum
from database import Base

class MatchFormat(str, enum.Enum):
    T20 = "T20"
    ODI = "ODI"
    TEST = "TEST"

class MatchStatus(str, enum.Enum):
    UPCOMING = "UPCOMING"
    LIVE = "LIVE"
    COMPLETED = "COMPLETED"

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)

class Match(Base):
    __tablename__ = "matches"
    
    id = Column(Integer, primary_key=True, index=True)
    format = Column(Enum(MatchFormat), nullable=False)
    venue = Column(String, nullable=False)
    date = Column(Date, nullable=False)
    status = Column(Enum(MatchStatus), default=MatchStatus.UPCOMING, nullable=False)
    
    teams = relationship("Team", back_populates="match", cascade="all, delete-orphan")
    deliveries = relationship("Delivery", back_populates="match", cascade="all, delete-orphan")

class Team(Base):
    __tablename__ = "teams"
    
    id = Column(Integer, primary_key=True, index=True)
    match_id = Column(Integer, ForeignKey("matches.id"), nullable=False)
    name = Column(String, nullable=False)
    
    match = relationship("Match", back_populates="teams")
    players = relationship("Player", back_populates="team", cascade="all, delete-orphan")

class Player(Base):
    __tablename__ = "players"
    
    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    name = Column(String, nullable=False)
    role = Column(String, nullable=False)  # e.g., Batsman, Bowler, All-Rounder, Wicketkeeper
    batting_style = Column(String, nullable=False)
    bowling_style = Column(String, nullable=True)
    
    team = relationship("Team", back_populates="players")

class Delivery(Base):
    __tablename__ = "deliveries"
    
    id = Column(Integer, primary_key=True, index=True)
    match_id = Column(Integer, ForeignKey("matches.id"), nullable=False)
    innings = Column(Integer, nullable=False)  # 1 or 2
    over_number = Column(Integer, nullable=False)  # 0-indexed (0 to 19 for T20)
    ball_number = Column(Integer, nullable=False)  # usually 1-6, but could be more for extras
    
    bowler_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    batsman_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    non_striker_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    
    runs = Column(Integer, default=0, nullable=False)
    extras = Column(Integer, default=0, nullable=False)
    extra_type = Column(String, nullable=True)  # wide, no-ball, bye, leg-bye
    
    is_wicket = Column(Boolean, default=False, nullable=False)
    wicket_type = Column(String, nullable=True)  # bowled, caught, lbw, run out, etc.
    fielder_id = Column(Integer, ForeignKey("players.id"), nullable=True)
    
    match = relationship("Match", back_populates="deliveries")
    
    bowler = relationship("Player", foreign_keys=[bowler_id])
    batsman = relationship("Player", foreign_keys=[batsman_id])
    non_striker = relationship("Player", foreign_keys=[non_striker_id])
    fielder = relationship("Player", foreign_keys=[fielder_id])
