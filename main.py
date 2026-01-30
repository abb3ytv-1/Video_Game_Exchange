import os
from typing import List, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status, Header, Depends
from sqlmodel import SQLModel, Field, Session, create_engine, select

import socket

# -------------------- Database Setup --------------------
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://gameuser:gamepass@localhost:5432/videogameexchange"
)

engine = create_engine(DATABASE_URL, echo=True)

# -------------------- Lifespan Event --------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    SQLModel.metadata.create_all(engine)
    yield

# -------------------- App Setup --------------------
app = FastAPI(
    title="Retro Video Game Exchange API",
    version="1.0.0",
    lifespan=lifespan
)

@app.get("/")
def root():
    return {"message": "API is running"}

@app.get("/whoami")
def whoami():
    return {
        "container_name": os.getenv("CONTAINER_NAME", "unknown"),
        "host_name": socket.gethostname()
        }

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
    owner_id: int = Field(foreign_key="user.id")

class TradeOffer(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    # The game the requester is offering
    offered_game_id: int = Field(foreign_key="game.id")
    # The game they want in return
    requested_game_id: int = Field(foreign_key="game.id")
    # Who created the offer
    requester_id: int = Field(foreign_key="user.id")
    # pending | accepted | rejected
    status: str = Field(default="pending", index=True)

# -------------------- Auth Dependency --------------------
def get_current_user(x_user_id: Optional[int] = Header(None)):
    if x_user_id is None:
        raise HTTPException(status_code=401, detail="Missing X-User-ID header")
    return x_user_id

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

@app.put("/offers/{offer_id}")
def update_offer(
    offer_id: int,
    status: str,
    current_user_id: int = Depends(get_current_user)
):
    with Session(engine) as session:
        offer = session.get(TradeOffer, offer_id)
        if not offer:
            raise HTTPException(status_code=404, detail="Offer not found")
        if status not in ["pending", "accepted", "rejected"]:
            raise HTTPException(400, "Invalid status")
        
        # EXTRA CREDIT: Only the requester can update their offer
        if offer.requester_id != current_user_id:
            raise HTTPException(403, "You are not authorized to update this offer")
        
        offer.status = status
        session.commit()
        session.refresh(offer)
        return offer

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

# ------------------ Trade Offers -----------------------------
# Create
@app.post("/offers", response_model=TradeOffer)
def create_offer(offer: TradeOffer, current_user_id: int = Depends(get_current_user)):
    with Session(engine) as session:
        offered_game = session.get(Game, offer.offered_game_id)
        requested_game = session.get(Game, offer.requested_game_id)

        if not offered_game or not requested_game:
            raise HTTPException(404, "Game not found")
        if offered_game.owner_id != current_user_id:
            raise HTTPException(403, "You can only offer your own games")

        offer.requester_id = current_user_id
        session.add(offer)
        session.commit()
        session.refresh(offer)
        return offer

# View offers received for games owned by user
@app.get("/offers", response_model=List[TradeOffer])
def get_offers(current_user_id: int = Depends(get_current_user)):
    with Session(engine) as session:
        return session.exec(
            select(TradeOffer).where(
                TradeOffer.requested_game_id.in_(
                    select(Game.id).where(Game.owner_id == current_user_id)
                )
            )
        ).all()

# Update (extra credit: only requester can update)
@app.put("/offers/{offer_id}")
def update_offer(
    offer_id: int,
    status: str,
    current_user_id: int = Depends(get_current_user)
):
    with Session(engine) as session:
        offer = session.get(TradeOffer, offer_id)
        if not offer:
            raise HTTPException(status_code=404, detail="Offer not found")
        if status not in ["pending", "accepted", "rejected"]:
            raise HTTPException(status_code=400, detail="Invalid status")

        # Only requester or owner of requested game can update
        requested_game = session.get(Game, offer.requested_game_id)
        if current_user_id != offer.requester_id and current_user_id != requested_game.owner_id:
            raise HTTPException(403, detail="You are not authorized to update this offer")

        offer.status = status
        session.commit()
        session.refresh(offer)
        return offer

