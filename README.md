# boyfriendtv yt-dlp extractor

A yt-dlp extractor plugin for **boyfriendtv.org** — the missing piece that
makes stock yt-dlp say `Unsupported URL` on BoyfriendTV pages.

BoyfriendTV serves its videos through a KVS-style player. The watch page
embeds the stream in a player config block (`hlsAuto` / `videoUrl` / CDN
`.m3u8`), not as a plain `<video>` tag, so stock yt-dlp has nothing to
hook onto. This extractor reads that config and hands yt-dlp the real HLS
master playlist, so every quality variant becomes a selectable format.

**Only `boyfriendtv.org` is used.** Any `boyfriendtv.com` URL is rewritten
to `.org` before the page is fetched.

## What it extracts

For a page like `https://www.boyfriendtv.org/videos/1273129/justcumoverme-16/`:

| Format ID | Resolution | Approx. size | Bitrate |
|-----------|-----------|--------------|---------|
| `hls-328` | 426x240 | ~69 MiB | 329k |
| `hls-757` | 854x480 | ~160 MiB | 758k |
| `hls-1452` | 1280x720 | ~307 MiB | 1452k |
| `hls-3214` | 1920x1080 | ~680 MiB | 3215k |

Metadata: title, thumbnail, duration, tags, performers (`cast`), and
description (from Open Graph + JSON-LD + the page's own tag/performer
markup).

## How it works

1. **URL normalize.** `boyfriendtv.com` → `boyfriendtv.org`.
2. **Fetch the watch page** with desktop browser headers (User-Agent,
   Referer, Accept-Language, Sec-Fetch-*). Public videos need no login.
3. **Read the player config.** `hlsAuto` is the HLS master-playlist URL.
   `videoUrl`, CDN `.m3u8` links, and KVS `get_file` URLs are fallbacks.
4. **Resolve the playlist.** The `hlsAuto` URL returns a `#EXTM3U` master
   playlist (one variant per quality, each a signed `index.m3u8` on the
   CDN). yt-dlp's `_extract_m3u8_formats` turns it into the format list.

**Do NOT string-replace the `_TPL_` placeholder.** The `hlsAuto` URL
contains a `multi=.../_TPL_.mp4` template, but the signed key is tied to
that exact path — replacing `_TPL_` with a variant id returns HTTP 403.
The master playlist (fetched from the `_TPL_` URL itself) holds the real
per-quality URLs. The extractor lets yt-dlp resolve them.

Signed URLs expire (the `end=` timestamp, ~16h). Extract and download in
the same run; do not store the stream URL for later.

## Install

### Option A — pip (recommended, permanent)

```bash
pip install .
# or, from a checkout:
#   pip install /path/to/boyfriendtv-ytdlp
```

This installs the `yt_dlp_plugins` package into your Python environment,
and stock `yt-dlp` picks it up automatically. No flags needed.

### Option B — plugin directory (no install)

Point yt-dlp at the directory that **contains** the `yt_dlp_plugins`
package:

```bash
yt-dlp --plugin-dirs /path/to/boyfriendtv-ytdlp \
  "https://www.boyfriendtv.org/videos/1273129/justcumoverme-16/"
```

> Note: `--plugin-dirs` expects a directory whose **child** holds the
> `yt_dlp_plugins` package. This repo is laid out for that: pass the repo
> root (which contains `yt_dlp_plugins/`). If you use the `plugins/`
> layout, pass the `plugins/` directory instead.

### Option C — copy into an existing yt-dlp install

```bash
cp -r yt_dlp_plugins /usr/local/lib/python3.11/dist-packages/
# (adjust the site-packages path to your Python)
```

## yt-dlp CMD usage

List the available formats (no download):

```bash
yt-dlp -F "https://www.boyfriendtv.org/videos/1273129/justcumoverme-16/"
```

Download the best quality:

```bash
yt-dlp -f best "https://www.boyfriendtv.org/videos/1273129/justcumoverme-16/"
```

Download a specific quality (720p here):

```bash
yt-dlp -f hls-1452 "https://www.boyfriendtv.org/videos/1273129/justcumoverme-16/"
```

Download with a nice filename and the title/tags in the name:

```bash
yt-dlp -f best -o "%(title)s [%(id)s].%(ext)s" \
  "https://www.boyfriendtv.org/videos/1273129/justcumoverme-16/"
```

A `.com` URL works too — it is rewritten to `.org` automatically:

```bash
yt-dlp -F "https://www.boyfriendtv.com/videos/1273129/justcumoverme-16/"
```

Show the metadata yt-dlp sees (title, duration, thumbnail, tags, cast):

```bash
yt-dlp --skip-download --print "%(id)s | %(title)s | %(duration)s" \
  --print "%(tags)s" --print "%(cast)s" \
  "https://www.boyfriendtv.org/videos/1273129/justcumoverme-16/"
```

Batch mode (one URL per line in `urls.txt`, skip already-downloaded):

```bash
yt-dlp -a urls.txt --download-archive archive.txt -f best
```

If a video is age-gated or needs a session, pass your browser cookies:

```bash
yt-dlp --cookies-from-browser chrome -f best "https://www.boyfriendtv.org/videos/1273129/justcumoverme-16/"
```

## Using it in a pipeline (how the SunnyBlueSkies ingest uses it)

The ingest calls `yt-dlp` on a URL. With the plugin installed, it can be
given a **boyfriendtv.org page URL directly** — yt-dlp extracts the stream
and downloads it. There is no need to pre-extract the stream URL first.

That is the safety net this plugin provides: if a dispatcher ever hands
the ingest a raw page URL (the old stub bug), yt-dlp + this plugin
extracts the real video instead of saving the page HTML as a stub.

For the live server the plugin is baked into the php image
(`Dockerfile.web`, step 3b) and also installed in the running container at
`/usr/local/lib/python3.11/dist-packages/yt_dlp_plugins/`, so it survives
the next image rebuild.

## Files

```
boyfriendtv-ytdlp/
  boyfriendtv.py                  standalone extractor (same code as the plugin)
  yt_dlp_plugins/
    __init__.py
    extractor/
      __init__.py
      boyfriendtv.py              the extractor plugin
  pyproject.toml                  pip-installable package
  README.md                       this file
```

## YTDLnis (Android) — using the `cmds` folder

YTDLnis has a built-in Terminal (bash) with `git`, `python`, `pip` and
`yt-dlp` ready to use. The most reliable install is the Terminal, one
command at a time (do **not** paste the whole block at once — the app's
command box will treat every word as a URL):

```bash
git clone https://github.com/SunnyBlueSkies/yt-dlp-boyfriendtv
cd yt-dlp-boyfriendtv
pip install .
```

That installs the plugin into the Python YTDLnis's yt-dlp uses, and it is
then loaded automatically for every download. No template needed.

**Using a command template instead (the `cmds` folder).** The `cmds`
folder holds YTDLnis command templates — saved sets of extra yt-dlp
arguments that get appended to a download. You can make one that loads
this plugin without installing it:

1. Get the plugin files on the phone first (`git clone` the repo, or
   download the ZIP from GitHub and extract it). Suppose it lands at
   `.../Yt-dlp/yt-dlp-boyfriendtv/` (which contains `yt_dlp_plugins/`).
2. In YTDLnis, create a command template named e.g. `BoyfriendTV` whose
   content is:

```text
--plugin-dirs .../Yt-dlp
```

   Point it at the folder that **contains** the `yt-dlp-boyfriendtv`
   folder — i.e. the **parent** of the repo, not the repo itself.
   (`--plugin-dirs` looks at the children of the directory you give it
   for a `yt_dlp_plugins` package, so the parent is the correct level.
   Verified: `--plugin-dirs <repo>` alone does not load it;
   `--plugin-dirs <parent of repo>` does.)
3. Enable that template as an extra command for video (and for data
   fetching, so the format list loads too). Then paste a boyfriendtv URL
   normally and pick a format.

**How to tell the plugin is loaded.** Do **not** use
`yt-dlp --list-extractors | grep -i boyfriend` — that list does not
include plugin extractors, so it shows nothing even when the plugin is
working. The real test is:

```bash
yt-dlp -F "https://www.boyfriendtv.org/videos/1273129/justcumoverme-16/"
```

If it lists the four `hls-*` formats (240p / 480p / 720p / 1080p), the
plugin is loaded. If it says `Unsupported URL`, the plugin is not
loaded — re-check the install or the `--plugin-dirs` parent path.

## Troubleshooting

- **`Unsupported URL` still appears.** The plugin is not loaded. Test
  with `yt-dlp -F "<a boyfriendtv.org page>"` — it should list the four
  `hls-*` formats. If it says `Unsupported URL`, the plugin is not in a
  directory yt-dlp searches (Option A or C, or the right `--plugin-dirs`
  parent path — see the YTDLnis section above).
- **403 on a stream URL.** You are using a stream URL captured earlier.
  Signed URLs expire. Re-extract from the page URL instead.
- **Only one format listed.** The page exposed a single variant, or the
  HLS master playlist download timed out. Retry; the playlist is fetched
  fresh each run.
- **No stream found.** The page may require a login or the player config
  may have changed. Open the page in a browser (logged in if needed) and
  retry with `--cookies-from-browser`.
