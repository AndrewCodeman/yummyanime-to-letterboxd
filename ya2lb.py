#!/usr/bin/env python3
"""Turn your YummyAnime lists into Letterboxd import files.

Reads the public lists of a YummyAnime profile, finds the TMDB and IMDb ids of
anime films through Wikidata and writes CSV files for Letterboxd's importer.
See README.md.
"""
import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

__version__ = "1.0.0"

YUMMY_API = "https://api.yani.tv"
WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"
USER_AGENT = f"yummyanime-to-letterboxd/{__version__} (https://github.com/AndrewCodeman/yummyanime-to-letterboxd)"
WIKIDATA_BATCH = 200     # MyAnimeList ids per Wikidata query
MAX_CSV_BYTES = 950_000  # Letterboxd rejects import files over 1 MB

# YummyAnime list ids
WATCHING, PLANNED, WATCHED, DROPPED, POSTPONED = 0, 1, 2, 3, 5
LIST_NAMES = {WATCHING: "watching", PLANNED: "planned", WATCHED: "watched",
              DROPPED: "dropped", POSTPONED: "postponed"}

# YummyAnime types that are films even when Wikidata doesn't know them
FILM_TYPES = {"movie", "short-movie"}


# --- YummyAnime
def user_id(text):
    """'123', 'id123' or 'https://yummyani.me/users/id123' -> '123'."""
    m = re.search(r"(?:users/)?(?:id)?(\d+)/?$", text.strip())
    if not m:
        sys.exit(f"Can't find a user id in {text!r}. Use the number from your profile link, "
                 "e.g. https://yummyani.me/users/id12345")
    return m.group(1)


def fetch_lists(uid, app_token=None):
    headers = {"Lang": "en", "Accept": "application/json"}
    if app_token:
        headers["X-Application"] = app_token
    data = fetch_json(f"{YUMMY_API}/users/{uid}/lists", headers)
    if data is None:
        sys.exit("YummyAnime didn't answer. Try again later.")
    if "response" not in data:
        sys.exit(f"YummyAnime: {data.get('error', 'unexpected answer')} (user id {uid})")
    return data["response"]


def parse_entry(a):
    """Turn one YummyAnime list entry into a flat record."""
    user = a.get("user") or {}
    lst = ((user.get("list") or {}).get("list") or {})
    ids = a.get("remote_ids") or {}
    return {
        "yummy_id": a.get("anime_id"),
        "title": (a.get("title") or "").strip(),
        "year": a.get("year") or None,
        "type": (a.get("type") or {}).get("alias", ""),
        "list": LIST_NAMES.get(lst.get("id"), lst.get("title", "").lower()),
        "rating": user.get("rating") or None,
        "favorite": bool((user.get("list") or {}).get("is_fav")),
        "mal_id": ids.get("myanimelist_id") or None,
        "kp_id": ids.get("kp_id") or None,
        "url": f"https://yummyani.me/catalog/item/{a['anime_url']}" if a.get("anime_url") else "",
        "tmdb_id": None,
        "imdb_id": None,
    }


# --- Wikidata
def lookup_ids(mal_ids, log=print):
    """MyAnimeList id -> (TMDB movie id, IMDb id) from Wikidata.

    Wikidata only has a TMDB *movie* id for films, so finding one also tells us
    the anime is something Letterboxd will know.
    """
    found = {}
    ids = sorted({str(i) for i in mal_ids if i})
    for start in range(0, len(ids), WIKIDATA_BATCH):
        chunk = ids[start:start + WIKIDATA_BATCH]
        query = ("SELECT ?mal ?tmdb ?imdb WHERE { VALUES ?mal { %s } ?item wdt:P4086 ?mal . "
                 "OPTIONAL { ?item wdt:P4947 ?tmdb } OPTIONAL { ?item wdt:P345 ?imdb } }"
                 % " ".join(f'"{i}"' for i in chunk))
        data = fetch_json(WIKIDATA_SPARQL + "?" + urllib.parse.urlencode({"query": query, "format": "json"}),
                          {"Accept": "application/sparql-results+json"}, timeout=90)
        if data is None:
            log("  Wikidata didn't answer, the rest will be matched by title")
            return found
        for row in data["results"]["bindings"]:
            tmdb = row.get("tmdb", {}).get("value")
            imdb = row.get("imdb", {}).get("value")
            old = found.get(int(row["mal"]["value"]), (None, None))
            found[int(row["mal"]["value"])] = (old[0] or tmdb, old[1] or imdb)
        log(f"  checked {min(start + WIKIDATA_BATCH, len(ids))}/{len(ids)}")
    return found


def fetch_json(url, headers, attempts=3, timeout=30):
    headers = {"User-Agent": USER_AGENT, **headers}
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                try:
                    return json.load(e)
                except json.JSONDecodeError:
                    return {"error": "not found"}
            time.sleep(2 * (attempt + 1))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            time.sleep(2 * (attempt + 1))
    return None


# --- conversion
def is_film(r):
    return bool(r["tmdb_id"]) or r["type"] in FILM_TYPES


def convert(entries, ids=None, watched_lists=(WATCHED,)):
    """Build the rows that get written to disk. Pure function, no I/O."""
    ids = ids or {}
    watched_names = {LIST_NAMES[i] for i in watched_lists}
    records = []
    for a in entries:
        r = parse_entry(a)
        r["tmdb_id"], r["imdb_id"] = ids.get(r["mal_id"], (None, None))
        records.append(r)

    films, watchlist, series = [], [], []
    for r in records:
        row = {"tmdbID": r["tmdb_id"] or "", "imdbID": r["imdb_id"] or "",
               "Title": r["title"], "Year": r["year"] or "", "Rating10": r["rating"] or ""}
        if r["list"] in watched_names:
            (films if is_film(r) else series).append(row)
        elif r["list"] == "planned" and is_film(r):
            watchlist.append({k: v for k, v in row.items() if k != "Rating10"})
    return {"records": records, "films": films, "watchlist": watchlist, "series": series}


# --- output
def write_letterboxd_csv(path, rows, columns):
    """Write a Letterboxd import file, split into parts under 1 MB. Returns the paths."""
    base, ext = os.path.splitext(path)
    paths, part, f, writer = [], 0, None, None
    for row in rows:
        if f is None or f.tell() > MAX_CSV_BYTES:
            if f:
                f.close()
            part += 1
            p = path if part == 1 else f"{base}-{part}{ext}"
            paths.append(p)
            # Letterboxd wants plain UTF-8 and backslash-escaped quotes.
            f = open(p, "w", encoding="utf-8", newline="")
            writer = csv.writer(f, doublequote=False, escapechar="\\")
            writer.writerow(columns)
        writer.writerow([row.get(c, "") for c in columns])
    if f:
        f.close()
    return paths


def write_reference_csv(path, records):
    """Everything from YummyAnime in one table, for you to look through. Not for Letterboxd."""
    columns = ["list", "type", "title", "year", "rating", "favorite", "tmdb_id", "imdb_id", "mal_id", "kp_id", "url"]
    with open(path, "w", encoding="utf-8-sig", newline="") as f:  # BOM so Excel reads it right
        w = csv.DictWriter(f, columns, extrasaction="ignore")
        w.writeheader()
        w.writerows(records)


def main(argv=None):
    p = argparse.ArgumentParser(description="Turn your YummyAnime lists into Letterboxd import files.")
    p.add_argument("profile", help="your YummyAnime profile link or user id, e.g. https://yummyani.me/users/id12345")
    p.add_argument("--out", default="letterboxd", help="output folder, ./letterboxd by default")
    p.add_argument("--also", nargs="+", default=[], choices=["watching", "dropped", "postponed"],
                   help="treat these lists as watched too")
    p.add_argument("--no-wikidata", action="store_true", help="don't look up TMDB/IMDb ids, match by title only")
    p.add_argument("--yummy-app-token", default=os.environ.get("YUMMY_APP_TOKEN"),
                   help="YummyAnime application token, sent as X-Application (or set YUMMY_APP_TOKEN)")
    p.add_argument("--version", action="version", version=__version__)
    args = p.parse_args(argv)

    uid = user_id(args.profile)
    entries = fetch_lists(uid, args.yummy_app_token)
    if not entries:
        sys.exit("The lists are empty. If they aren't, check that your lists are public in your YummyAnime "
                 "profile settings.")
    print(f"YummyAnime: {len(entries)} titles in the lists of user {uid}")

    ids = {}
    if not args.no_wikidata:
        print("Looking up TMDB and IMDb ids on Wikidata...")
        ids = lookup_ids([parse_entry(a)["mal_id"] for a in entries])

    watched = (WATCHED,) + tuple(k for k, v in LIST_NAMES.items() if v in args.also)
    result = convert(entries, ids, watched)

    os.makedirs(args.out, exist_ok=True)
    columns = ["tmdbID", "imdbID", "Title", "Year", "Rating10"]
    written = write_letterboxd_csv(os.path.join(args.out, "films.csv"), result["films"], columns)
    written += write_letterboxd_csv(os.path.join(args.out, "watchlist.csv"), result["watchlist"], columns[:-1])
    written += write_letterboxd_csv(os.path.join(args.out, "series.csv"), result["series"], columns)
    reference = os.path.join(args.out, "yummyanime-all.csv")
    write_reference_csv(reference, result["records"])
    written.append(reference)

    with_id = sum(1 for r in result["films"] if r["tmdbID"] or r["imdbID"])
    print()
    print(f"Films:      {len(result['films'])} ({with_id} with a TMDB or IMDb id)")
    print(f"Watchlist:  {len(result['watchlist'])}")
    print(f"Series:     {len(result['series'])}")
    print()
    for path in written:
        print("  " + path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
