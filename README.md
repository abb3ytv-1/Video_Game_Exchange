# Video Game Exchange API Client

A Python client library for accessing the Retro Video Game Exchange API, now deployed in a multi-node setup with load balancing via NGINX.

---

### Architecture Overview

The API is deployed across three FastAPI containers with NGINX acting as a load balancer, distributing requests in a round-robin fashion. All API instances share the same PostgreSQL database for consistent data storage.
```
          ┌────────────┐
          │  NGINX LB  │
          │  (Port 80) │
          └─────┬──────┘
                │
       ┌────────┴────────┐
       │        │        │
 ┌──────┐  ┌──────┐  ┌──────┐
 │ API1 │  │ API2 │  │ API3 │
 │(8000)│  │(8000)│  │(8000)│
 └──────┘  └──────┘  └──────┘
       │        │        │
       └────────┴────────┘
             PostgreSQL
            
*This diagram was created using AI
```

NGINX only forwards traffic within the Docker network.

`/whoami` can be used to verify which container handled the request.

**Example responses:**

```
{"container_name":"api1","host_name":"fc6eed3344b3"}
{"container_name":"api2","host_name":"b22e8655ae78"}
{"container_name":"api3","host_name":"c3f9b18ae4f4"}
```

### Installation & Setup

**Install the client library:**

```
pip install video-game-exchange-api-client
```

### Usage

**Create a client**

```
from video_game_exchange_api_client import Client

client = Client(base_url="http://localhost:8080")  # points to NGINX load balancer
```

If authentication is required:

```
from video_game_exchange_api_client import AuthenticatedClient

client = AuthenticatedClient(base_url="http://localhost:8080", token="SuperSecretToken")
```

---

### Accessing Endpoints
**1. Get all users**

```
from video_game_exchange_api_client.api.users import get_users

with client as c:
    users = get_users.sync(client=c)
    print(users)
```

**2. Create a trade offer (authenticated)**

```
from video_game_exchange_api_client.api.offers import create_offer

offer_data = {
    "offered_game_id": 1,
    "requested_game_id": 2,
    "requester_id": 1  # X-User-ID in header
}

with client as c:
    offer = create_offer.sync(client=c, json_body=offer_data)
    print(offer)
```

**3. Update a trade offer (EXTRA CREDIT: only requester can update)**

```
from video_game_exchange_api_client.api.offers import update_offer

update_data = {"status": "accepted"}

with client as c:
    updated_offer = update_offer.sync(client=c, offer_id=1, json_body=update_data)
    print(updated_offer)
```

**4. View offers received**

```
from video_game_exchange_api_client.api.offers import get_offers

with client as c:
    offers = get_offers.sync(client=c, user_id=2)
    print(offers)
```

---

### Using `curl` to test load balancing

```
curl http://localhost:8080/whoami
curl -X POST http://localhost:8080/users \
-H "Content-Type: application/json" \
-d '{"name":"Abbey","email":"abbey@example.com","password":"pass123","address":"123 Street"}'
curl -X POST http://localhost:8080/offers \
-H "Content-Type: application/json" \
-H "X-User-ID: 1" \
-d '{"offered_game_id":1,"requested_game_id":2}'
curl -X PUT http://localhost:8080/offers/1 \
-H "Content-Type: application/json" \
-H "X-User-ID: 1" \
-d '{"status":"accepted"}'
curl http://localhost:8080/offers?user_id=2
```

---

### Advanced Customizations

You can pass **httpx arguments** to the client for logging, SSL, or custom headers:

```
from video_game_exchange_api_client import Client

def log_request(request):
    print(f"Request: {request.method} {request.url}")

def log_response(response):
    print(f"Response: {response.status_code} from {response.request.url}")

client = Client(
    base_url="http://localhost:8080",
    httpx_args={"event_hooks": {"request": [log_request], "response": [log_response]}}
)
```

---

### Installing Dependencies

This project uses a `requirements.txt` file. Install dependencies with:

```
pip install -r requirements.txt
```

Or install the client in another project (for development):

```
pip install .
```

---

### Multi-Node Deployment Notes

- The API can run in multiple Docker containers (e.g., `api1`, `api2`, `api3`)

- NGINX acts as a load balancer forwarding requests across containers

- Requests to `/whoami` can help verify round-robin behavior across nodes

- All users, games, and trade offers are persisted in a single PostgreSQL database