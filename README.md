# 🕹️ Distributed Two-Person Game System  
### Final Project – Programming 5



The system includes:

- **User Service** (Python + FastAPI)
- **Room Service** (Python + FastAPI)
- **Game Rules Service – Tic Tac Toe** (Python + FastAPI + WebSockets)
- **CLI Client** (Python)
- **Web Client** (HTML + JavaScript)

Everything is stored in a single **monorepo**.

---

## 📁 Repository Structure

 Each backend microservice uses its own virtual environment.

 ### User service
```
cd backend/user-service
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install fastapi uvicorn
uvicorn main:app --reload --port 8001
```
 ### Room service
```
cd backend/room-service
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install fastapi uvicorn
uvicorn main:app --reload --port 8002
```
 ### Game rules service
```
cd backend/game-rules-service
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install fastapi uvicorn
uvicorn main:app --reload --port 8003
```
### Run the CLI client
```
cd clients/cli
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install websocket-client
python main.py
```
### Run the Web client
```
clients/web/index.html
```

## Backend Microservices Overview

All services run independently and communicate using HTTP.
The game logic uses WebSockets for real-time updates.

### User Service ```(backend/user-service/main.py)```
**Purpose**

Handles player creation and stores user data in memory.

**Endpoints**

POST /users
Creates a new user and returns its unique user_id.

GET /users
Returns all registered users.

GET /users/{user_id}
Check a specific user by their ID.

### Room Service ```(backend/room-service/main.py)```
**Purpose**

Manages game rooms and assigns players to them.

**Features**

- Create rooms

- Add players (max 2)

- Prevent a player from joining multiple rooms

- Reset a room for a new match

- List all rooms

**Endpoints**

POST /rooms – create a room

POST /rooms/{id}/join – add player to room

GET /rooms – list rooms

POST /rooms/{id}/reset – reset room state

### Game Rules Service – Tic Tac Toe ```(backend/game-rules-service/main.py)```
**Purpose**

Implements the actual gameplay and manages live communication.

**Features**

- Validates moves

- Tracks turns

- Detects wins and draws

- Broadcasts board state via WebSockets

- Sends final board before resetting

- Automatically starts new rounds

**WebSocket Endpoint**
```
ws://localhost:8003/ws/{room_id}/{player_id}
```

**Messages**

Clients receive JSON like:
```
{
  "type": "state",
  "board": ["X", "", "O", ...],
  "turn": "player1",
  "winner": null,
  "message": "Player X moved"
}
```

**Endpoints**

GET /game/{room_id} - Returns the current full game state for the given room.

DELETE /game/{room_id} - Deletes the current game state for a room.

## Client Applications

### CLI Client ```(clients/cli/main.py)```

A Python command-line client using websocket-client.

**Features**

- Connects to the WebSocket server

- Displays the board in ASCII

- Accepts user moves

- Reacts to turn changes

- Shows winner and draws

- Avoids repeated spam messages

- Waits for new rounds automatically

**Flow**

1. User inputs room_id and player_id.

2. Client connects through WebSocket.

3. Server sends "state" messages.

4. CLI redraws board and handles turn logic.

### Web Client ```(clients/web/index.html)```

Plain HTML + CSS + JavaScript (no external frameworks).

**Includes**

- Form to enter room and player ID

- Interactive 3×3 board

- WebSocket connection

- Real-time UI updates

- Messages for turns, winner, errors

**How It Works**

Clicking a cell sends:
```
{ "type": "move", "cell": <index> }
```

- Server broadcasts the new state

- UI updates instantly

## How to Test the Full System

1. Start all backend services:

- User Service (8001)

- Room Service (8002)

- Game Rules Service (8003)

2. Create two users (POST /users).

3. Create a room and join both players.

4. Open two clients:

- One CLI client

- One Web client (or two CLI clients)

5. Play Tic Tac Toe in real time.

6. Watch automatic resets and new round creation.

## Technologies Used

- Python 3

- FastAPI (REST APIs)

- Uvicorn (ASGI server)

- WebSockets

- JavaScript (Vanilla)

- HTML/CSS

- websocket-client (Python)

- Virtual Environments (.venv)