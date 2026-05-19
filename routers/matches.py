from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from database import get_db
import schemas, crud, models
from auth import get_current_user

router = APIRouter(prefix="/matches", tags=["Matches"])

@router.post("/", response_model=schemas.MatchResponse, dependencies=[Depends(get_current_user)])
def create_match(match: schemas.MatchCreate, db: Session = Depends(get_db)):
    return crud.create_match(db=db, match=match)

@router.get("/{match_id}", response_model=schemas.MatchResponse)
def get_match(match_id: int, db: Session = Depends(get_db)):
    db_match = crud.get_match(db, match_id=match_id)
    if db_match is None:
        raise HTTPException(status_code=404, detail="Match not found")
    return db_match

@router.get("/{match_id}/summary")
def get_match_summary(match_id: int, db: Session = Depends(get_db)):
    db_match = crud.get_match(db, match_id=match_id)
    if db_match is None:
        raise HTTPException(status_code=404, detail="Match not found")
        
    deliveries = db_match.deliveries
    
    # Calculate fall of wickets
    fow = []
    runs_when_wicket = 0
    for d in sorted(deliveries, key=lambda x: (x.innings, x.over_number, x.ball_number)):
        runs_when_wicket += d.runs + d.extras
        if d.is_wicket:
            fow.append({
                "innings": d.innings,
                "score": runs_when_wicket,
                "over": f"{d.over_number}.{d.ball_number}",
                "batsman_id": d.batsman_id,
                "wicket_type": d.wicket_type
            })
            
    # Calculate winner by simplest logic (most runs)
    team_a_runs = sum(d.runs + d.extras for d in deliveries if d.innings == 1)
    team_b_runs = sum(d.runs + d.extras for d in deliveries if d.innings == 2)
    
    result = "Match drawn or tied"
    if team_a_runs > team_b_runs and db_match.status == models.MatchStatus.COMPLETED:
        result = "Team batting first won"
    elif team_b_runs > team_a_runs and db_match.status == models.MatchStatus.COMPLETED:
        result = "Team batting second won"
        
    return {
        "match_id": match_id,
        "format": db_match.format,
        "status": db_match.status,
        "result": result,
        "team_a_runs": team_a_runs,
        "team_b_runs": team_b_runs,
        "fall_of_wickets": fow
    }
