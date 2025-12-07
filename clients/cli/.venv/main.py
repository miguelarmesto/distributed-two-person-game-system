# clients/cli/main.py
import json
import threading
import time
import requests
from websocket import WebSocketApp

GAME_RULES_WS_BASE = "ws://127.0.0.1:8003/ws"
GAME_RULES_HTTP_BASE = "http://127.0.0.1:8003"

current_board = [""] * 9
current_turn = None
current_players = []
current_mark_map = {}
current_winner = None

socket_app = None
socket_connected = False
stop_flag = False

current_room_id = None
my_player_id = None

last_status_msg = None


def print_board(board):
    symbols = [c if c else " " for c in board]
    print()
    print(f" {symbols[0]} | {symbols[1]} | {symbols[2]}    (0 | 1 | 2)")
    print("---+---+---")
    print(f" {symbols[3]} | {symbols[4]} | {symbols[5]}    (3 | 4 | 5)")
    print("---+---+---")
    print(f" {symbols[6]} | {symbols[7]} | {symbols[8]}    (6 | 7 | 8)")
    print()


def maybe_print_once(msg):
    global last_status_msg
    if msg != last_status_msg:
        print("\n" + msg)
        last_status_msg = msg


def safe_http_delete(url):
    try:
        return requests.delete(url, timeout=3)
    except Exception as e:
        print(f"[HTTP ERROR] DELETE {url} -> {e}")
        return None


def on_open(ws):
    global socket_connected, last_status_msg
    socket_connected = True
    last_status_msg = None
    print("\n[INFO] Connected to Game Rules Service.")


def on_message(ws, message):
    global current_board, current_turn, current_players, current_mark_map, current_winner, last_status_msg

    try:
        data = json.loads(message)
    except json.JSONDecodeError:
        print(f"[ERROR] Invalid JSON from server: {message}")
        return

    msg_type = data.get("type")

    if msg_type == "state":
        current_board = data.get("board", [""] * 9)
        current_turn = data.get("turn")
        current_players = data.get("players", [])
        current_mark_map = data.get("mark_map", {})
        current_winner = data.get("winner")

        last_status_msg = None

        text = data.get("message", "State update")
        print("\n=== GAME UPDATE ===")
        print(text)
        print_board(current_board)

        if current_winner is not None:
            if current_winner == "draw":
                print("Result: Draw!")
            elif current_winner == my_player_id:
                print("Result: You WON! 🎉")
            else:
                print(f"Result: Player {current_winner} won.")

            print("A new round will start automatically in 10 seconds...")
            threading.Thread(target=end_round_flow, args=(current_room_id,), daemon=True).start()

        else:
            if current_turn == my_player_id:
                print("It is YOUR turn.")
            else:
                print(f"It is opponent's turn ({current_turn}).")

    elif msg_type == "info":
        maybe_print_once("[INFO] " + str(data.get("message")))

    elif msg_type == "error":
        maybe_print_once("[SERVER ERROR] " + str(data.get("message")))


def on_error(ws, error):
    maybe_print_once(f"[WEBSOCKET ERROR] {error}")


def on_close(ws, close_status_code, close_msg):
    global socket_connected
    socket_connected = False
    maybe_print_once("[INFO] WebSocket connection closed.")


def run_ws(ws_url):
    global socket_app, stop_flag
    socket_app = WebSocketApp(
        ws_url,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
    )
    socket_app.run_forever()
    stop_flag = True


def end_round_flow(room_id):
    """
    When a match finishes:
    - wait 10 seconds
    - delete current game state
    - close WS
    - return to main loop to ask for new room/player id
    """
    global socket_app, socket_connected, stop_flag

    # Wait 10 seconds
    for i in range(10, 0, -1):
        maybe_print_once(f"[INFO] Returning to menu in {i} seconds...")
        time.sleep(1)

    # Delete current game state
    del_url = f"{GAME_RULES_HTTP_BASE}/games/{room_id}"
    print(f"[INFO] Deleting finished match: {del_url}")
    safe_http_delete(del_url)

    # Close WebSocket
    try:
        if socket_app:
            socket_app.close()
    except:
        pass

    time.sleep(0.5)
    maybe_print_once("[INFO] Match cleared. Returning to menu...")


def interactive_loop():
    global current_room_id, my_player_id, socket_app, socket_connected, stop_flag, current_winner, last_status_msg

    while True:
        # Reset data
        current_winner = None
        last_status_msg = None
        stop_flag = False
        socket_connected = False

        # Ask connection
        room = input("\nEnter room_id (or 'q' to quit): ").strip()
        if room.lower() == "q":
            print("Exiting.")
            break

        player = input("Enter your player_id: ").strip()
        if player.lower() == "q":
            print("Exiting.")
            break

        current_room_id = room
        my_player_id = player

        ws_url = f"{GAME_RULES_WS_BASE}/{room}/{player}"
        print(f"\n[INFO] Connecting to: {ws_url}")

        t = threading.Thread(target=run_ws, args=(ws_url,), daemon=True)
        t.start()

        time.sleep(1.0)

        try:
            while not stop_flag:
                if not socket_connected:
                    break

                if current_winner is not None:
                    break

                if current_turn is None:
                    maybe_print_once("[INFO] Waiting for opponent or game start...")
                    time.sleep(1.0)
                    continue

                if current_turn != my_player_id:
                    maybe_print_once("[INFO] Waiting for opponent move...")
                    time.sleep(0.8)
                    continue

                user_input = input("\nYour turn. Enter index (0-8) or 'q': ").strip()
                if user_input.lower() == "q":
                    print("Leaving session...")
                    try:
                        if socket_app:
                            socket_app.close()
                    except:
                        pass
                    break

                if not user_input.isdigit():
                    print("Must be a number 0–8.")
                    continue

                idx = int(user_input)
                if idx < 0 or idx > 8:
                    print("Must be between 0 and 8.")
                    continue

                if socket_app and socket_connected:
                    socket_app.send(json.dumps({"action": "move", "index": idx}))
                else:
                    print("WebSocket not available.")

        except KeyboardInterrupt:
            print("\n[INFO] Interrupted. Exiting.")
            try:
                if socket_app:
                    socket_app.close()
            except:
                pass
            break

    print("Goodbye.")


if __name__ == "__main__":
    interactive_loop()
