from sqlalchemy.orm import Session
from sqlalchemy import func
from fastapi import HTTPException
import models
import schemas
from models import MatchFormat

def get_match(db: Session, match_id: int):
    return db.query(models.Match).filter(models.Match.id == match_id).first()

def get_matches(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.Match).offset(skip).limit(limit).all()

def create_match(db: Session, match: schemas.MatchCreate):
    db_match = models.Match(
        format=match.format,
        venue=match.venue,
        date=match.date
    )
    db.add(db_match)
    db.commit()
    db.refresh(db_match)
    
    # Add teams
    team_a = models.Team(match_id=db_match.id, name=match.team_a.name)
    team_b = models.Team(match_id=db_match.id, name=match.team_b.name)
    db.add(team_a)
    db.add(team_b)
    db.commit()
    db.refresh(team_a)
    db.refresh(team_b)
    
    # Add players for team A
    for p in match.team_a.players:
        db.add(models.Player(team_id=team_a.id, **p.model_dump()))
    
    # Add players for team B
    for p in match.team_b.players:
        db.add(models.Player(team_id=team_b.id, **p.model_dump()))
        
    db.commit()
    return db_match

def is_legal_delivery(extra_type: str):
    # Wides and no-balls are not legal deliveries
    if extra_type and extra_type.lower() in ['wide', 'no-ball', 'noball', 'w', 'nb']:
        return False
    return True

def record_delivery(db: Session, delivery: schemas.DeliveryCreate):
    # 1. Reject duplicate ball entry
    existing = db.query(models.Delivery).filter(
        models.Delivery.match_id == delivery.match_id,
        models.Delivery.innings == delivery.innings,
        models.Delivery.over_number == delivery.over_number,
        models.Delivery.ball_number == delivery.ball_number
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Delivery already exists for this ball number in this over.")

    # Get match details
    match = db.query(models.Match).filter(models.Match.id == delivery.match_id).first()
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    # 1.5 Validate Players and Teams
    batsman = db.query(models.Player).filter(models.Player.id == delivery.batsman_id).first()
    non_striker = db.query(models.Player).filter(models.Player.id == delivery.non_striker_id).first()
    bowler = db.query(models.Player).filter(models.Player.id == delivery.bowler_id).first()

    if not batsman or not non_striker or not bowler:
        raise HTTPException(status_code=404, detail="One or more players not found")

    if batsman.team_id != non_striker.team_id:
        raise HTTPException(status_code=400, detail="Batsman and non-striker must belong to the same team")

    if batsman.team_id == bowler.team_id:
        raise HTTPException(status_code=400, detail="Bowler must belong to the opposing team")

    match_team_ids = [t.id for t in match.teams]
    if batsman.team_id not in match_team_ids or bowler.team_id not in match_team_ids:
        raise HTTPException(status_code=400, detail="Players must belong to teams participating in this match")

    # Enforce innings logic: Batting team must be consistent across an innings
    current_innings_del = db.query(models.Delivery).filter(
        models.Delivery.match_id == delivery.match_id,
        models.Delivery.innings == delivery.innings
    ).first()

    if current_innings_del:
        existing_batsman = db.query(models.Player).filter(models.Player.id == current_innings_del.batsman_id).first()
        if existing_batsman and existing_batsman.team_id != batsman.team_id:
            raise HTTPException(status_code=400, detail="Batsmen must belong to the batting team for this innings")
    elif delivery.innings == 2:
        # First ball of innings 2: must be the other team batting
        innings_1_del = db.query(models.Delivery).filter(
            models.Delivery.match_id == delivery.match_id,
            models.Delivery.innings == 1
        ).first()
        if innings_1_del:
            innings_1_batsman = db.query(models.Player).filter(models.Player.id == innings_1_del.batsman_id).first()
            if innings_1_batsman and innings_1_batsman.team_id == batsman.team_id:
                raise HTTPException(status_code=400, detail="The team batting in innings 2 must be different from innings 1")

    # 2. Check if innings has ended (Wickets or Overs)
    # Wickets
    wickets = db.query(func.count(models.Delivery.id)).filter(
        models.Delivery.match_id == delivery.match_id,
        models.Delivery.innings == delivery.innings,
        models.Delivery.is_wicket == True
    ).scalar() or 0
    if wickets >= 10:
        raise HTTPException(status_code=400, detail="Innings has already ended (10 wickets).")

    # Legal deliveries in current innings
    deliveries_in_innings = db.query(models.Delivery).filter(
        models.Delivery.match_id == delivery.match_id,
        models.Delivery.innings == delivery.innings
    ).all()
    legal_balls_innings = sum(1 for d in deliveries_in_innings if is_legal_delivery(d.extra_type))
    
    max_overs = 20 if match.format == MatchFormat.T20 else (50 if match.format == MatchFormat.ODI else float('inf'))
    if legal_balls_innings >= max_overs * 6:
        raise HTTPException(status_code=400, detail=f"Innings has already ended ({max_overs} overs).")

    # 3. Check 6 legal deliveries per over limit
    deliveries_in_over = [d for d in deliveries_in_innings if d.over_number == delivery.over_number]
    legal_balls_over = sum(1 for d in deliveries_in_over if is_legal_delivery(d.extra_type))
    if legal_balls_over >= 6:
        raise HTTPException(status_code=400, detail="Over already has 6 legal deliveries.")

    # 4. Bowler cap check
    legal_balls_by_bowler = sum(1 for d in deliveries_in_innings if d.bowler_id == delivery.bowler_id and is_legal_delivery(d.extra_type))
    bowler_max_overs = 4 if match.format == MatchFormat.T20 else (10 if match.format == MatchFormat.ODI else float('inf'))
    if legal_balls_by_bowler >= bowler_max_overs * 6:
        raise HTTPException(status_code=400, detail=f"Bowler has reached the maximum over limit ({bowler_max_overs} overs).")

    db_delivery = models.Delivery(**delivery.model_dump())
    db.add(db_delivery)
    db.commit()
    db.refresh(db_delivery)
    return db_delivery
