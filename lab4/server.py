from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import asyncio

DIR_ICONS = {0: "▲", 1: "▶", 2: "▼", 3: "◀"}

MAP_WIDTH = 12
MAP_HEIGHT = 10

tactical_map = [["0"] * MAP_WIDTH for _ in range(MAP_HEIGHT)]
mines_db = {}
rovers_db = {}
bomb_log = []  # [{x, y, status}]

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- MODELS ---
class MineCreate(BaseModel):
    x: int
    y: int
    serial_number: str

class RoverCreate(BaseModel):
    commands: str


# --- ROUTES ---
@app.get("/map")
def get_map():
    return {"map": tactical_map}


@app.get("/bombs")
def get_bombs():
    return bomb_log


@app.post("/mines")
def create_mine(mine: MineCreate):
    mine_id = f"M-{len(mines_db) + 1}"

    mines_db[mine_id] = {
        "x": mine.x,
        "y": mine.y,
        "serial_number": mine.serial_number
    }

    tactical_map[mine.y][mine.x] = "X"

    return {"id": mine_id}


@app.get("/rovers")
def get_rovers():
    return {"rovers": rovers_db}


@app.post("/rovers")
def create_rover(rover: RoverCreate):
    rover_id = f"R-{len(rovers_db) + 1}"

    rovers_db[rover_id] = {
        "status": "Not Started",
        "commands": rover.commands,
        "position": [0, 0],
        "facing": 2,
        "on_mine": False,
        "busy": False,
        "last_known": None
    }

    return {"id": rover_id}


# --- WEBSOCKET ---
@app.websocket("/ws/rovers/{rover_id}")
async def websocket_endpoint(websocket: WebSocket, rover_id: str):
    await websocket.accept()

    clean_id = rover_id.replace("ASSET-", "")

    if clean_id not in rovers_db:
        await websocket.close()
        return

    r = rovers_db[clean_id]

    # 🚫 Eliminated rover reconnect block
    if r["status"] == "Eliminated":
        loc = r.get("last_known", ["?", "?"])
        await websocket.send_json({
            "status": "ERROR",
            "message": "ERROR: [ASSET ELIMINATED] CANNOT ESTABLISH CONNECTION",
            "last_known": loc
        })
        await websocket.close()
        return

    r["status"] = "Moving"

    try:
        while True:
            cmd = (await websocket.receive_text()).upper()

            if r["busy"]:
                continue

            x, y = r["position"]
            facing = r["facing"]

            msg = "Action Complete"
            pin = None

            # --- ROTATION ---
            if cmd == 'L':
                facing = (facing - 1) % 4

            elif cmd == 'R':
                facing = (facing + 1) % 4

            # --- MOVE ---
            elif cmd == 'M':
                nx, ny = x, y

                if facing == 0: ny -= 1
                elif facing == 1: nx += 1
                elif facing == 2: ny += 1
                elif facing == 3: nx -= 1

                if 0 <= ny < MAP_HEIGHT and 0 <= nx < MAP_WIDTH:

                    # 💥 EXPLODE only when LEAVING mine
                    if r["on_mine"]:
                        tactical_map[y][x] = "☢"
                        r["status"] = "Eliminated"
                        r["last_known"] = [x, y]

                        # remove mine
                        target = next(
                            (k for k, m in mines_db.items() if m["x"] == x and m["y"] == y),
                            None
                        )
                        if target:
                            del mines_db[target]
                        #clear cell (no lingering landmine)
                        tactical_map[y][x] = "0"

                        # log suspected
                        bomb_log.append({
                            "x": x,
                            "y": y,
                            "status": "SUSPECTED"
                        })

                        await websocket.send_json({
                            "status": "Eliminated",
                            "message": f"COLLISION DETECTED at [{x}, {y}]",
                            "x": x,
                            "y": y
                        })
                        break

                    # breadcrumb
                    if tactical_map[y][x] not in ("X", "☢"):
                        tactical_map[y][x] = "*"

                    # move
                    x, y = nx, ny

                    # check stepping ON mine (safe)
                    hit = next(
                        (m for m in mines_db.values() if m["x"] == x and m["y"] == y),
                        None
                    )
                    r["on_mine"] = True if hit else False

            # --- DIG ---
            elif cmd == 'D':
                r["busy"] = True

                await websocket.send_json({
                    "status": "MOVING",
                    "message": "Demining..."
                })

                await asyncio.sleep(2)

                target = next(
                    (k for k, m in mines_db.items() if m["x"] == x and m["y"] == y),
                    None
                )

                if target:
                    pin = mines_db[target]["serial_number"]
                    del mines_db[target]
                    tactical_map[y][x] = "0"
                    r["on_mine"] = False

                    bomb_log.append({
                        "x": x,
                        "y": y,
                        "status": "DEFUSED"
                    })

                    msg = "Demining Complete"
                else:
                    msg = "No ordnance detected"

                r["busy"] = False

            # --- UPDATE ---
            r["position"] = [x, y]
            r["facing"] = facing

            if tactical_map[y][x] not in ("X", "☢"):
                tactical_map[y][x] = DIR_ICONS[facing]

            # 🚨 rover overlap warning
            for rid, other in rovers_db.items():
               for rid, other in rovers_db.items():
                    if (
                        rid != clean_id
                        and other["position"] == [x, y]
                        and other["status"] != "Eliminated"
                    ):
                        await websocket.send_json({
                            "status": "WARNING",
                            "message": f"WARNING: [ASSET {rid}] IS ALSO ON THIS CELL"
                        })

            await websocket.send_json({
                "command": cmd,
                "status": r["status"],
                "message": msg,
                "pin": pin,
                "x": x,
                "y": y
            })

    except WebSocketDisconnect:
        if r["status"] != "Eliminated":
            r["status"] = "Finished"


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)