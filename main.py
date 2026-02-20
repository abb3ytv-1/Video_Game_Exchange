import os
from typing import List, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status, Header, Depends
from sqlmodel import SQLModel, Field, Session, create_engine, select

from kafka import KafkaProducer
import json
import socket

# -------------------- Database Setup --------------------
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://gameuser:gamepass@localhost:5432/videogameexchange"
)

engine = create_engine(DATABASE_URL, echo=True)

# -------------------- Kafka Setup --------------------
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP", "kafka:9092")
_producer = None

def get_kafka_producer():
    """Lazy initialization of Kafka producer with retry logic."""
    global _producer
    if _producer is None:
        import time
        max_retries = 10
        for attempt in range(max_retries):
            try:
                _producer = KafkaProducer(
                    bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                    value_serializer=lambda v: json.dumps(v).encode('utf-8')
                )
                print(f"Connected to Kafka at {KAFKA_BOOTSTRAP_SERVERS}")
                break
            except Exception as e:
                print(f"[Attempt {attempt + 1}/{max_retries}] Failed to connect to Kafka: {e}")
                if attempt < max_retries - 1:
                    time.sleep(5)
                else:
                    print("Warning: Could not connect to Kafka. Notifications disabled.")
    return _producer

def send_email_notification(message: dict):
    """Send a notification message to Kafka for email processing."""
    producer = get_kafka_producer()
    if producer:
        try:
            producer.send("email_notifications", message)
            producer.flush()
            print(f"Notification sent: {message['type']}")
        except Exception as e:
            print(f"Failed to send notification: {e}")
    else:
        print(f"Kafka not available. Notification not sent: {message['type']}")

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

@app.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: int):
    with Session(engine) as session:
        user = session.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        session.delete(user)
        session.commit()

@app.put("/users/{user_id}/password")
def change_password(
    user_id: int,
    new_password: str,
    current_user_id: int = Depends(get_current_user)
):
    if current_user_id != user_id:
        raise HTTPException(403, "You can only change your own password")
    
    with Session(engine) as session:
        user = session.get(User, user_id)
        if not user:
            raise HTTPException(404, "User not found")
        
        user.password = new_password
        session.commit()

        send_email_notification({
            "type": "password_changed",
            "recipients": [user.email],
            "subject": "Password Changed",
            "body": "Your password has been successfully changed."
        })

        return {"message": "Password updated"}

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

        offeror = session.get(User, offer.requester_id)
        offeree = session.get(User, requested_game.owner_id)

        send_email_notification({
            "type": "offer_created",
            "recipients": [offeror.email, offeree.email],
            "subject": "New Trade Offer Created",
            "body": f"A new trade offer has been created for {requested_game.title}."
        })

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

        # Notify both offeror and offeree about status change
        offeror = session.get(User, offer.requester_id)
        offeree = session.get(User, requested_game.owner_id)
        notification_type = f"offer_{status}"
        send_email_notification({
            "type": notification_type,
            "recipients": [offeror.email, offeree.email],
            "subject": f"Offer {status}",
            "body": f"The trade offer for {requested_game.title} has been {status}."
        })

        return offer