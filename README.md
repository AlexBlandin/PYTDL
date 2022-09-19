# PYTDL
Python Youtube Downloader: An interactive command-line tool to batch download with yt-dlp

## Requirements

- [`poetry install`](https://python-poetry.org/)
  + [`yt-dlp`](https://github.com/yt-dlp/yt-dlp)
  + [`tqdm`](https://github.com/tqdm/tqdm)
  + [`pytomlpp`](https://pypi.org/project/pytomlpp/)
  + [`humanize`](https://github.com/jmoiron/humanize)
  + [`langcodes`](https://pypi.org/project/langcodes/)
- [`ffmpeg`](https://ffmpeg.org)

## Configuration

Create a `config.toml` file in this folder to set your configuration. See [TOML](toml.io/en/) for syntax.
The following settings can be altered in the top level:

```py
is_audio: bool = False # Do we only want the audio files?
is_captions: bool = False # Do we only want the captions?
is_forced: bool = False # Do we get videos despite the download history?
is_idle: bool = True # Do we avoid prompting for user action?
is_ascii: bool = False # Do we use ASCII only progress bars?
is_quiet: bool = True # Do we try to avoid continuous printouts?
is_dated: bool = False # Do we use a dated output by default? (Excludes site-specific downloads i.e. twitch.tv)

naptime: int = 3 # average wait-time between downloads
maxres: int = 0 # highest resolution for videos, if any (0 is uncapped)

queue_file: str = pytdl/queue.txt # Where to save download queue
history_file: str = pytdl/history.txt # Where to save download history
config_file: str = pytdl/config.toml # Configuration file to load
```

The output templates and yt-dlp settings can also be modified under the `[ytdlp]` table.
This is usually via `[ytdlp.default]`, which applies to all downloads.
Some websites will override `[ytdlp.default]`:
- `[ytdlp.twitch]` for `twitch.tv` and similar livestream platforms (timestamped videos in `~/Streams/<streamer>/`)
- `[ytdlp.crunchyroll]` for downloading enUS subbed crunchyroll videos (login cookies: `pytdl/cookies/crunchy.txt`)
- `[ytdlp.playlist]` to download a numbered playlist, in oldest to newest or newest to oldest order (typically youtube)

Some settings can override `[ytdlp.default]` (but not website overrides):
- `[ytdlp.dated]` to include the upload/release date in the filename

To overwrite the filename output template for a chosen `<config>`, set its table accordingly:
```toml
[ytdlp.<config>.outtmpl]
default: str
```

For example, `config.toml` can be:

```toml
is_idle = false
is_dated = true
maxres = 1080
naptime = 10

[ytdlp.dated.outtmpl]
default = "~/Videos/%(uploader)s/%(release_date>%Y-%m-%d,timestamp>%Y-%m-%d,upload_date>%Y-%m-%d|20xx-xx-xx)s %(title)s [%(id)s].%(ext)s"
```

The path to the file can be changed during use with the `pyt-dl> config <path>` command.
It can also be altered by setting the path in `config.toml`, such as `config_file = ~/.pytdl_config`.
This also allows for two simultaneous config files, with the second overriding `config.toml`.
