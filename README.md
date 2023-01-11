# PYTDL
Python YouTube Downloader: An interactive command-line tool to batch download with [`yt-dlp`](https://github.com/yt-dlp/yt-dlp)

## Requirements

- [`poetry install`](https://python-poetry.org/)
  + [`yt-dlp`](https://github.com/yt-dlp/yt-dlp)
  + [`tqdm`](https://github.com/tqdm/tqdm)
  + [`pytomlpp`](https://pypi.org/project/pytomlpp/)
  + [`humanize`](https://github.com/jmoiron/humanize)
  + [`langcodes`](https://pypi.org/project/langcodes/)
- [`ffmpeg`](https://ffmpeg.org)

## Configuration

Create a `config.toml` file in this folder to set your configuration. See [TOML](toml.io/en/) for allowed syntax.

The following settings can be altered in the top level of the config file, where they must all appear before any `[template]` tables:

```py
is_audio: bool = False # Do we only want the audio files?
is_captions: bool = False # Do we only want the captions?
is_forced: bool = False # Do we get videos despite the download history?
is_idle: bool = True # Do we avoid prompting for user action?
is_ascii: bool = False # Do we use ASCII only progress bars?
is_quiet: bool = True # Do we try to avoid continuous printouts?
is_dated: bool = False # Do we use a dated output by default?

naptime: int = 3 # average wait-time between downloads
maxres: int = 0 # highest resolution for videos, if any (0 is uncapped)

queue_file: str = pytdl/queue.txt # Where to save download queue
history_file: str = pytdl/history.txt # Where to save download history
config_file: str = pytdl/config.toml # Configuration file to load
```

### Output Templates

The output templates and yt-dlp settings can also be modified under the `[template]` table. This is usually via `[template.default]`, which applies to all downloads.

Some websites will override `[template.default]`:
- `[template.twitch]` for `twitch.tv` and similar livestream platforms (timestamped videos in `~/Streams/<streamer>/`)
- `[template.crunchyroll]` for downloading `en-US` subbed crunchyroll videos (login cookies: `pytdl/cookies/crunchy.txt`)
- `[template.playlist]` to download a numbered playlist, in oldest to newest or newest to oldest order
- `[template.podcast]` will try to download to as broad a file-name as possible, since some set the title and ID to the podcast itself, not the specific episode

Some settings can override `[template.default]` (but not website overrides like `twitch.tv`), e.g.:
- `is_dated` includes the upload/release date in the filename for default videos

To overwrite the filename [output template](https://github.com/yt-dlp/yt-dlp#output-template) for a chosen `<config>`, set its `outtmpl.default` field:
```toml
[template.<config>]
outtmpl.default = "~/Videos/%(title)s.%(ext)s"
```

For example, `config.toml` can be:

```toml
is_idle = false
is_dated = true
maxres = 1080
naptime = 10

[template.dated]
outtmpl.default = "~/Videos/%(uploader)s/%(release_date>%Y-%m-%d,timestamp>%Y-%m-%d,upload_date>%Y-%m-%d|20xx-xx-xx)s %(title)s [%(id)s].%(ext)s"
```

The path to the file can be changed during use with the `PYTDL> config <path>` command.
It can also be altered by setting the path in `config.toml`, such as `config_file = ~/.pytdl_config`.
This also allows for two simultaneous config files, with the second overriding `config.toml`.

### Logging

Logging can be altered under the `[log_config]` table in `config.toml`. See the provided default in the `PYTDL` class, which uses the `debug.log` file in the installation directory. We already set `'datefmt': '%Y-%m-%d-%H-%M-%S,uuu'` by modifying `logging.Formatter.default_time_format`, so do not override `datefmt` in a formatter unless you're happy losing the millisecond component. The schema for the dictionary is available [here](https://docs.python.org/3/library/logging.config.html#logging-config-dictschema).
