from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List
from database import get_db
import schemas, crud, models
from auth import get_current_user

router = APIRouter(prefix="/scoring", tags=["Scoring"])

@router.post("/delivery", response_model=schemas.DeliveryResponse, dependencies=[Depends(get_current_user)])
def record_delivery(delivery: schemas.DeliveryCreate, db: Session = Depends(get_db)):
    return crud.record_delivery(db=db, delivery=delivery)

@router.get("/match/{match_id}/live")
def get_live_scorecard(match_id: int, db: Session = Depends(get_db)):
    match = crud.get_match(db, match_id)
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
        
    deliveries = db.query(models.Delivery).filter(models.Delivery.match_id == match_id).all()
    
    innings_data = {}
    for inn in [1, 2]:
        inn_deliveries = [d for d in deliveries if d.innings == inn]
        runs = sum(d.runs + d.extras for d in inn_deliveries)
        wickets = sum(1 for d in inn_deliveries if d.is_wicket)
        
        legal_balls = sum(1 for d in inn_deliveries if crud.is_legal_delivery(d.extra_type))
        overs = f"{legal_balls // 6}.{legal_balls % 6}"
        
        crr = (runs / legal_balls * 6) if legal_balls > 0 else 0
        
        # Last 5 overs run rate
        last_30_balls = inn_deliveries[-30:] if len(inn_deliveries) >= 30 else inn_deliveries
        last_5_runs = sum(d.runs + d.extras for d in last_30_balls)
        last_5_legal = sum(1 for d in last_30_balls if crud.is_legal_delivery(d.extra_type))
        last_5_crr = (last_5_runs / last_5_legal * 6) if last_5_legal > 0 else 0
        
        req_rr = None
        if inn == 2 and innings_data.get(1):
            target = innings_data[1]["runs"] + 1
            runs_needed = target - runs
            balls_remaining = (20 * 6 if match.format == models.MatchFormat.T20 else 50 * 6) - legal_balls
            req_rr = (runs_needed / balls_remaining * 6) if balls_remaining > 0 else 0

        innings_data[inn] = {
            "runs": runs,
            "wickets": wickets,
            "overs": overs,
            "current_run_rate": round(crr, 2),
            "last_5_overs_run_rate": round(last_5_crr, 2),
            "required_run_rate": round(req_rr, 2) if req_rr is not None else None
        }
        
    return innings_data

@router.get("/match/{match_id}/batsman/{batsman_id}")
def get_batsman_card(match_id: int, batsman_id: int, db: Session = Depends(get_db)):
    deliveries = db.query(models.Delivery).filter(
        models.Delivery.match_id == match_id,
        models.Delivery.batsman_id == batsman_id
    ).all()
    
    if not deliveries:
        raise HTTPException(status_code=404, detail="Batsman records not found for this match")
        
    runs = sum(d.runs for d in deliveries)
    # Wides don't count as ball faced, but no-balls do
    balls_faced = sum(1 for d in deliveries if d.extra_type not in ["wide", "w"])
    fours = sum(1 for d in deliveries if d.runs == 4)
    sixes = sum(1 for d in deliveries if d.runs == 6)
    strike_rate = (runs / balls_faced * 100) if balls_faced > 0 else 0
    
    # Check how out
    out_delivery = db.query(models.Delivery).filter(
        models.Delivery.match_id == match_id,
        models.Delivery.is_wicket == True,
        models.Delivery.batsman_id == batsman_id  # Assuming batsman_id is the one who got out for simplicity
    ).first()
    
    how_out = "not out"
    if out_delivery:
        how_out = f"c {out_delivery.fielder_id} b {out_delivery.bowler_id}" if out_delivery.wicket_type == "caught" else out_delivery.wicket_type
        
    return {
        "batsman_id": batsman_id,
        "runs": runs,
        "balls_faced": balls_faced,
        "fours": fours,
        "sixes": sixes,
        "strike_rate": round(strike_rate, 2),
        "how_out": how_out
    }

@router.get("/match/{match_id}/bowler/{bowler_id}")
def get_bowler_figures(match_id: int, bowler_id: int, db: Session = Depends(get_db)):
    deliveries = db.query(models.Delivery).filter(
        models.Delivery.match_id == match_id,
        models.Delivery.bowler_id == bowler_id
    ).all()
    
    if not deliveries:
        raise HTTPException(status_code=404, detail="Bowler records not found for this match")
        
    legal_balls = sum(1 for d in deliveries if crud.is_legal_delivery(d.extra_type))
    overs = f"{legal_balls // 6}.{legal_balls % 6}"
    
    runs_conceded = sum(d.runs + d.extras for d in deliveries if d.extra_type not in ["bye", "leg-bye"])
    wickets = sum(1 for d in deliveries if d.is_wicket and d.wicket_type not in ["run out"])
    
    economy = (runs_conceded / legal_balls * 6) if legal_balls > 0 else 0
    
    # Maidens (simplified logic: check if any over had 6 legal balls and 0 runs)
    maidens = 0
    over_runs = {}
    for d in deliveries:
        if d.over_number not in over_runs:
            over_runs[d.over_number] = {"runs": 0, "legal_balls": 0}
        over_runs[d.over_number]["runs"] += (d.runs + d.extras)
        if crud.is_legal_delivery(d.extra_type):
            over_runs[d.over_number]["legal_balls"] += 1
            
    for o, stats in over_runs.items():
        if stats["legal_balls"] == 6 and stats["runs"] == 0:
            maidens += 1

    return {
        "bowler_id": bowler_id,
        "overs": overs,
        "maidens": maidens,
        "runs_conceded": runs_conceded,
        "wickets": wickets,
        "economy_rate": round(economy, 2)
    }

@router.get("/match/{match_id}/partnerships")
def get_partnership_tracker(match_id: int, db: Session = Depends(get_db)):
    deliveries = db.query(models.Delivery).filter(models.Delivery.match_id == match_id).order_by(models.Delivery.id).all()
    
    partnerships = []
    current_p = None
    
    for d in deliveries:
        pair = tuple(sorted([d.batsman_id, d.non_striker_id]))
        if current_p is None or current_p["pair"] != pair:
            if current_p:
                partnerships.append(current_p)
            current_p = {"pair": pair, "runs": 0, "balls": 0}
            
        current_p["runs"] += d.runs + (d.extras if d.extra_type in ["no-ball", "nb", "wide", "w"] else 0)
        if d.extra_type not in ["wide", "w"]:
            current_p["balls"] += 1
            
        if d.is_wicket:
            partnerships.append(current_p)
            current_p = None
            
    if current_p:
        partnerships.append(current_p)
        
    return {"match_id": match_id, "partnerships": partnerships}
