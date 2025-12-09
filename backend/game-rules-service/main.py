# backend/game-rules-service/main.py
import asyncio
import json
from typing import Dict, List, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
import requests


USER_SERVICE_URL = "http://127.0.0.1:8001"   
ROOM_SERVICE_URL = "http://127.0.0.1:8002"   


app = FastAPI(title="Game Rules Service (Tic-Tac-Toe)", version="0.1")


def check_winner(board: List[str]) -> Optional[str]:
    lines = [
        (0,1,2), (3,4,5), (6,7,8),  
        (0,3,6), (1,4,7), (2,5,8),  
        (0,4,8), (2,4,6)            
    ]
    for a,b,c in lines:
        if board[a] and board[a] == board[b] == board[c]:
            return board[a]  # "X" or "O"
    if all(cell != "" for cell in board):
        return "draw"
    return None


games: Dict[str, Dict] = {}


def user_exists(user_id: str) -> bool:
    
    try:
        r = requests.get(f"{USER_SERVICE_URL}/users/{user_id}", timeout=2)
        return r.status_code == 200
    except requests.RequestException:
        return False

def user_in_room(room_id: str, user_id: str) -> bool:
    try:
        r = requests.get(f"{ROOM_SERVICE_URL}/rooms", timeout=3)
        if r.status_code != 200:
            return False
        rooms = r.json()
  
        if isinstance(rooms, dict) and rooms.get("message"):
            return False
        for room in rooms:
            if room.get("id") == room_id:
                return user_id in room.get("players", [])
        return False
    except requests.RequestException:
        return False


@app.websocket("/ws/{room_id}/{player_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str, player_id: str):


    await websocket.accept()


    if not user_exists(player_id):
        await websocket.send_text(json.dumps({"type":"error","message":"User not found in User Service"}))
        await websocket.close()
        return

    if not user_in_room(room_id, player_id):
        await websocket.send_text(json.dumps({"type":"error","message":"User not in the specified room"}))
        await websocket.close()
        return


    if room_id not in games:

        games[room_id] = {
            "board": [""]*9,
            "players": [],
            "mark_map": {},
            "turn": None,
            "sockets": {},
            "lock": asyncio.Lock()
        }

    game = games[room_id]


    if player_id in game["sockets"]:
        await websocket.send_text(json.dumps({"type":"error","message":"Player already connected"}))
        await websocket.close()
        return


    if player_id not in game["players"]:
        game["players"].append(player_id)


    game["sockets"][player_id] = websocket


    if player_id not in game["mark_map"]:
        if len(game["mark_map"]) == 0:
            game["mark_map"][player_id] = "X"
        elif len(game["mark_map"]) == 1:
            game["mark_map"][player_id] = "O"


    try:
        if len(game["players"]) == 2 and len(game["sockets"]) == 2:

            p1, p2 = game["players"][0], game["players"][1]
            game["mark_map"].setdefault(p1, "X")
            game["mark_map"].setdefault(p2, "O")

            game["turn"] = p1


            await broadcast_state(room_id, f"Game started. {game['turn']} goes first.")
        else:

            await websocket.send_text(json.dumps({"type":"info","message":"Waiting for opponent..."}))


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


        if room_id in games:
            g = games[room_id]
            if player_id in g["sockets"]:
                del g["sockets"][player_id]

            await notify_remaining_on_disconnect(room_id, player_id)
    except Exception as e:

        try:
            await websocket.send_text(json.dumps({"type":"error","message":f"Server error: {str(e)}"}))
            await websocket.close()
        except:
            pass


@app.get("/games/{room_id}")
def get_game_state(room_id: str):

    game = games.get(room_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    return {
        "board": game["board"],
        "players": game["players"],
        "turn": game["turn"],
        "mark_map": game["mark_map"],
    }

async def handle_move(room_id: str, player_id: str, index: int):
    if room_id not in games:
        return
    game = games[room_id]
    async with game["lock"]:

        if player_id not in game["players"]:
            ws = game["sockets"].get(player_id)
            if ws:
                await ws.send_text(json.dumps({"type":"error","message":"You are not a player in this game"}))
            return


        if game["turn"] != player_id:
            ws = game["sockets"].get(player_id)
            if ws:
                await ws.send_text(json.dumps({"type":"error","message":"Not your turn"}))
            return


        if not isinstance(index, int) or index < 0 or index > 8:
            await game["sockets"][player_id].send_text(json.dumps({"type":"error","message":"Invalid index"}))
            return

        if game["board"][index] != "":
            await game["sockets"][player_id].send_text(json.dumps({"type":"error","message":"Cell already occupied"}))
            return


        mark = game["mark_map"].get(player_id)
        game["board"][index] = mark


        result = check_winner(game["board"])
        if result == "X" or result == "O":

            winner_id = None
            for pid, m in game["mark_map"].items():
                if m == result:
                    winner_id = pid

            await broadcast_state(room_id, f"Player {winner_id} ({result}) wins!", winner=winner_id)


            asyncio.create_task(delayed_reset(room_id, delay_seconds=3))


            return

        elif result == "draw":
            await broadcast_state(room_id, "Draw!", winner="draw")

            await reset_game_state(room_id)
            return
        else:

            other = [p for p in game["players"] if p != player_id]
            next_player = other[0] if other else None
            game["turn"] = next_player
            await broadcast_state(room_id, f"Player {player_id} moved. Next: {next_player}")

async def delayed_reset(room_id: str, delay_seconds: int = 3):

    await asyncio.sleep(delay_seconds)

    await reset_game_state(room_id)

    await broadcast_state(room_id, "New round started.", winner=None)

async def broadcast_state(room_id: str, message: str, winner: Optional[str]=None):

    game = games.get(room_id)
    if not game:
        return

    payload = {
        "type": "state",
        "message": message,
        "board": game["board"],
        "players": game["players"],
        "turn": game["turn"],
        "mark_map": game["mark_map"],
        "winner": winner
    }


    for pid, ws in list(game["sockets"].items()):
        try:
            await ws.send_text(json.dumps(payload))
        except Exception:

            pass

async def notify_remaining_on_disconnect(room_id: str, disconnected_player: str):

    game = games.get(room_id)
    if not game:
        return
    for pid, ws in list(game["sockets"].items()):
        if pid != disconnected_player:
            try:
                await ws.send_text(json.dumps({"type":"info","message":f"Opponent {disconnected_player} disconnected."}))
            except:
                pass

async def reset_game_state(room_id: str):

    game = games.get(room_id)
    if not game:
        return
    game["board"] = [""] * 9
    if game["players"]:
        game["turn"] = game["players"][0]
    else:
        game["turn"] = None


@app.delete("/games/{room_id}")
def delete_game(room_id: str):

    if room_id in games:
        del games[room_id]
        return {"message": "Game state cleared"}
    else:
        raise HTTPException(status_code=404, detail="Game not found")