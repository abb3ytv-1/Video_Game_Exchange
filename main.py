import os
from typing import List, Optional
from fastapi import FastAPI, HTTPException, status
from sqlmodel import SQLModel, Field, Session, create_engine, select

# -------------------- App Setup --------------------
app = FastAPI(
    title="Retro Video Game Exchange API",
    version="1.0.0"
)

@app.get("/")
def root():
    return {"message": "API is running"}

# -------------------- Database Setup --------------------
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///database.db")
engine = create_engine(DATABASE_URL, echo=True)

# -------------------- Models --------------------
class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    email: str
    password: str
    address: str

class Game(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    platform: str
    owner_id: int

SQLModel.metadata.create_all(engine)

# -------------------- User Endpoints --------------------
@app.post("/users", response_model=User, status_code=status.HTTP_201_CREATED)
def create_user(user: User):
    with Session(engine) as session:
        session.add(user)
        session.commit()
        session.refresh(user)
        return user

@app.get("/users", response_model=List[User])
def get_users():
    with Session(engine) as session:
        return session.exec(select(User)).all()

@app.get("/users/{user_id}", response_model=User)
def get_user(user_id: int):
    with Session(engine) as session:
        user = session.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return user

@app.put("/users/{user_id}", response_model=User)
def update_user(user_id: int, updated_user: User):
    with Session(engine) as session:
        user = session.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        user.name = updated_user.name
        user.email = updated_user.email
        user.password = updated_user.password
        user.address = updated_user.address
        session.commit()
        session.refresh(user)
        return user

@app.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: int):
    with Session(engine) as session:
        user = session.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        session.delete(user)
        session.commit()

# -------------------- Game Endpoints --------------------
@app.post("/games", response_model=Game, status_code=status.HTTP_201_CREATED)
def create_game(game: Game):
    with Session(engine) as session:
        owner = session.get(User, game.owner_id)
        if not owner:
            raise HTTPException(status_code=400, detail="Owner does not exist")
        session.add(game)
        session.commit()
        session.refresh(game)
        return game

@app.get("/games", response_model=List[Game])
def get_games():
    with Session(engine) as session:
        return session.exec(select(Game)).all()

@app.get("/games/{game_id}", response_model=Game)
def get_game(game_id: int):
    with Session(engine) as session:
        game = session.get(Game, game_id)
        if not game:
            raise HTTPException(status_code=404, detail="Game not found")
        return game

@app.put("/games/{game_id}", response_model=Game)
def update_game(game_id: int, updated_game: Game):
    with Session(engine) as session:
        game = session.get(Game, game_id)
        if not game:
            raise HTTPException(status_code=404, detail="Game not found")
        game.title = updated_game.title
        game.platform = updated_game.platform
        game.owner_id = updated_game.owner_id
        session.commit()
        session.refresh(game)
        return game

@app.delete("/games/{game_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_game(game_id: int):
    with Session(engine) as session:
        game = session.get(Game, game_id)
        if not game:
            raise HTTPException(status_code=404, detail="Game not found")
        session.delete(game)
        session.commit()

# -------------------- Game Search --------------------
@app.get("/games/search", response_model=List[Game])
def search_games(title: Optional[str] = None, owner_id: Optional[int] = None):
    with Session(engine) as session:
        query = select(Game)
        if title:
            query = query.where(Game.title.ilike(f"%{title}%"))
        if owner_id:
            query = query.where(Game.owner_id == owner_id)
        return session.exec(query).all()
