from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
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

@router.post(
    "/{match_id}/teams/{team_id}/players",
    response_model=schemas.TeamResponse,
    dependencies=[Depends(get_current_user)],
)
def add_players(
    match_id: int,
    team_id: int,
    players_data: schemas.PlayersAdd,
    db: Session = Depends(get_db),
):
    match = crud.get_match(db, match_id=match_id)
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    team = db.query(models.Team).filter(
        models.Team.id == team_id,
        models.Team.match_id == match_id,
    ).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found in this match")
    return crud.add_players(db=db, team_id=team_id, players=players_data.players)

@router.patch(
    "/{match_id}/status",
    response_model=schemas.MatchResponse,
    dependencies=[Depends(get_current_user)],
)
def update_match_status(
    match_id: int,
    body: schemas.MatchStatusUpdate,
    db: Session = Depends(get_db),
):
    db_match = crud.get_match(db, match_id=match_id)
    if not db_match:
        raise HTTPException(status_code=404, detail="Match not found")
    if body.player_of_match_id is not None:
        player = db.query(models.Player).filter(models.Player.id == body.player_of_match_id).first()
        if not player:
            raise HTTPException(status_code=404, detail="Player not found")
        match_team_ids = {t.id for t in db_match.teams}
        if player.team_id not in match_team_ids:
            raise HTTPException(status_code=400, detail="Player does not belong to a team in this match")
    return crud.update_match_status(db=db, match_id=match_id, status=body.status, player_of_match_id=body.player_of_match_id)

@router.get("/{match_id}/summary")
def get_match_summary(match_id: int, db: Session = Depends(get_db)):
    db_match = crud.get_match(db, match_id=match_id)
    if db_match is None:
        raise HTTPException(status_code=404, detail="Match not found")

    deliveries = sorted(
        db_match.deliveries,
        key=lambda x: (x.innings, x.over_number, x.ball_number),
    )

    team_map = {t.id: t.name for t in db_match.teams}

    # Fall of wickets per innings
    runs_by_innings: dict = {}
    fow: dict = {1: [], 2: []}
    for d in deliveries:
        inn = d.innings
        runs_by_innings[inn] = runs_by_innings.get(inn, 0) + d.runs + d.extras
        if d.is_wicket:
            fow[inn].append({
                "score": runs_by_innings[inn],
                "over": f"{d.over_number}.{d.ball_number}",
                "batsman_id": d.batsman_id,
                "wicket_type": d.wicket_type,
            })

    innings_1_dels = [d for d in deliveries if d.innings == 1]
    innings_2_dels = [d for d in deliveries if d.innings == 2]

    innings_1_runs = runs_by_innings.get(1, 0)
    innings_2_runs = runs_by_innings.get(2, 0)
    innings_2_wickets = sum(1 for d in innings_2_dels if d.is_wicket)

    # Determine which team batted first
    team_batting_first = "Team 1"
    team_batting_second = "Team 2"
    if innings_1_dels:
        bat_player = db.query(models.Player).filter(
            models.Player.id == innings_1_dels[0].batsman_id
        ).first()
        if bat_player:
            team_batting_first = team_map.get(bat_player.team_id, "Team 1")
            team_batting_second = next(
                (name for tid, name in team_map.items() if tid != bat_player.team_id),
                "Team 2",
            )

    result = "Match in progress"
    if db_match.status == models.MatchStatus.COMPLETED:
        if not innings_2_dels:
            result = f"{team_batting_first} won (opponent did not bat)"
        elif innings_1_runs > innings_2_runs:
            margin = innings_1_runs - innings_2_runs
            result = f"{team_batting_first} won by {margin} run{'s' if margin != 1 else ''}"
        elif innings_2_runs > innings_1_runs:
            wickets_remaining = 10 - innings_2_wickets
            result = f"{team_batting_second} won by {wickets_remaining} wicket{'s' if wickets_remaining != 1 else ''}"
        else:
            result = "Match tied"

    player_of_match = None
    if db_match.player_of_match_id:
        pom = db.query(models.Player).filter(models.Player.id == db_match.player_of_match_id).first()
        if pom:
            player_of_match = {"id": pom.id, "name": pom.name, "team": team_map.get(pom.team_id)}

    return {
        "match_id": match_id,
        "format": db_match.format,
        "venue": db_match.venue,
        "date": db_match.date,
        "status": db_match.status,
        "result": result,
        "team_batting_first": team_batting_first,
        "innings_1_runs": innings_1_runs,
        "team_batting_second": team_batting_second,
        "innings_2_runs": innings_2_runs,
        "player_of_match": player_of_match,
        "fall_of_wickets": fow,
    }
