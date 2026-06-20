"""Subscribe to the `inference/normvla` queue and print synced joints + camera images.

normvla = the pre-synced feed SmolVLA consumes: 224x224 JPEG frame(s) + joint state, time-aligned.
This script confirms the full perception pipeline is live (cameras + torqued bus + inference config).

Run (on a machine that can reach the Station):
    # local Station:
    NORMA_CORE_PATH=/mnt/d/normacore/norma-core uv run python subscribe_normvla.py
    # remote Station (arm on another laptop):
    STATION_HOST=<robot-ip> NORMA_CORE_PATH=/mnt/d/normacore/norma-core uv run python subscribe_normvla.py
    # also dump the latest frame(s) to normvla_cam0.jpg / normvla_cam1.jpg:
    SAVE_IMAGES=1 STATION_HOST=<robot-ip> NORMA_CORE_PATH=... uv run python subscribe_normvla.py
"""
import asyncio
import logging
import os
import sys

NC = os.path.abspath(os.environ.get("NORMA_CORE_PATH", "../norma-core"))
sys.path.insert(0, NC)                                      # target.gen_python.* + shared.gremlin_py.*
sys.path.insert(0, os.path.join(NC, "software/station/shared"))  # station_py

from station_py import new_station_client, StreamEntry  # type: ignore
from target.gen_python.protobuf.drivers.inferences import normvla as normvla_pb2  # type: ignore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("normvla-sub")

HOST = os.environ.get("STATION_HOST", "localhost")
PORT = os.environ.get("STATION_PORT", "8888")
SAVE = os.environ.get("SAVE_IMAGES", "").lower() in ("1", "true", "yes")
SAMPLE = int(os.environ.get("SAMPLE_FRAMES", "20"))


async def main() -> None:
    client = await new_station_client(f"{HOST}:{PORT}", log)
    q: asyncio.Queue = asyncio.Queue()
    err = client.follow("inference/normvla", q)
    log.info("following inference/normvla on %s:%s", HOST, PORT)

    seen = 0
    while seen < SAMPLE:
        if err is not None and not err.empty():
            log.error("follow error: %s", await err.get())
            break
        try:
            entry: StreamEntry = await asyncio.wait_for(q.get(), timeout=2.0)
        except asyncio.TimeoutError:
            log.info("no frames yet — check: cameras detected? torque ON (follower)? inference configured?")
            continue
        if entry is None:
            log.info("stream ended")
            break

        frame = normvla_pb2.FrameReader(memoryview(bytes(entry.Data)))
        joints = frame.get_joints()
        images = frame.get_images()
        pos_norm = [round(j.get_position_norm(), 3) for j in joints]
        img_sizes = [len(bytes(im.get_jpeg())) for im in images]
        log.info("frame %2d | %d joints pos_norm=%s | %d image(s) bytes=%s",
                 seen, len(joints), pos_norm, len(images), img_sizes)

        if SAVE and images:
            for i, im in enumerate(images):
                fn = f"normvla_cam{i}.jpg"
                with open(fn, "wb") as f:
                    f.write(bytes(im.get_jpeg()))
            log.info("saved %d image(s) -> normvla_cam*.jpg", len(images))
        seen += 1

    log.info("done (sampled %d frame(s))", seen)


if __name__ == "__main__":
    asyncio.run(main())
