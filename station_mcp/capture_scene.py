"""Capture the top-cam scene (raw + grid overlay) for locating the box."""
import asyncio
import io
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
    await b.send_joint_targets({8: 2917})  # ensure jaws open
    jpeg = await b.get_frame("top")
    with open("box_raw.jpg", "wb") as f:
        f.write(jpeg)
    with open("box_grid.jpg", "wb") as f:
        f.write(overlay.draw_grid(jpeg, step=20))
    from PIL import Image
    print("top frame size:", Image.open(io.BytesIO(jpeg)).size)


asyncio.run(main())
