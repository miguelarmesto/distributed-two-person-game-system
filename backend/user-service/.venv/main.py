from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, List
from uuid import uuid4
import threading


class UserCreate(BaseModel):
    username: str

class User(BaseModel):
    id: str
    username: str

app = FastAPI(title="User Service", version="0.1")


users: Dict[str, User] = {}
lock = threading.Lock()

@app.post("/users", response_model=User, status_code=201)
def create_user(payload: UserCreate):
    
    with lock:
        if any(u.username == payload.username for u in users.values()):
            raise HTTPException(status_code=400, detail="Username already exists")
        user_id = str(uuid4())
        user = User(id=user_id, username=payload.username)
        users[user_id] = user
    return user

@app.get("/users", response_model=List[User])
def list_users():
    
    return list(users.values())

@app.get("/users/{user_id}", response_model=User)
def get_user(user_id: str):
    
    user = users.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@app.get("/health")
def health():
    
    return {"status": "ok"}