
import json
import threading
import time

from websocket import WebSocketApp



GAME_RULES_WS_BASE_URL = "ws://127.0.0.1:8003/ws"


current_board = [""] * 9
current_turn = None
current_players = []
current_mark_map = {}
current_winner = None
my_player_id = None

socket_app = None
socket_connected = False
stop_flag = False




def print_board(board):

    symbols = [cell if cell else " " for cell in board]

    print()
    print(f" {symbols[0]} | {symbols[1]} | {symbols[2]}    (0 | 1 | 2)")
    print("---+---+---")
    print(f" {symbols[3]} | {symbols[4]} | {symbols[5]}    (3 | 4 | 5)")
    print("---+---+---")
    print(f" {symbols[6]} | {symbols[7]} | {symbols[8]}    (6 | 7 | 8)")
    print()


def print_state_message(message):
    global current_turn, my_player_id, current_winner

    print("\n=== GAME UPDATE ===")
    print(message)
    print_board(current_board)

    if current_winner is not None:
 
        if current_winner == "draw":
            print("Result: Draw!")
        else:
            if my_player_id and current_winner == my_player_id:
                print("Result: You WON! 🎉")
            else:
                print("Result: Player {} won.".format(current_winner))
        print("A new round will start with an empty board.")
    else:
        if my_player_id is not None:
            if current_turn == my_player_id:
                print("It is YOUR turn.")
            elif current_turn is None:
                print("Waiting for opponent to join or game to start...")
            else:
                print("It is opponent's turn ({}).".format(current_turn))




def on_open(ws):
    global socket_connected
    socket_connected = True
    print("\n Connected to Game Rules Service.")


def on_message(ws, message):
    global current_board, current_turn, current_players, current_mark_map, current_winner

    try:
        data = json.loads(message)
    except json.JSONDecodeError:
        print(" ERROR Received invalid JSON: {}".format(message))
        return

    msg_type = data.get("type")

    if msg_type == "state":

        current_board = data.get("board", [""] * 9)
        current_turn = data.get("turn")
        current_players = data.get("players", [])
        current_mark_map = data.get("mark_map", {})
        current_winner = data.get("winner")

        text_message = data.get("message", "State update")
        print_state_message(text_message)

    elif msg_type == "info":
        print("\n {}".format(data.get("message")))

    elif msg_type == "error":
        print("\n SERVER ERROR {}".format(data.get("message")))

    else:
        print("\n DEBUG Unknown message type: {}".format(data))


def on_error(ws, error):
    print("\n WEBSOCKET ERROR {}".format(error))


def on_close(ws, close_status_code, close_msg):
    global socket_connected
    socket_connected = False
    print("\n[INFO] WebSocket connection closed.")




def websocket_thread(url):
    global socket_app, stop_flag

    socket_app = WebSocketApp(
        url,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
    )


    socket_app.run_forever()


    stop_flag = True


def main():
    global my_player_id, socket_app, stop_flag

    print("=== CLI Tic-Tac-Toe Client ===")
    print("Make sure User Service, Room Service and Game Rules Service are running.")
    print("You must already have a room with two players in Room Service.\n")

    room_id = input("Enter room_id: ").strip()
    my_player_id = input("Enter your player_id: ").strip()

    if not room_id or not my_player_id:
        print("room_id and player_id are required. Exiting.")
        return

    ws_url = "{}/{}/{}".format(GAME_RULES_WS_BASE_URL, room_id, my_player_id)
    print("\n[INFO] Connecting to: {}".format(ws_url))


    t = threading.Thread(target=websocket_thread, args=(ws_url,), daemon=True)
    t.start()


    time.sleep(1.0)


    try:
        while not stop_flag:
            if not socket_connected:
       
                time.sleep(0.5)
                continue

 
            if current_winner is not None:
                print("\n Game finished. Waiting for the next round...")
                time.sleep(2.0)
                continue

            if current_turn is None:
                print("\n Waiting for opponent or for the game to start...")
                time.sleep(2.0)
                continue


            if current_turn != my_player_id:
                print("\n Not your turn. Waiting for opponent move...")
                time.sleep(2.0)
                continue

       
            user_input = input("\nYour turn. Enter move index (0-8) or 'q' to quit: ").strip()

            if user_input.lower() == "q":
                print("Quitting game...")
                break

            if not user_input.isdigit():
                print("Please enter a number between 0 and 8 or 'q'.")
                continue

            index = int(user_input)
            if index < 0 or index > 8:
                print("Index must be between 0 and 8.")
                continue


            if socket_app:
                payload = {"action": "move", "index": index}
                try:
                    socket_app.send(json.dumps(payload))
                except Exception as e:
                    print("ERROR Failed to send move: {}".format(e))
            else:
                print("ERROR WebSocket is not available.")

    except KeyboardInterrupt:
        print("\n[INFO] Interrupted by user. Exiting...")


    if socket_app:
        try:
            socket_app.close()
        except Exception:
            pass


    time.sleep(0.5)
    print("Goodbye.")


if __name__ == "__main__":
    main()