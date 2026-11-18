# God's Eye: the world on Jarvis's screen

God's Eye shows public world data on a map in Jarvis:
- **Earthquakes** from the US Geological Survey: the last hour, day or week, or the
  significant ones.
- **Aircraft** over a wide named region (Florida, US east or west, New York area,
  Caribbean, UK and Ireland, Europe, Japan), from the OpenSky Network.
- **Satellites** from CelesTrak: space stations, visible satellites, weather and GPS.
- **Wildfires** from NASA FIRMS: active fire detections worldwide or over a wide named region.
- **Weather** from Open-Meteo: current conditions at the centre of a wide named region.
- **Space weather** from NOAA SWPC: the latest planetary K-index readings.
- **Traffic** from TomTom: incidents over a wide named region (needs a free TomTom key).
- **Ships** from AISStream: live AIS positions over a wide named region (needs a free
  AISStream key).

## Use it

- **On the Jarvis screen:** click the **God's Eye** dot, pick a layer, and press **Show on
  the map**. The map opens in the middle of the screen; **×** or **Esc** closes it.
- **Ask Jarvis:** "Any big earthquakes today?" or "How busy is the sky over Europe?"
- **In the terminal:** `bau spatial earthquakes --purpose "..."` (see `bau spatial --help`).

## What it will not do

- **Follow a person.** Questions that look like tracking someone (a name, an address,
  "track my ex") are refused.
- **Watch one place.** Aircraft are shown only for wide named regions, never a box you
  draw around one spot.
- **Name private planes.** Airline flights show their flight number; private aircraft show
  only as "private aircraft", because a registration can point to one person.
- **Pretend.** Satellites are listed from their published orbital data; their positions
  are not computed, so they aren't drawn on the map.

## Fair use of the sources

Each view is kept for five minutes, so the public sources are asked at most once in that
time. If a source answers "too many requests", BAU waits until the time it gives (or ten
minutes) and sends nothing before then. Every query is written to the audit record with
its purpose.

| Source | Terms |
|---|---|
| USGS earthquakes | public domain |
| OpenSky Network | free for non-commercial use; commercial use needs their licence |
| CelesTrak | public orbital data |
| NASA FIRMS | near-real-time fire detections; public data, attribution requested; not for safety-critical use |
| Open-Meteo | free for non-commercial use; data CC BY 4.0 |
| NOAA SWPC | US Government public domain |
| TomTom Traffic | needs a free API key and TomTom's terms |
| AISStream.io | needs a free API key and AISStream's terms |
| World outline | Made with Natural Earth: public domain |

## Keys for the live layers

The earthquake, aircraft, satellite, wildfire (global), weather and space-weather layers work
without a key. Traffic and ships need free accounts:

```bash
# Put these in the service environment, never in a chat or a git commit.
TOMTOM_API_KEY=...
AISSTREAM_API_KEY=...
FIRMS_MAP_KEY=...          # optional: smaller area queries instead of the global 24-hour CSV
```

Ships need the optional `websocket-client` package. The global wildfire CSV is large; the
screen keeps the 400 brightest detections for the map and the rest stay in the source result.


## The sky: timely post ideas (2026-11-10)

God's Eye also helps the money loop. Each day it works out the sky on this computer (no
internet needed): full and new moons, the solstices and equinoxes, and the peaks of the major
meteor showers (Quadrantids, Lyrids, Eta Aquariids, Perseids, Orionids, Leonids, Geminids;
dates read 2026-11-10 from space.com, rmg.co.uk and amsmeteors.org, one day either side). When
there is a moment, the creator feed gives the day's first post that theme, for example "watching
the Perseid meteor shower under the night sky". Each moment is used once. Earthquakes and other
disasters are never a theme.

## In the money loop and the briefing (2026-11-10)

- **Best hours:** autopost only posts in the audience's evening, 18:00 to 23:00 local in at
  least one of New York, Chicago, Los Angeles or London. The creator profile can list its own
  `posting_zones`.
- **Brand safety:** before each post God's Eye reads the USGS earthquake feed (public
  domain). A magnitude 7 or stronger quake in the last 24 hours holds that day's posts; they
  stay queued and go out once it has passed. If the feed cannot be reached, posting goes on.
- **Briefing:** Jarvis's morning facts carry tonight's sky, any magnitude 6+ earthquakes of
  the last 24 hours, and whether posts are held. Every lookup is audited with its purpose.
