from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
import models

router = APIRouter(prefix="/stats", tags=["Stats"])

@router.get("/head-to-head")
def get_head_to_head(team_a_name: str, team_b_name: str, db: Session = Depends(get_db)):
    # Find all completed matches where these two teams played
    # This is simplified: in a real system we'd compare team IDs, 
    # but based on requirements, teams are created per match. 
    # We'll match by name string.
    
    matches = db.query(models.Match).filter(models.Match.status == models.MatchStatus.COMPLETED).all()
    
    team_a_wins = 0
    team_b_wins = 0
    draws = 0
    
    for m in matches:
        teams = {t.name: t.id for t in m.teams}
        if team_a_name in teams and team_b_name in teams:
            team_a_id = teams[team_a_name]
            team_b_id = teams[team_b_name]
            
            # Figure out who won
            team_a_runs = sum(d.runs + d.extras for d in m.deliveries if d.batsman.team_id == team_a_id)
            team_b_runs = sum(d.runs + d.extras for d in m.deliveries if d.batsman.team_id == team_b_id)
            
            if team_a_runs > team_b_runs:
                team_a_wins += 1
            elif team_b_runs > team_a_runs:
                team_b_wins += 1
            else:
                draws += 1
                
    return {
        "team_a": team_a_name,
        "team_b": team_b_name,
        "team_a_wins": team_a_wins,
        "team_b_wins": team_b_wins,
        "draws": draws,
        "total_matches": team_a_wins + team_b_wins + draws
    }
