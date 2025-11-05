# backend/game-rules-service/main.py
import asyncio
import json
from typing import Dict, List, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
import requests

# -------------------------
# Configuration
# -------------------------
USER_SERVICE_URL = "http://127.0.0.1:8001"   # where User Service runs
ROOM_SERVICE_URL = "http://127.0.0.1:8002"   # where Room Service runs

# -------------------------
# App
# -------------------------
app = FastAPI(title="Game Rules Service (Tic-Tac-Toe)", version="0.1")

# -------------------------
# Helpers: Tic-Tac-Toe logic
# -------------------------
def check_winner(board: List[str]) -> Optional[str]:
    """
    Check the board for a winner.
    board is a list of 9 elements with "", "X" or "O".
    Returns "X" or "O" if there is a winner, "draw" if board full and no winner, or None if game continues.
    """
    lines = [
        (0,1,2), (3,4,5), (6,7,8),  # rows
        (0,3,6), (1,4,7), (2,5,8),  # cols
        (0,4,8), (2,4,6)            # diagonals
    ]
    for a,b,c in lines:
        if board[a] and board[a] == board[b] == board[c]:
            return board[a]  # "X" or "O"
    if all(cell != "" for cell in board):
        return "draw"
    return None

# -------------------------
# Game state in memory
# -------------------------
# Structure per room_id:
# {
#   "board": ["", "", ...],  # 9 items
#   "players": [player_id1, player_id2],  # order of joining
#   "mark_map": {player_id1: "X", player_id2: "O"},
#   "turn": player_id_of_whos_turn,
#   "sockets": {player_id: websocket_obj},
#   "lock": asyncio.Lock()
# }
games: Dict[str, Dict] = {}

# -------------------------
# Utilities: verify user and membership
# -------------------------
def user_exists(user_id: str) -> bool:
    """Checks User Service to ensure the user exists."""
    try:
        r = requests.get(f"{USER_SERVICE_URL}/users/{user_id}", timeout=2)
        return r.status_code == 200
    except requests.RequestException:
        return False

def user_in_room(room_id: str, user_id: str) -> bool:
    """
    Checks Room Service GET /rooms and finds the room,
    then verifies user_id is listed in that room's players.
    This avoids needing a dedicated GET /rooms/{room_id} endpoint.
    """
    try:
        r = requests.get(f"{ROOM_SERVICE_URL}/rooms", timeout=3)
        if r.status_code != 200:
            return False
        rooms = r.json()
        # if rooms endpoint returns message when empty, handle gracefully
        if isinstance(rooms, dict) and rooms.get("message"):
            return False
        for room in rooms:
            if room.get("id") == room_id:
                return user_id in room.get("players", [])
        return False
    except requests.RequestException:
        return False

# -------------------------
# WebSocket endpoint
# -------------------------
@app.websocket("/ws/{room_id}/{player_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str, player_id: str):
    """
    WebSocket entrypoint for players.
    - Validates user exists and is member of the room (via Room Service).
    - Registers the websocket in the game's state.
    - When two players are connected, starts the game and notifies both.
    - Accepts 'move' messages from the client like: {"action":"move","index":4}
    - Broadcasts state updates to both players.
    """
    # Accept the connection
    await websocket.accept()

    # Basic validation: user must exist and be in the room
    if not user_exists(player_id):
        await websocket.send_text(json.dumps({"type":"error","message":"User not found in User Service"}))
        await websocket.close()
        return

    if not user_in_room(room_id, player_id):
        await websocket.send_text(json.dumps({"type":"error","message":"User not in the specified room"}))
        await websocket.close()
        return

    # Register / create game state atomically per room
    if room_id not in games:
        # create new game entry
        games[room_id] = {
            "board": [""]*9,
            "players": [],
            "mark_map": {},
            "turn": None,
            "sockets": {},
            "lock": asyncio.Lock()
        }

    game = games[room_id]

    # Prevent duplicate connections for same player
    if player_id in game["sockets"]:
        await websocket.send_text(json.dumps({"type":"error","message":"Player already connected"}))
        await websocket.close()
        return

    # Add the player to the game players list if not present
    if player_id not in game["players"]:
        game["players"].append(player_id)

    # Save websocket
    game["sockets"][player_id] = websocket

    # Assign marks based on join order: first -> X, second -> O
    if player_id not in game["mark_map"]:
        if len(game["mark_map"]) == 0:
            game["mark_map"][player_id] = "X"
        elif len(game["mark_map"]) == 1:
            game["mark_map"][player_id] = "O"

    # Notify and possibly start the game when we have two players connected
    try:
        if len(game["players"]) == 2 and len(game["sockets"]) == 2:
            # Ensure both players have marks and turn is set
            p1, p2 = game["players"][0], game["players"][1]
            game["mark_map"].setdefault(p1, "X")
            game["mark_map"].setdefault(p2, "O")
            # First player's turn by default
            game["turn"] = p1

            # Send initial game state to both players
            await broadcast_state(room_id, f"Game started. {game['turn']} goes first.")
        else:
            # Inform this player to wait for opponent
            await websocket.send_text(json.dumps({"type":"info","message":"Waiting for opponent..."}))

        # Listen for incoming messages
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({"type":"error","message":"Invalid JSON"}))
                continue

            action = data.get("action")

            if action == "move":
                index = data.get("index")
                await handle_move(room_id, player_id, index)
            else:
                await websocket.send_text(json.dumps({"type":"error","message":"Unknown action"}))

    except WebSocketDisconnect:
        # Remove socket on disconnect
        # If a player disconnects, remove from sockets but keep game state for possible reconnection.
        if room_id in games:
            g = games[room_id]
            if player_id in g["sockets"]:
                del g["sockets"][player_id]
            # optional: notify remaining player
            await notify_remaining_on_disconnect(room_id, player_id)
    except Exception as e:
        # send error and close
        try:
            await websocket.send_text(json.dumps({"type":"error","message":f"Server error: {str(e)}"}))
            await websocket.close()
        except:
            pass


async def handle_move(room_id: str, player_id: str, index: int):
    """
    Handle a move requested by player_id at `index` (0-8).
    Validate turn, index range, and occupancy.
    Update board, check winner/draw, broadcast new state.
    """
    if room_id not in games:
        return
    game = games[room_id]
    async with game["lock"]:
        # validate player part of the game
        if player_id not in game["players"]:
            ws = game["sockets"].get(player_id)
            if ws:
                await ws.send_text(json.dumps({"type":"error","message":"You are not a player in this game"}))
            return

        # validate it's player's turn
        if game["turn"] != player_id:
            ws = game["sockets"].get(player_id)
            if ws:
                await ws.send_text(json.dumps({"type":"error","message":"Not your turn"}))
            return

        # validate index
        if not isinstance(index, int) or index < 0 or index > 8:
            await game["sockets"][player_id].send_text(json.dumps({"type":"error","message":"Invalid index"}))
            return

        if game["board"][index] != "":
            await game["sockets"][player_id].send_text(json.dumps({"type":"error","message":"Cell already occupied"}))
            return

        # perform move
        mark = game["mark_map"].get(player_id)
        game["board"][index] = mark

        # check winner or draw
        result = check_winner(game["board"])
        if result == "X" or result == "O":
            # find which player_id corresponds to this mark
            winner_id = None
            for pid, m in game["mark_map"].items():
                if m == result:
                    winner_id = pid
            # broadcast final state with winner
            await broadcast_state(room_id, f"Player {winner_id} ({result}) wins!", winner=winner_id)
            # reset board for next game
            await reset_game_state(room_id)
            # optionally notify Room Service to reset the room
            try:
                requests.post(f"{ROOM_SERVICE_URL}/rooms/{room_id}/reset", timeout=2)
            except requests.RequestException:
                pass
            return
        elif result == "draw":
            await broadcast_state(room_id, "Draw!", winner="draw")
            await reset_game_state(room_id)
            try:
                requests.post(f"{ROOM_SERVICE_URL}/rooms/{room_id}/reset", timeout=2)
            except requests.RequestException:
                pass
            return
        else:
            # switch turn to the other player
            other = [p for p in game["players"] if p != player_id]
            next_player = other[0] if other else None
            game["turn"] = next_player
            await broadcast_state(room_id, f"Player {player_id} moved. Next: {next_player}")
