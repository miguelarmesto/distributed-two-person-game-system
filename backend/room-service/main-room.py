from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, List
import requests
from uuid import uuid4
import threading

# --- Modelos ---
class RoomCreate(BaseModel):
    name: str
    host_id: str   # ID del usuario que crea la sala

class Room(BaseModel):
    id: str
    name: str
    players: List[str]  # lista de IDs de usuarios
    status: str         # "waiting" o "full"

# --- App ---
app = FastAPI(title="Room Service", version="0.1")

# --- Almacenamiento temporal ---
rooms: Dict[str, Room] = {}
lock = threading.Lock()

# --- Constante del User Service ---
USER_SERVICE_URL = "http://127.0.0.1:8001"

# --- Función auxiliar ---
def verify_user_exists(user_id: str):
    """Consulta el User Service para comprobar que un usuario existe."""
    try:
        r = requests.get(f"{USER_SERVICE_URL}/users/{user_id}", timeout=2)
        if r.status_code == 404:
            raise HTTPException(status_code=404, detail="User not found")
        elif r.status_code != 200:
            raise HTTPException(status_code=500, detail="User service error")
    except requests.ConnectionError:
        raise HTTPException(status_code=503, detail="User service unavailable")

# --- Endpoints ---
@app.post("/rooms", response_model=Room, status_code=201)
def create_room(payload: RoomCreate):
    """Crea una nueva sala, verificando que el usuario anfitrión existe."""
    verify_user_exists(payload.host_id)

    with lock:
        room_id = str(uuid4())
        room = Room(id=room_id, name=payload.name, players=[payload.host_id], status="waiting")
        rooms[room_id] = room
    return room

@app.get("/rooms", response_model=List[Room])
def list_rooms():
    """Lista todas las salas."""
    return list(rooms.values())

@app.post("/rooms/{room_id}/join/{user_id}", response_model=Room)
def join_room(room_id: str, user_id: str):
    """Permite a un usuario unirse a una sala si no está llena."""
    verify_user_exists(user_id)

    room = rooms.get(room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    if user_id in room.players:
        raise HTTPException(status_code=400, detail="User already in room")

    if len(room.players) >= 2:
        raise HTTPException(status_code=400, detail="Room is full")

    room.players.append(user_id)
    room.status = "full" if len(room.players) == 2 else "waiting"
    return room

@app.get("/health")
def health():
    return {"status": "ok"}