# yummyanime-to-letterboxd

Moves your anime lists from YummyAnime to Letterboxd.

I keep track of the anime I watch on YummyAnime, and my films on Letterboxd. I wanted the anime films there too,
with my ratings, and didn't want to add a hundred and fifty of them by hand.

The script reads your lists through the public YummyAnime API, so there's nothing to log in to. Anime titles are
where imports usually go wrong: YummyAnime might call a film "Kimi no Na wa." while Letterboxd knows it as
"Your Name.". So for every anime the script asks Wikidata for its TMDB and IMDb ids, using the MyAnimeList id that
YummyAnime keeps. Letterboxd matches by those ids first, and for most films the title doesn't matter at all.

One thing to know before you start: Letterboxd is about films. Anime TV series are mostly not on it, so they
don't go into the main import file.

## What you get

| File | What it is |
|---|---|
| `films.csv` | Anime films from your **Watched** list, with your ratings. This is the main file to import. |
| `watchlist.csv` | Films from your **Planned** list, for the Letterboxd watchlist. |
| `series.csv` | Watched series, OVAs and specials. Most of them won't be found on Letterboxd. |
| `yummyanime-all.csv` | All your lists in one table for you to look through. Opens in Excel. Not for Letterboxd. |

An anime counts as a film if Wikidata has a TMDB movie id for it, or if YummyAnime marks it as a movie. That's why
some OVAs end up in `films.csv`: TMDB lists them as films, and so does Letterboxd.

## Step 1. Find your profile link

Open your profile on https://yummyani.me. The link looks like `https://yummyani.me/users/id12345`. Your lists have
to be public. They are by default.

## Step 2. Convert

You need Python 3.8 or newer. No packages to install.

```
python ya2lb.py https://yummyani.me/users/id12345
```

The number alone works too: `python ya2lb.py 12345`. The files appear in the `letterboxd` folder, and the
script prints how many films it found and how many of them got a TMDB or IMDb id.

## Step 3. Import into Letterboxd

Go to https://letterboxd.com/import/ and choose `films.csv`. Letterboxd shows you what it matched before saving
anything:

- Turn on **Hide successful matches** to see only the problem rows.
- Rows marked **No match found** can be fixed with **Replace title**. Otherwise they are simply skipped.
- Rows without an id are matched by English title and year. Look at those, they're the ones that go wrong.
- **Import Titles** saves everything, and there is no undo.

`watchlist.csv` goes to the watchlist import instead: open your watchlist on Letterboxd, click the settings icon
and choose **Import**.

Don't open the CSV files in Excel before importing. Excel may save them in another encoding or with semicolons,
and then Letterboxd finds nothing. Use `yummyanime-all.csv` if you want to look at your data in Excel.

## Options

```
--out DIR                  output folder, ./letterboxd by default
--also LIST [LIST ...]     treat other lists as watched too: watching, dropped, postponed
--no-wikidata              don't look up TMDB/IMDb ids, match by title only
--yummy-app-token TOKEN    YummyAnime application token (or set YUMMY_APP_TOKEN)
```

For example, `--also dropped` adds the films you gave up on. You probably rated them, and Letterboxd has no
"dropped" status, so they become ordinary watched films.

Favorites aren't carried over. Letterboxd's import has no field for likes.

## Where the data goes

The script talks to two public services, and neither needs an account:

- `api.yani.tv`, the YummyAnime API, to read your lists. Its documentation asks applications to register and send
  a token in the `X-Application` header, and allows personal use only. At the time of writing it answers without
  a token. If that changes, create an application at https://yummyani.me and pass its token with
  `--yummy-app-token`.
- `query.wikidata.org`, with MyAnimeList ids (just numbers), to get TMDB and IMDb ids.

Nothing is sent anywhere else, and the script doesn't touch your Letterboxd account. You do the import yourself.

## Tests

```
python -m unittest
```

## License

MIT
