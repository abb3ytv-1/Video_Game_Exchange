from app.video_game_exchange_api_client import Client
from app.video_game_exchange_api_client.api.default import (
    create_user,
    get_users,
    create_game,
    get_games,
)
from app.video_game_exchange_api_client.models import Game, User

# Create a client
client = Client(base_url="http://localhost:8000")

# Create a new user
new_user = User(username="gamer123", email="inviteinfinity@gmail.com")
user_response = create_user.sync(client=client, json_body=new_user)
print("Created User:", user_response)

# Create a new game
new_game - Game(title="Retro Racer", platform="NES", owner_id=user_response.id)
game_response = create_game.sync(client=client, json_body=new_game)
print("Created Game:", game_response)

# Ger all users
all_users = get_users.sync(client=client)
print("All Users:", all_users)

# Get all games
all_games = get_games.sync(client=client)
print("All Games:", all_games)