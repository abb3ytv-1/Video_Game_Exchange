import os
import time
import hashlib
from typing import List, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status, Header, Depends
from sqlmodel import SQLModel, Field, Session, create_engine, select
from sqlalchemy.exc import OperationalError
from prometheus_fastapi_instrumentator import Instrumentator
from prometheus_client import Counter, Histogram
from kafka import KafkaProducer
import json
import socket

# -------------------- Shard Configuration --------------------
NUM_SHARDS = 2
SHARD_URLS = [
    os.getenv("SHARD0_URL", "postgresql://gameuser:passgame@postgres_shard0:5432/videogameexchange"),
    os.getenv("SHARD1_URL", "postgresql://gameuser:passgame@postgres_shard1:5432/videogameexchange"),
]

# pool_pre_ping=True detects stale connections so partial-availability works cleanly
SHARD_ENGINES = [
    create_engine(url, echo=True, pool_pre_ping=True)
    for url in SHARD_URLS
]

def get_shard_index(entity_id: int) -> int:
    """Return which shard owns this ID.  Works for user, game, and offer IDs
    because each shard's PostgreSQL sequences are configured to produce only
    even (shard 0) or odd (shard 1) values."""
    return entity_id % NUM_SHARDS

def get_shard_engine(entity_id: int):
    return SHARD_ENGINES[get_shard_index(entity_id)]

def get_creation_shard(email: str) -> int:
    """Deterministic shard for new users: stable MD5 hash of email.
    hashlib is used instead of hash() to avoid Python's per-process seed."""
    return int(hashlib.md5(email.encode()).hexdigest(), 16) % NUM_SHARDS

# -------------------- Prometheus Shard Metrics --------------------
shard_queries_total = Counter(
    "shard_queries_total",
    "Total queries routed to each shard",
    ["shard_index", "operation"]
)

cross_shard_ops_total = Counter(
    "cross_shard_operations_total",
    "Operations that required querying multiple shards (scatter-gather)",
    ["operation"]
)

shard_query_duration_seconds = Histogram(
    "shard_query_duration_seconds",
    "Query latency per shard in seconds",
    ["shard_index", "operation"]
)

# -------------------- Kafka Setup --------------------
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP", "kafka:9092")
_producer = None

def get_kafka_producer():
    """Lazy initialization of Kafka producer with retry logic."""
    global _producer
    if _producer is None:
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
    # create_all is a no-op when init SQL has already created the tables.
    # It ensures tables exist if the app is run outside Docker without init SQL.
    for engine in SHARD_ENGINES:
        SQLModel.metadata.create_all(engine)
    yield

# -------------------- App Setup --------------------
app = FastAPI(
    title="Retro Video Game Exchange API",
    version="2.0.0",
    lifespan=lifespan
)

# Expose /metrics endpoint for Prometheus
Instrumentator().instrument(app).expose(app)

@app.get("/")
def root():
    return {"message": "API is running (sharded)"}

@app.get("/whoami")
def whoami():
    return {
        "container_name": os.getenv("CONTAINER_NAME", "unknown"),
        "host_name": socket.gethostname()
    }

@app.get("/shards")
def shard_info():
    """Returns shard topology. Useful for demonstrating the routing strategy."""
    return {
        "num_shards": NUM_SHARDS,
        "routing": "entity_id % num_shards",
        "id_assignment": "shard 0 = even IDs, shard 1 = odd IDs (interleaved sequences)",
        "shards": [
            {"index": i, "host": url.split("@")[-1] if "@" in url else url}
            for i, url in enumerate(SHARD_URLS)
        ]
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
    # Assign shard deterministically by email hash so it is stable across
    # API-container restarts (hashlib.md5 unlike Python's hash() is not seeded).
    target_shard = get_creation_shard(user.email)
    t0 = time.time()
    shard_queries_total.labels(shard_index=str(target_shard), operation="user_create").inc()
    try:
        with Session(SHARD_ENGINES[target_shard]) as session:
            session.add(user)
            session.commit()
            session.refresh(user)
            return user
    except OperationalError:
        raise HTTPException(503, detail={"error": "Shard unavailable", "shard": target_shard})
    finally:
        shard_query_duration_seconds.labels(
            shard_index=str(target_shard), operation="user_create"
        ).observe(time.time() - t0)

@app.get("/users", response_model=List[User])
def get_users():
    # Scatter-gather: collect from all shards
    results = []
    for i, engine in enumerate(SHARD_ENGINES):
        t0 = time.time()
        shard_queries_total.labels(shard_index=str(i), operation="user_list").inc()
        try:
            with Session(engine) as session:
                results.extend(session.exec(select(User)).all())
        except OperationalError:
            pass  # Partial availability: skip downed shard, return the rest
        finally:
            shard_query_duration_seconds.labels(
                shard_index=str(i), operation="user_list"
            ).observe(time.time() - t0)
    return results

@app.get("/users/{user_id}", response_model=User)
def get_user(user_id: int):
    shard = get_shard_index(user_id)
    t0 = time.time()
    shard_queries_total.labels(shard_index=str(shard), operation="user_get").inc()
    try:
        with Session(get_shard_engine(user_id)) as session:
            user = session.get(User, user_id)
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
            return user
    except OperationalError:
        raise HTTPException(503, detail={"error": "Shard unavailable", "shard": shard})
    finally:
        shard_query_duration_seconds.labels(
            shard_index=str(shard), operation="user_get"
        ).observe(time.time() - t0)

@app.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: int):
    shard = get_shard_index(user_id)
    shard_queries_total.labels(shard_index=str(shard), operation="user_delete").inc()
    try:
        with Session(get_shard_engine(user_id)) as session:
            user = session.get(User, user_id)
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
            session.delete(user)
            session.commit()
    except OperationalError:
        raise HTTPException(503, detail={"error": "Shard unavailable", "shard": shard})

@app.put("/users/{user_id}/password")
def change_password(
    user_id: int,
    new_password: str,
    current_user_id: int = Depends(get_current_user)
):
    if current_user_id != user_id:
        raise HTTPException(403, "You can only change your own password")
    shard = get_shard_index(user_id)
    shard_queries_total.labels(shard_index=str(shard), operation="user_update").inc()
    try:
        with Session(get_shard_engine(user_id)) as session:
            user = session.get(User, user_id)
            if not user:
                raise HTTPException(404, "User not found")
            user.password = new_password
            session.commit()
            user_email = user.email
        send_email_notification({
            "type": "password_changed",
            "recipients": [user_email],
            "subject": "Password Changed",
            "body": "Your password has been successfully changed."
        })
        return {"message": "Password updated"}
    except OperationalError:
        raise HTTPException(503, detail={"error": "Shard unavailable", "shard": shard})

# -------------------- Game Endpoints --------------------
@app.post("/games", response_model=Game, status_code=status.HTTP_201_CREATED)
def create_game(game: Game):
    # Games are co-located with their owner on the same shard
    shard = get_shard_index(game.owner_id)
    t0 = time.time()
    shard_queries_total.labels(shard_index=str(shard), operation="game_create").inc()
    try:
        with Session(SHARD_ENGINES[shard]) as session:
            owner = session.get(User, game.owner_id)
            if not owner:
                raise HTTPException(status_code=400, detail="Owner does not exist")
            session.add(game)
            session.commit()
            session.refresh(game)
            return game
    except OperationalError:
        raise HTTPException(503, detail={"error": "Shard unavailable", "shard": shard})
    finally:
        shard_query_duration_seconds.labels(
            shard_index=str(shard), operation="game_create"
        ).observe(time.time() - t0)

@app.get("/games", response_model=List[Game])
def get_games():
    # Scatter-gather across all shards
    results = []
    for i, engine in enumerate(SHARD_ENGINES):
        t0 = time.time()
        shard_queries_total.labels(shard_index=str(i), operation="game_list").inc()
        try:
            with Session(engine) as session:
                results.extend(session.exec(select(Game)).all())
        except OperationalError:
            pass
        finally:
            shard_query_duration_seconds.labels(
                shard_index=str(i), operation="game_list"
            ).observe(time.time() - t0)
    return results

# NOTE: /games/search MUST be registered before /games/{game_id}.
# FastAPI matches routes in order; without this, "search" is captured as game_id.
@app.get("/games/search", response_model=List[Game])
def search_games(title: Optional[str] = None, owner_id: Optional[int] = None):
    if owner_id is not None:
        # We know the shard — route directly
        shard = get_shard_index(owner_id)
        shard_queries_total.labels(shard_index=str(shard), operation="game_search").inc()
        try:
            with Session(SHARD_ENGINES[shard]) as session:
                query = select(Game).where(Game.owner_id == owner_id)
                if title:
                    query = query.where(Game.title.ilike(f"%{title}%"))
                return session.exec(query).all()
        except OperationalError:
            raise HTTPException(503, detail={"error": "Shard unavailable", "shard": shard})
    else:
        # No shard key — scatter-gather
        cross_shard_ops_total.labels(operation="game_search").inc()
        results = []
        for i, engine in enumerate(SHARD_ENGINES):
            shard_queries_total.labels(shard_index=str(i), operation="game_search").inc()
            try:
                with Session(engine) as session:
                    query = select(Game)
                    if title:
                        query = query.where(Game.title.ilike(f"%{title}%"))
                    results.extend(session.exec(query).all())
            except OperationalError:
                pass
        return results

@app.get("/games/{game_id}", response_model=Game)
def get_game(game_id: int):
    # game_id encodes its shard (interleaved sequences guarantee this)
    shard = get_shard_index(game_id)
    t0 = time.time()
    shard_queries_total.labels(shard_index=str(shard), operation="game_get").inc()
    try:
        with Session(SHARD_ENGINES[shard]) as session:
            game = session.get(Game, game_id)
            if not game:
                raise HTTPException(status_code=404, detail="Game not found")
            return game
    except OperationalError:
        raise HTTPException(503, detail={"error": "Shard unavailable", "shard": shard})
    finally:
        shard_query_duration_seconds.labels(
            shard_index=str(shard), operation="game_get"
        ).observe(time.time() - t0)

@app.put("/games/{game_id}", response_model=Game)
def update_game(game_id: int, updated_game: Game):
    shard = get_shard_index(game_id)
    shard_queries_total.labels(shard_index=str(shard), operation="game_update").inc()
    try:
        with Session(SHARD_ENGINES[shard]) as session:
            game = session.get(Game, game_id)
            if not game:
                raise HTTPException(status_code=404, detail="Game not found")
            game.title = updated_game.title
            game.platform = updated_game.platform
            game.owner_id = updated_game.owner_id
            session.commit()
            session.refresh(game)
            return game
    except OperationalError:
        raise HTTPException(503, detail={"error": "Shard unavailable", "shard": shard})

@app.delete("/games/{game_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_game(game_id: int):
    shard = get_shard_index(game_id)
    shard_queries_total.labels(shard_index=str(shard), operation="game_delete").inc()
    try:
        with Session(SHARD_ENGINES[shard]) as session:
            game = session.get(Game, game_id)
            if not game:
                raise HTTPException(status_code=404, detail="Game not found")
            session.delete(game)
            session.commit()
    except OperationalError:
        raise HTTPException(503, detail={"error": "Shard unavailable", "shard": shard})

# -------------------- Trade Offer Endpoints --------------------
@app.post("/offers", response_model=TradeOffer)
def create_offer(offer: TradeOffer, current_user_id: int = Depends(get_current_user)):
    offered_shard  = get_shard_index(offer.offered_game_id)
    requested_shard = get_shard_index(offer.requested_game_id)

    if offered_shard != requested_shard:
        # Scatter-gather: the two games live on different shards
        cross_shard_ops_total.labels(operation="offer_create").inc()

    # --- Fetch offered game ---
    shard_queries_total.labels(shard_index=str(offered_shard), operation="offer_create_fetch").inc()
    try:
        with Session(SHARD_ENGINES[offered_shard]) as session:
            offered_game = session.get(Game, offer.offered_game_id)
            offered_owner_id = offered_game.owner_id if offered_game else None
    except OperationalError:
        raise HTTPException(503, detail={"error": "Shard unavailable", "shard": offered_shard})

    # --- Fetch requested game (possibly on a different shard) ---
    shard_queries_total.labels(shard_index=str(requested_shard), operation="offer_create_fetch").inc()
    try:
        with Session(SHARD_ENGINES[requested_shard]) as session:
            requested_game = session.get(Game, offer.requested_game_id)
            requested_owner_id = requested_game.owner_id if requested_game else None
            requested_title    = requested_game.title    if requested_game else None
    except OperationalError:
        raise HTTPException(503, detail={"error": "Shard unavailable", "shard": requested_shard})

    if offered_game is None or requested_game is None:
        raise HTTPException(404, "Game not found")
    if offered_owner_id != current_user_id:
        raise HTTPException(403, "You can only offer your own games")

    # --- Store the offer on the requester's shard ---
    requester_shard = get_shard_index(current_user_id)
    offer.requester_id = current_user_id
    shard_queries_total.labels(shard_index=str(requester_shard), operation="offer_create").inc()
    try:
        with Session(SHARD_ENGINES[requester_shard]) as session:
            session.add(offer)
            session.commit()
            session.refresh(offer)
            saved_offer = offer
    except OperationalError:
        raise HTTPException(503, detail={"error": "Shard unavailable", "shard": requester_shard})

    # --- Fetch user emails for notifications (possibly cross-shard) ---
    offeror_email, offeree_email = None, None
    try:
        with Session(SHARD_ENGINES[get_shard_index(current_user_id)]) as session:
            offeror = session.get(User, current_user_id)
            offeror_email = offeror.email if offeror else None
    except OperationalError:
        pass
    try:
        with Session(SHARD_ENGINES[get_shard_index(requested_owner_id)]) as session:
            offeree = session.get(User, requested_owner_id)
            offeree_email = offeree.email if offeree else None
    except OperationalError:
        pass

    recipients = [e for e in [offeror_email, offeree_email] if e]
    if recipients:
        send_email_notification({
            "type": "offer_created",
            "recipients": recipients,
            "subject": "New Trade Offer Created",
            "body": f"A new trade offer has been created for {requested_title}."
        })

    return saved_offer

# View offers received for games owned by the current user
@app.get("/offers", response_model=List[TradeOffer])
def get_offers(current_user_id: int = Depends(get_current_user)):
    # Step 1: fetch owned game IDs from the user's shard
    user_shard = get_shard_index(current_user_id)
    shard_queries_total.labels(shard_index=str(user_shard), operation="offers_game_ids").inc()
    try:
        with Session(SHARD_ENGINES[user_shard]) as session:
            owned_game_ids = [
                g.id for g in session.exec(
                    select(Game).where(Game.owner_id == current_user_id)
                ).all()
            ]
    except OperationalError:
        raise HTTPException(503, detail={"error": "Shard unavailable", "shard": user_shard})

    if not owned_game_ids:
        return []

    # Step 2: scatter to all shards — offer requesters can be on any shard
    cross_shard_ops_total.labels(operation="offers_list").inc()
    results = []
    for i, engine in enumerate(SHARD_ENGINES):
        shard_queries_total.labels(shard_index=str(i), operation="offers_list").inc()
        try:
            with Session(engine) as session:
                results.extend(
                    session.exec(
                        select(TradeOffer).where(
                            TradeOffer.requested_game_id.in_(owned_game_ids)
                        )
                    ).all()
                )
        except OperationalError:
            pass
    return results

@app.put("/offers/{offer_id}")
def update_offer(
    offer_id: int,
    status: str,
    current_user_id: int = Depends(get_current_user)
):
    if status not in ["pending", "accepted", "rejected"]:
        raise HTTPException(status_code=400, detail="Invalid status")

    offer_shard = get_shard_index(offer_id)
    shard_queries_total.labels(shard_index=str(offer_shard), operation="offer_update_fetch").inc()

    # Step 1: Fetch the offer from its shard to get game references
    try:
        with Session(SHARD_ENGINES[offer_shard]) as session:
            offer = session.get(TradeOffer, offer_id)
            if not offer:
                raise HTTPException(404, "Offer not found")
            offer_requester_id      = offer.requester_id
            offer_requested_game_id = offer.requested_game_id
    except OperationalError:
        raise HTTPException(503, detail={"error": "Shard unavailable", "shard": offer_shard})

    # Step 2: Fetch requested game for authorization (may be on a different shard)
    requested_game_shard = get_shard_index(offer_requested_game_id)
    if requested_game_shard != offer_shard:
        cross_shard_ops_total.labels(operation="offer_update").inc()
    shard_queries_total.labels(
        shard_index=str(requested_game_shard), operation="offer_update_fetch"
    ).inc()
    try:
        with Session(SHARD_ENGINES[requested_game_shard]) as session:
            requested_game = session.get(Game, offer_requested_game_id)
            if not requested_game:
                raise HTTPException(404, "Requested game not found")
            rg_owner_id = requested_game.owner_id
            rg_title    = requested_game.title
    except OperationalError:
        raise HTTPException(503, detail={"error": "Shard unavailable", "shard": requested_game_shard})

    # Step 3: Authorization
    if current_user_id != offer_requester_id and current_user_id != rg_owner_id:
        raise HTTPException(403, "You are not authorized to update this offer")

    # Step 4: Apply the status update
    shard_queries_total.labels(shard_index=str(offer_shard), operation="offer_update").inc()
    try:
        with Session(SHARD_ENGINES[offer_shard]) as session:
            offer = session.get(TradeOffer, offer_id)
            offer.status = status
            session.commit()
            session.refresh(offer)
            updated_offer = offer
    except OperationalError:
        raise HTTPException(503, detail={"error": "Shard unavailable", "shard": offer_shard})

    # Step 5: Notifications (users may be on different shards)
    offeror_email, offeree_email = None, None
    try:
        with Session(SHARD_ENGINES[get_shard_index(offer_requester_id)]) as session:
            offeror = session.get(User, offer_requester_id)
            offeror_email = offeror.email if offeror else None
    except OperationalError:
        pass
    try:
        with Session(SHARD_ENGINES[get_shard_index(rg_owner_id)]) as session:
            offeree = session.get(User, rg_owner_id)
            offeree_email = offeree.email if offeree else None
    except OperationalError:
        pass

    recipients = [e for e in [offeror_email, offeree_email] if e]
    if recipients:
        send_email_notification({
            "type": f"offer_{status}",
            "recipients": recipients,
            "subject": f"Offer {status}",
            "body": f"The trade offer for {rg_title} has been {status}."
        })

    return updated_offer
