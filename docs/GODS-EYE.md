# God's Eye: the world on Jarvis's screen

God's Eye shows public world data on a map in Jarvis:
- **Earthquakes** from the US Geological Survey: the last hour, day or week, or the
  significant ones.
- **Aircraft** over a wide named region (Florida, US east or west, New York area,
  Caribbean, UK and Ireland, Europe, Japan), from the OpenSky Network.
- **Satellites** from CelesTrak: space stations, visible satellites, weather and GPS.

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
| World outline | Made with Natural Earth: public domain |

## The sky: timely post ideas (2026-11-10)

God's Eye also helps the money loop. Each day it works out the sky on this computer (no
internet needed): full and new moons, the solstices and equinoxes, and the peaks of the major
meteor showers (Quadrantids, Lyrids, Eta Aquariids, Perseids, Orionids, Leonids, Geminids;
dates read 2026-11-10 from space.com, rmg.co.uk and amsmeteors.org, one day either side). When
there is a moment, the creator feed gives the day's first post that theme, for example "watching
the Perseid meteor shower under the night sky". Each moment is used once. Earthquakes and other
disasters are never a theme.
