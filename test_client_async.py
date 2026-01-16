import asyncio
from app.video_game_exchange_api_client import Client
from app.video_game_exchange_api_client.api.default import (
    create_user,
    get_users,
    create_game,
    get_games
)
from app.video_game_exchange_api_client.models import Game, User

async def main():
    # create a client
    async with Client(base_url="http://localhost:8000") as client:
        # create a new user
        new_user = User(username="gamer123", email="inviteinfinity@gmail.com")
        user_response = await create_user.asyncio(client=client, json_body=new_user)
        print("Created User:", user_response)

        # create a new game
        new_game = Game(title="Retro Racer", platform="NES", owner_id=user_response.id)
        game_response = await create_game.asyncio(client=client, json_body=new_game)
        print("Created Game:", game_response)

        # get all users
        all_users = await get_users.asyncio(client=client)
        print("All Users:", all_users)

        # get all games
        all_games = await get_games.asyncio(client=client)
        print("All Games:", all_games)

# Run the async main function
asyncio.run(main())