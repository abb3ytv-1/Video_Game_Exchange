from fastapi import FastAPI
from typing import List
from pydantic import BaseModel

app = FastAPI(
    title="Retro Video Game Exchange API",
    version="1.0.0"
)

@app.get("/")
def root():
    return {"message": "API is running"}

class User(BaseModel):
    id: int
    username: str

class Game(BaseModel):
    id: int
    title: str
    platform: str
    owner_id: int

users: List[User] = []
games: List[Game] = []

@app.post("/users", response_model=User)
def create_user(user: User):
    users.append(user)
    return user

@app.get("/users", response_model=List[User])
def get_users():
    return users

@app.post("/games", response_model=Game)
def create_game(game: Game):
    games.append(game)
    return game

@app.get("/games", response_model=List[Game])
def get_games():
    return games