"""Capture top + wrist frames at the current arm pose (no move). For alignment checks."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
import backend as bk
import overlay


async def main():
    b = bk.LiveBackend("localhost", 8888, os.environ.get("NORMA_CORE_PATH", "../norma-core"),
                       os.environ.get("STATION_BUS_SERIAL"))
    await b.connect()
    top = await b.get_frame("top")
    wrist = await b.get_frame("wrist")
    with open("look_top.jpg", "wb") as f:
        f.write(overlay.draw_grid(top, step=20))
    with open("look_wrist.jpg", "wb") as f:
        f.write(wrist)
    print("saved look_top.jpg, look_wrist.jpg")


asyncio.run(main())
