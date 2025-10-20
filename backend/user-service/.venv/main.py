from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, List
from uuid import uuid4
import threading

# --- Modelos ---
class UserCreate(BaseModel):
    username: str

class User(BaseModel):
    id: str
    username: str

# --- App principal ---
app = FastAPI(title="User Service", version="0.1")

# --- Almacenamiento temporal en memoria ---
users: Dict[str, User] = {}
lock = threading.Lock()

# --- Endpoints ---
@app.post("/users", response_model=User, status_code=201)
def create_user(payload: UserCreate):
    """
    Crea un usuario si el nombre de usuario no existe.
    """
    with lock:
        if any(u.username == payload.username for u in users.values()):
            raise HTTPException(status_code=400, detail="Username already exists")
        user_id = str(uuid4())
        user = User(id=user_id, username=payload.username)
        users[user_id] = user
    return user

@app.get("/users", response_model=List[User])
def list_users():
    """Lista todos los usuarios"""
    return list(users.values())

@app.get("/users/{user_id}", response_model=User)
def get_user(user_id: str):
    """Devuelve un usuario por su id(404 si no existe)"""
    user = users.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@app.get("/health")
def health():
    """Endpoint para comprobar que el servicio está corriendo"""
    return {"status": "ok"}