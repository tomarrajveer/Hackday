from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from database import engine, Base, get_db
from routers import users, matches, scoring, stats
import auth
import schemas
from datetime import timedelta

# Create database tables (in production use alembic migrations instead)
Base.metadata.create_all(bind=engine)

app = FastAPI(title="CricBuzz Live Match Tracker API")

# Include Routers
app.include_router(users.router)
app.include_router(matches.router)
app.include_router(scoring.router)
app.include_router(stats.router)

@app.post("/token", response_model=schemas.Token)
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = auth.get_user_by_username(db, username=form_data.username)
    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=auth.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth.create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/")
def root():
    return {"message": "Welcome to CricBuzz Live Match Tracker API"}
