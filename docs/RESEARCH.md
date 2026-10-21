# Web research: Jarvis searches and reads the web

Jarvis can now look things up on the web and read pages, the way you would:

- **`web_search`**: searches the web **privately**, through a search service on your own
  computer (SearXNG). It asks the public search engines for you with no account and no
  tracking cookies, and gives Jarvis the titles, links and short snippets.
- **`read_page`**: reads one web page as plain text: the words of the article, without
  menus, adverts, scripts or footers.

Jarvis always says why he is looking something up, and every search and page is written to
BAU's audit record. What he finds is treated as **information, never as orders**: a page
that says "ignore your rules" is just text to him.

`read_page` never opens addresses on your computer or your home network (your router, a
printer, BAU's own pages), and only reads ordinary web pages (no downloads).

## Turn on private search (once)

BAU must be installed on a disk (on the live stick an install only fills memory and is gone
at the next restart). You need the internet for this step. In a terminal:

```bash
sudo bash /opt/bau-payload/bau-search-setup.sh
```

If that file is not there, it is in `BAU-PAYLOAD` on the stick:
`sudo bash /run/live/medium/BAU-PAYLOAD/bau-search-setup.sh` (or download it from
<https://raw.githubusercontent.com/BSAJabo258/linux-ai-biz/main/installer/bau-search-setup.sh>).

It takes a few minutes and ends with **Private search is running on 127.0.0.1:8888**. It
starts by itself at every boot from then on, and only this computer can reach it.

To check it later: `sudo systemctl status bau-search`.

## Try it

Open **BAU Jarvis** and ask, for example:

- "Search the web for the best free text-to-speech that runs on a laptop."
- "Read the first result and tell me what it recommends."

If Jarvis says *the private search is not running on this computer*, run the setup above,
or start it again with `sudo systemctl restart bau-search`.

## Good to know

- SearXNG is open-source (AGPL-3.0). Running it unchanged for yourself is fine.
- The search service uses up to about 0.5 GB of memory (it is capped there).
- Search engines sometimes slow down or refuse a busy searcher for a few minutes; the other
  engines keep answering.
- Tested 2026-10-21: the setup ran in a clean Debian 13 in about a minute and Jarvis's
  search returned real results. Not yet tested on your laptop itself.
