from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
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

    max_overs_map = {
        models.MatchFormat.T20: 20,
        models.MatchFormat.ODI: 50,
        models.MatchFormat.TEST: None,
    }
    max_overs = max_overs_map[match.format]

    innings_data = {}
    for inn in [1, 2]:
        inn_deliveries = [d for d in deliveries if d.innings == inn]
        runs = sum(d.runs + d.extras for d in inn_deliveries)
        wickets = sum(1 for d in inn_deliveries if d.is_wicket)

        legal_balls = sum(1 for d in inn_deliveries if crud.is_legal_delivery(d.extra_type))
        overs = f"{legal_balls // 6}.{legal_balls % 6}"

        crr = (runs / legal_balls * 6) if legal_balls > 0 else 0.0

        # Last 5 overs run rate: deliveries from the last 5 over numbers played
        last_5_crr = 0.0
        if inn_deliveries:
            current_over = max(d.over_number for d in inn_deliveries)
            last_5_start = max(0, current_over - 4)
            last_5_dels = [d for d in inn_deliveries if d.over_number >= last_5_start]
            last_5_runs = sum(d.runs + d.extras for d in last_5_dels)
            last_5_legal = sum(1 for d in last_5_dels if crud.is_legal_delivery(d.extra_type))
            last_5_crr = (last_5_runs / last_5_legal * 6) if last_5_legal > 0 else 0.0

        req_rr = None
        if inn == 2 and innings_data.get(1) and max_overs is not None:
            target = innings_data[1]["runs"] + 1
            runs_needed = target - runs
            balls_remaining = (max_overs * 6) - legal_balls
            if balls_remaining > 0:
                req_rr = round(runs_needed / balls_remaining * 6, 2)
            else:
                req_rr = float('inf') if runs_needed > 0 else 0.0

        innings_data[inn] = {
            "runs": runs,
            "wickets": wickets,
            "overs": overs,
            "current_run_rate": round(crr, 2),
            "last_5_overs_run_rate": round(last_5_crr, 2),
            "required_run_rate": req_rr,
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
    # Wides don't count as balls faced
    balls_faced = sum(1 for d in deliveries if d.extra_type not in ["wide", "w"])
    fours = sum(1 for d in deliveries if d.runs == 4)
    sixes = sum(1 for d in deliveries if d.runs == 6)
    strike_rate = (runs / balls_faced * 100) if balls_faced > 0 else 0.0

    # Check how out — look for the wicket delivery where this batsman was dismissed
    out_delivery = db.query(models.Delivery).filter(
        models.Delivery.match_id == match_id,
        models.Delivery.is_wicket == True,
        models.Delivery.batsman_id == batsman_id,
    ).first()

    how_out = "not out"
    if out_delivery:
        bowler_name = out_delivery.bowler.name if out_delivery.bowler else str(out_delivery.bowler_id)
        fielder_name = out_delivery.fielder.name if out_delivery.fielder else None
        wtype = (out_delivery.wicket_type or "").lower()
        if wtype == "caught":
            how_out = f"c {fielder_name} b {bowler_name}" if fielder_name else f"c & b {bowler_name}"
        elif wtype == "stumped":
            how_out = f"st {fielder_name} b {bowler_name}" if fielder_name else f"st b {bowler_name}"
        elif wtype == "run out":
            how_out = f"run out ({fielder_name})" if fielder_name else "run out"
        else:
            how_out = f"{out_delivery.wicket_type} b {bowler_name}"

    return {
        "batsman_id": batsman_id,
        "runs": runs,
        "balls_faced": balls_faced,
        "fours": fours,
        "sixes": sixes,
        "strike_rate": round(strike_rate, 2),
        "how_out": how_out,
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

    # Byes and leg-byes are not charged to the bowler
    runs_conceded = sum(d.runs + d.extras for d in deliveries if d.extra_type not in ["bye", "leg-bye"])
    # Run outs are not credited to the bowler
    wickets = sum(1 for d in deliveries if d.is_wicket and (d.wicket_type or "").lower() != "run out")

    economy = (runs_conceded / legal_balls * 6) if legal_balls > 0 else 0.0

    # Maiden: over bowled by this bowler with 6 legal balls and 0 runs conceded
    maidens = 0
    over_stats: dict = {}
    for d in deliveries:
        o = d.over_number
        if o not in over_stats:
            over_stats[o] = {"runs": 0, "legal_balls": 0}
        over_stats[o]["runs"] += d.runs + d.extras if d.extra_type not in ["bye", "leg-bye"] else 0
        if crud.is_legal_delivery(d.extra_type):
            over_stats[o]["legal_balls"] += 1

    for _, s in over_stats.items():
        if s["legal_balls"] == 6 and s["runs"] == 0:
            maidens += 1

    return {
        "bowler_id": bowler_id,
        "overs": overs,
        "maidens": maidens,
        "runs_conceded": runs_conceded,
        "wickets": wickets,
        "economy_rate": round(economy, 2),
    }

@router.get("/match/{match_id}/partnerships")
def get_partnership_tracker(match_id: int, db: Session = Depends(get_db)):
    deliveries = db.query(models.Delivery).filter(
        models.Delivery.match_id == match_id
    ).order_by(models.Delivery.innings, models.Delivery.over_number, models.Delivery.ball_number).all()

    partnerships = []
    current_p = None

    for d in deliveries:
        pair = sorted([d.batsman_id, d.non_striker_id])  # list for consistent comparison
        if current_p is None or current_p["pair"] != pair or current_p["innings"] != d.innings:
            if current_p:
                partnerships.append(current_p)
            current_p = {"pair": pair, "innings": d.innings, "runs": 0, "balls": 0}

        # Wides/no-balls add to partnership runs
        current_p["runs"] += d.runs + (d.extras if d.extra_type in ["no-ball", "nb", "wide", "w"] else 0)
        if d.extra_type not in ["wide", "w"]:
            current_p["balls"] += 1

        if d.is_wicket:
            partnerships.append(current_p)
            current_p = None

    if current_p:
        partnerships.append(current_p)

    return {"match_id": match_id, "partnerships": partnerships}
