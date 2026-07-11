"""AISStream live socket -> vessels table.

Realtime feed, snapshot mode: connect, capture position reports for
AIS_SECONDS, store them, disconnect. The controller reruns it on a short
cadence; phase 2 forwards the same socket straight to the frontend.

Run from the repo root:  python3 -m datapipeline.ais.loader

IMPORTANT: AISStream's free tier has essentially NO coverage over the
Persian Gulf / Indian Ocean (community receivers cluster in Europe/US).
The default box below is the English Channel / North Sea — it proves the
pipeline is live with real ships. Override with AIS_BBOX in .env if
coverage improves: AIS_BBOX=[[[latMin,lonMin],[latMax,lonMax]]]
"""
import asyncio
import json
import os
from datetime import datetime, timezone

from datapipeline.common.db import upsert

DURATION = int(os.environ.get("AIS_SECONDS", "60"))
EUROPE_BOX = [[[48.0, -6.0], [58.0, 12.0]]]   # good free-tier coverage
HORMUZ_BOX = [[[24.0, 54.0], [30.0, 60.0]]]   # kept for reference; ~zero free coverage
BOX = json.loads(os.environ["AIS_BBOX"]) if os.environ.get("AIS_BBOX") else EUROPE_BOX


async def run():
    import websockets  # imported here so the other loaders don't need it
    key = os.environ.get("AISSTREAM_API_KEY")
    if not key:
        raise SystemExit("AISSTREAM_API_KEY not set in .env  (free key: https://aisstream.io/)")

    sub = {"APIKey": key, "BoundingBoxes": BOX, "FilterMessageTypes": ["PositionReport"]}
    rows = []
    async with websockets.connect("wss://stream.aisstream.io/v0/stream") as ws:
        await ws.send(json.dumps(sub))
        loop = asyncio.get_event_loop()
        end = loop.time() + DURATION
        print(f"AIS: listening on box {BOX} for {DURATION}s ...")
        while loop.time() < end:
            remaining = end - loop.time()
            if remaining <= 0:
                break
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=remaining)
            except asyncio.TimeoutError:
                break
            m = json.loads(msg)
            if m.get("MessageType") != "PositionReport":
                continue
            pr = m["Message"]["PositionReport"]
            meta = m.get("MetaData", {})
            rows.append((
                meta.get("MMSI"),
                pr.get("Latitude", meta.get("latitude")),
                pr.get("Longitude", meta.get("longitude")),
                pr.get("Sog"), pr.get("Cog"),
                datetime.now(timezone.utc),
                (meta.get("ShipName") or "").strip() or None,
            ))
    upsert("vessels", ["mmsi", "lat", "lon", "sog", "cog", "ts", "name"],
           rows, conflict=["mmsi", "ts"])
    print(f"AIS: captured {len(rows)} position reports")
    return len(rows)


def main():
    return asyncio.run(run())


if __name__ == "__main__":
    main()
