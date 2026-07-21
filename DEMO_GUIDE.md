# Running PRAHARI and what to show a judge

This is the practical guide: how to start it, how to make the data fresh, and
the short walk-through we use on stage. For the story behind the project, read
`SUBMISSION.md`.

## Start it

The quick way, both halves at once, from the `platform` folder:

```
./run_dev.sh
```

Or start the two parts yourself if you prefer:

- Backend, from `platform`:
  ```
  python3 -m uvicorn api.main:app --port 8000
  ```
- Frontend, from `platform/frontend` (run `npm install` the first time):
  ```
  npm run dev
  ```

Then open http://localhost:5173. The map and the side panels load on their own.
The backend's own docs, if a judge wants to poke the raw data, are at
http://localhost:8000/docs.

## Before you present: freshen the data

The database holds a snapshot, so pull the latest before you go on. This needs
the API keys and the database URL in your `.env` file:

```
python3 -m datapipeline.controller --force
```

If you want it to keep refreshing while you talk, run it on a loop instead:

```
python3 -m datapipeline.controller --loop 300
```

You can check how fresh each feed is at http://localhost:8000/freshness.

## The 90-second walk-through

1. Start on the calm dashboard. Point at the map: the suppliers, the ports, the
   Strait of Hormuz. Show the chokepoint watch list on the right sitting quiet.
2. Click **Inject signal**. This replays a real news event from our data, an
   Israel–Iran strike near Hormuz. Watch the pipeline light up one step at a
   time: signal, simulation, routes, decision.
3. Read the answer straight off the cards: the risk level, the cost in rupees
   per day, how far the reserve drops, and the supplier and route to switch to.
   The new route draws itself across the map.
4. Turn a knob in the assumptions panel, for example "days to reroute", and show
   the whole thing recompute live. This is the "our assumptions are open, change
   them yourself" moment that judges tend to ask about.
5. If the live data is fresh, click **Run live** to run the same thing on the
   current real news. Right now Hormuz reads Critical off 77 real events, so the
   live number is even stronger than the injected one.

## If something goes wrong on stage

The **Inject signal** button does not need the database or the internet. It runs
the full pipeline on a cached real event. If the wifi dies mid-demo, that button
still works, and it produces the same result every time. That is your safety net,
so lean on it if you are nervous about the network.

There is also a **Reactive / Anticipatory** switch at the top. Flip it to
Reactive and the screen goes to a plain "old way" panel showing the 47-day
number. It is a fast way to make the before-and-after contrast without saying a
word.

## Common questions and short answers

- **Is this real-time?** It is real public data, refreshed on a schedule, not a
  live stream. Prices and ships update every few minutes, news every few hours.
- **Did an AI make up these numbers?** No. Every number is computed and can be
  checked. The AI only reads news text; it never invents figures.
- **Why no live ships near Hormuz?** The free ship tracker has almost no coverage
  there. The live dots prove the pipeline works; the Hormuz risk comes from news
  and sanctions data, which we do have.
