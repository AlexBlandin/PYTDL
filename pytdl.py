#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "yt-dlp[default]>=2025.3.31",
#   "tqdm",
#   "attrs",
#   "cattrs",
#   "ada_url",
#   "pytomlpp",
#   "humanize",
#   "langcodes",
#   "beautifulsoup4",
# ]
# ///
#
"""
A single file Python script requiring only `uv` to run, no Python install required.

Copyright 2025 Alex
"""

"""
Python YouTube Downloader: An interactive command-line tool to batch download with yt-dlp.

Requirements:
- ffmpeg: https://ffmpeg.org (`.exe`: https://www.gyan.dev/ffmpeg/builds/)
- yt_dlp: https://pypi.org/project/yt-dlp/
- tqdm: https://pypi.org/project/tqdm/
- attrs: https://pypi.org/project/attrs/
- cattrs: https://pypi.org/project/cattrs/
- ada_url: https://pypi.org/project/ada-url/
- pytomlpp: https://pypi.org/project/pytomlpp/
- humanize: https://pypi.org/project/humanize/
- langcodes: https://pypi.org/project/langcodes/

Copyright 2019 Alex Blandin
"""

import itertools as it
import json
import logging  # TODO(alex): actually use logging.warning() etc now
import logging.config
import logging.handlers
import os
import platform
import sys
from cmd import Cmd
from collections import ChainMap
from collections.abc import Callable, Iterable
from contextlib import suppress
from os import system as term
from pathlib import Path
from pprint import pprint
from random import randint, random
from subprocess import run
from time import sleep
from typing import Any, Literal, Self

import langcodes  # used to convert IETF BCP 47 (i.e., Crunchyroll's en-US) to ISO 639-2 (for ffmpeg)
import pytomlpp as toml
from ada_url import URL, URLSearchParams
from humanize import naturaltime
from tqdm import tqdm
from yt_dlp import YoutubeDL

# TODO(alex): better outtmpl approach, so we can have
# 1: optional fields without added whitespace
# 2: dynamic truncation of fields we can safely truncate (title, etc), so we never lose id etc


class PYTDL(Cmd):
  """
  PYTDL itself.

  Can be configured with config_file (uses TOML).
  """

  intro = "Download videos iteractively or from files. Type help or ? for a list of commands."
  prompt = "PYTDL> "
  queue: dict[str, str]
  "Which URLs will we download from next"
  history: set[str]
  "Which URLs have we downloaded from (successfully) already"
  deleted: set[str]
  "Which URLs have we deleted from the queue or history"
  info_cache: dict[str, dict[str, Any]]
  "URL info we can save between uses"
  local: str | Path = Path(__file__).parent / "local"
  "The path where queue.txt, config.toml, cookies/, etc., are stored"
  home: str | Path = Path.home()
  "Where the user's home directory is, where we download to by default"
  cookies: str | Path = local / "cookies"
  "Where we keep cookies for yt-dlp to use"

  ###################
  ## Configuration ##
  ###################

  is_audio: bool = False
  "Do we only want the audio files?"
  is_captions: bool = False
  "Do we only want the captions?"
  is_forced: bool = False
  "Do we get videos despite the download history?"
  is_idle: bool = True
  "Do we avoid prompting for user action?"
  is_ascii: bool = False
  "Do we use ASCII only progress bars?"
  is_quiet: bool = True
  "Do we try to avoid continuous printouts?"
  is_dated: bool = False
  "Do we use a dated output by default? (Excludes site-specific downloads i.e. twitch.tv)"

  naptime: int = 3
  "Average wait-time between downloads"
  maxres: int = 0
  "Highest resolution for videos, if any (0 is uncapped)"

  queue_file: str | Path = local / "queue.txt"
  "Where to save download queue"
  history_file: str | Path = local / "history.txt"
  "Where to save download history"
  config_file: str | Path = local / "config.toml"
  "Configuration file to load"
  secrets: str | Path | dict[str, str | dict[str, str]] = toml.load(local / "secrets.toml")
  "Where to load secrets (usernames/passwords, etc)"

  fmt_timestamp = "%(timestamp>%Y-%m-%d-%H-%M-%S,release_date>%Y-%m-%d,upload_date>%Y-%m-%d|20xx-xx-xx)s"
  fmt_date_only = "%(timestamp>%Y-%m-%d,release_date>%Y-%m-%d,upload_date>%Y-%m-%d|20xx-xx-xx)s"
  fmt_title = "%(title.:100)s"

  log_config = {  # noqa: RUF012
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
      "simple": {"format": "{levelname:<8s} :: {message}", "style": "{"},
      "precise": {"format": "{asctime} {levelname:8s} :: {message}", "style": "{"},
    },
    "filters": {"warnings_and_below": {"()": "__main__.filter_maker", "level": "WARNING"}},
    "handlers": {
      "stdout": {
        "class": "logging.StreamHandler",
        "level": "INFO",
        "formatter": "simple",
        "stream": "ext://sys.stdout",
        "filters": ["warnings_and_below"],
      },
      "stderr": {
        "class": "logging.StreamHandler",
        "level": "ERROR",
        "formatter": "simple",
        "stream": "ext://sys.stderr",
      },
      "file": {
        "class": "logging.handlers.RotatingFileHandler",
        "formatter": "precise",
        "filename": local / "debug.log",
        "level": "DEBUG",
        "maxBytes": 1024 * 1024,
        "backupCount": 3,
      },
    },
    "root": {"level": "DEBUG", "handlers": ["stderr", "stdout", "file"]},
  }
  "The configuration for logging, such that we can provide a log file and terminal output."

  template = {  # noqa: RUF012
    "default": {
      "outtmpl": str(
        home / "Videos" / f"%(uploader,uploader_id|Unknown)s {fmt_timestamp} {fmt_title} [%(id)s].%(ext)s"
      ),
      # "rm_cache_dir": True,
      "merge_output_format": "mkv",
      "overwrites": False,
      "fixup": "never",  # "warn",
      "retries": 20,
      "fragment_retries": 20,
      # "sleep_interval": # TODO(alex): dynamically fill in if a playlist etc has been submitted
      # "max_sleep_interval:" # upper bound for random sleep
      # "add_metadata": True, # hopefully added in a future update
      # "embed_metadata": True, # hopefully added in a future update
      # "trim_file_name": True, # figure out how to do this better
      # "logger": log, # TODO(alex): this
      # "download_archive": # set/path of already downloaded files, TODO(alex): look into this
      "windowsfilenames": True,
      "consoletitle": True,  # dlp sets progress in the console title
    },
    "audio": {"format": "bestaudio/best", "postprocessors": [{"key": "FFmpegExtractAudio"}]},
    "captions": {
      "allsubtitles": True,
      "skip_download": True,
      "writesubtitles": True,
    },
    "dated": {  # TODO(alex): do a better way of setting this so it can be included in any...
      "outtmpl": str(home / "Videos" / f"{fmt_date_only} {fmt_title} [%(id)s].%(ext)s"),
    },
    "show": {
      "outtmpl": str(
        home
        / "Videos"
        / "Shows"
        / "%(series)s"
        / "%(season_number|)s %(season|)s %(episode_number)02d - %(episode|)s.%(ext)s"
      )
    },
    "playlist": {
      "outtmpl": str(
        home
        / "Videos"
        / "%(playlist_title)s"
        / f"%(playlist_autonumber,playlist_index|)03d %(uploader,uploader_id|Unknown)s {fmt_title} [%(id)s].%(ext)s"
      )
    },
    "podcast": {
      "outtmpl": str(home / "Videos" / "Podcasts" / f"{fmt_title} %(webpage_url_basename)s [%(id)s].%(ext)s")
    },
    "nebula": {
      "username": secrets["nebula"]["username"],
      "password": secrets["nebula"]["password"],
    },
    "twitter": {
      "username": secrets["twitter"]["username"],
      "password": secrets["twitter"]["password"],
      "cookiefile": str(cookies / "twitter.txt"),
      "outtmpl": str(
        home / "Videos" / f"%(uploader_id,uploader|Unknown)s {fmt_timestamp} {fmt_title} [%(id)s].%(ext)s"
      ),
      # switch around so it used uploader_id,uploader bc display names are funky
    },
    "twitch": {
      # "wait_for_video": (3,10) # TODO(alex): how does this one work? should I use it?
      # "live_from_start": True # TODO(alex): is this how I want it to handle it?
      "fixup": "never",
      "outtmpl": str(
        home / "Videos" / "Streams" / "%(uploader,uploader_id|Unknown)s" / f"{fmt_timestamp} %(title)s.%(ext)s"
      ),
    },
    "youtube": {
      "embed_chapters": True,
      "embed_thumbnail": True,
      "subtitleslangs": ["en", "eng", "gb", "enGB", "enUK", "enUS", "en-GB", "en-UK", "en-US"],
      "writesubtitles": True,
    },
    "crunchyroll": {  # doesn't work currently as there's no way to pass user-agent
      "subtitleslangs": ["en-US"],
      "writesubtitles": True,
      "username": secrets["crunchyroll"]["username"],
      "password": secrets["crunchyroll"]["password"],
      "cookiefile": str(cookies / "crunchyroll.txt"),
      "user-agent": str(cookies / "useragent.txt"),
      "outtmpl": str(
        home
        / "Videos"
        / "Shows"
        / "%(series)s"
        / "%(season_number|0)s %(season|)s %(episode_number)02d - %(episode|)s.%(ext)s"
      ),
    },
  }
  "The templates that control yt-dlp, such as output file templates, formats, and such settings."

  ###############################
  ## Format/Template Selection ##
  ###############################

  def site_params(self: Self, url: str) -> dict[str, str | bool] | None:
    """Specific parameters for known sites, including credentials."""
    if self.is_crunchyroll(url):
      return self.template["crunchyroll"]
    if self.is_nebula(url):
      return self.template["nebula"]
    if self.is_twitter(url):
      return self.template["twitter"]
    if self.is_twitch(url):
      return self.template["twitch"]
    if self.is_youtube(url):
      return self.template["youtube"]
    return None

  def params(self: Self, url: str, *, take_input: bool = True) -> ChainMap[str, str | bool]:
    """YT-DLP parameters for a given url according to our current config."""
    maps: list[dict[str, str | bool]] = [{"quiet": self.is_quiet}]

    if (site_param := self.site_params(url)) is not None:
      maps.append(site_param)

    # Category specific params (shows, podcasts, playlists, etc.)
    if self.is_show(url):
      maps.append(self.template["show"])
    if self.is_podcast(url):
      maps.append(self.template["podcast"])
    if self.is_playlist(url):
      if take_input:
        maps.append({"playlistreverse": yesno("Should we reverse the ordering playlist order?", accept_return=False)})
      maps.append(self.template["playlist"])

    # Params according to settings (audio only, captions, etc.)
    if self.is_audio:
      maps.append(self.template["audio"])
    if self.is_captions:
      maps.append(self.template["captions"])
    if self.maxres:
      maps.append({"format": f"bv*[height<={self.maxres}]+ba/b[height<={self.maxres}]/bv*+ba/b"})
    if self.is_dated:
      maps.append(self.template["dated"])
    maps.append(self.template["default"])

    return ChainMap(*maps)

  ###########################
  ## URL/Video Information ##
  ###########################

  def filter_info(self: Self, info: dict) -> dict[str, dict[str, Any]]:
    """Cleans an infodict of useless fields."""
    # TODO(alex): remove useless info (fragments, etc.) so we have less mem. footprint
    return info

  def is_url(self: Self, url: str) -> bool:
    """Is this a URL?"""
    return URL.can_parse(url)

  def url_info(self: Self, url: str) -> dict[str, dict[str, Any] | Any]:
    """Get the infodict for a URL."""
    if url in self.info_cache and not ("is_live" in self.info_cache[url] and self.info_cache[url]["is_live"]):
      return self.info_cache[url]
    info: dict[str, dict[str, Any] | Any] = {}
    try:
      with YoutubeDL(
        params={
          **(self.site_params(url) or self.template["default"]),
          "simulate": True,
          "quiet": True,
          "no_warnings": True,
          "consoletitle": True,
        }
      ) as ydl:
        extracted = ydl.extract_info(url, download=False)
      if isinstance(extracted, dict):
        info = self.filter_info(extracted)
        self.info_cache[url] = info
    except Exception:
      logging.exception(f"Exception on {url}")
    return info

  def is_supported(self: Self, url: str) -> bool:
    """Check if the URL is supported."""
    # TODO(alex): speedup, url_info is way too slow rn, probably better to cache a
    # domain to disk so we can just say "it's on this site, so it's probably
    # viable", perhaps as part of history, just as a quick check? or I do a
    # better system where when we process them, if we find it's now no-longer
    # supported (since this assumes it remains) then we kick that URL to a
    # different track to handle it
    info = None
    with suppress(Exception):
      info = self.url_info(url)
    if info is None:
      if not self.is_quiet:
        print(url, "is not supported")  # noqa: T201
      return False
    return True

  def is_show(self: Self, url: str) -> bool:
    """Is a URL for a show? If so, it'll have a different folder structure."""
    # info = self.url_info(url)
    return self.is_crunchyroll(url)

  def is_playlist(self: Self, url: str) -> bool:
    """Is a URL actually a playlist? If so, it'll be downloaded differently."""
    with suppress(Exception):
      info = self.url_info(url)
      return ("playlist" in url or "youtube.com/c/" in url) or (
        info.get("playlist") is not None
        or info.get("playlist_title") is not None
        or info.get("playlist_id") is not None
      )
    return False

  def is_live(self: Self, url: str) -> bool:
    """Is a video currently live? If so, we may need to wait until it's not."""
    with suppress(Exception):
      info = self.url_info(url)
      if "is_live" in info:
        return info["is_live"]
    return False

  def is_podcast(self: Self, url: str | URL) -> bool:
    """Is a URL a podcast?"""
    url = URL(str(url))
    return "podcast" in str(url)  # TODO(alex): this is very basic

  def is_crunchyroll(self: Self, url: str | URL) -> bool:
    """Is a URL for Crunchyroll?"""
    url = URL(str(url))
    return url.hostname in {
      "crunchyroll.com",
      "www.crunchyroll.com",
    }

  def is_nebula(self: Self, url: str | URL) -> bool:
    """Is a URL for nebula.tv?"""
    url = URL(str(url))
    return url.hostname in {
      "nebula.tv",
      "www.nebula.tv",
    }

  def is_twitch(self: Self, url: str | URL) -> bool:
    """Is a URL for twitch.tv?"""
    url = URL(str(url))
    return url.hostname in {
      "twitch.tv",
      "www.twitch.tv",
    }

  def is_twitter(self: Self, url: str | URL) -> bool:
    """Is a URL for twitter.com?"""
    url = URL(str(url))
    return url.hostname in {
      "twitter.com",
      "www.twitter.com",
      "x.com",
      "www.x.com",
    }

  def is_youtube(self: Self, url: str | URL) -> bool:
    """Is a URL for Youtube?"""
    url = URL(str(url))
    return url.hostname in {
      "www.youtube.com",
      "youtube.com",
      "youtu.be",
      "m.youtube.com",
      "www.youtube-nocookie.com",
      "piped.video",
      "piped.projectsegfau.lt",
    }

  #########
  ## I/O ##
  #########

  def ensure_dir(self: Self, url: str | Path) -> None:
    """Ensure we can place a URL's resultant file in its expected directory, recursively (ignoring templates)."""
    # Path(self.config(url, take_input=False)["outtmpl"]).expanduser().parent.mkdir(
    #   parents=True, exist_ok=True
    # )  # can't use bc. template's parents
    for parent in [
      parent
      for parent in Path(self.params(url, take_input=False)["outtmpl"]).expanduser().parents
      if not parent.exists() and "%(" not in parent.name and ")s" not in parent.name
    ][::-1]:
      parent.mkdir()

  def readfile(self: Self, path: str | Path) -> list[str]:
    """Reads lines from a file."""
    if (f := Path(path).expanduser()).is_file():
      return unique_list(map(self.clean_url, filter(None, map(str.strip, f.read_text(encoding="utf8").splitlines()))))
    return []

  def writefile(self: Self, path: str | Path, lines: list[str]) -> None:
    """Writes lines to a file."""
    f = Path(path).expanduser()
    f.write_text("\n".join(unique_list(map(self.clean_url, filter(None, lines)))), encoding="utf8", newline="\n")

  def update_history(self: Self) -> None:
    """Update the history file."""
    self.history |= set(self.readfile(self.history_file))
    self.writefile(self.history_file, sorted(self.history))

  def clean_url(self: Self, url: str | URL):  # noqa: ANN201, C901, D102
    # TODO(alex): https://github.com/ClearURLs/Addon
    if isinstance(url, URL) or URL.can_parse(url):
      url = URL(str(url))
      if self.is_youtube(url):
        if url.hostname in {"youtu.be"}:
          search = URLSearchParams(f"v={url.pathname.removeprefix('/')}")
          url.search = str(search)
          url.pathname = "/watch"
        url.hostname = "www.youtube.com"
        if not any(url.pathname.startswith(pn) for pn in ("/watch", "/playlist", "/@", "/channel/", "/c/", "/user/")):
          url.pathname = "/watch"
          vid = url.pathname.split("/")[-1]
          url.search = f"v={vid}"
        if url.search:
          search = URLSearchParams(url.search)
          if search.has("vi") and not search.has("v"):
            search.set("v", search.get("vi"))
          for key in search.keys():
            if key not in {"v", "list"}:
              search.delete(key)
          if url.pathname != "/playlist":
            search.delete("list")
          url.search = str(search)
      elif self.is_twitch(url):
        # clean "www.twitch.tv/videos/1234567890?filter=archives&sort=time" -> "www.twitch.tv/videos/1234567890"
        if url.search and url.pathname.startswith("/videos/"):
          url.search = ""
      elif url.hostname in {"imgur.artemislena.eu"}:
        if "/gallery/" in url.pathname:
          url.hostname = "imgur.com"
        else:
          url.hostname = "i.imgur.com"
      url = url.href
    else:
      print(f"Was unable to parse {url} as a URL. If you believe this is a bug, bring it up with the WHATWG URL spec.")
    return url

  def download(self: Self, raw_url: str) -> None:
    """Actually download something."""
    url = self.clean_url(raw_url)
    with YoutubeDL(self.params(url)) as ydl:
      # ydl.evaluate_outtmpl(ydl.params["outtmpl"], ydl.extract_info(url)) # TODO(alex): for better ensure_dir?
      self.ensure_dir(url)
      try:
        r = ydl.download(url)
      except KeyboardInterrupt:
        raise
      except SystemExit:
        raise
      except Exception as err:  # noqa: BLE001
        print(err)  # noqa: T201
        r = 1
    if r:
      if not self.is_idle and yesno(f"Did {url} download properly?"):
        self.history.add(raw_url)
    else:
      self.history.add(raw_url)

  def from_index(self: Self, i: str) -> str | None:
    """Gets the i'th URL in the queue."""
    queue = list(self.queue)
    if i.isdecimal() or (len(i) > 1 and i[0] == "-" and i[1:].isdecimal()):
      return queue[int(i)]
    return None

  ###################
  ## User Settings ##
  ###################

  def do_mode(self: Self, _arg: str = "") -> None:
    """Prints details about the mode of operation and system."""

    def yesify(b: bool, /) -> Literal["Yes", "No"]:  # noqa: FBT001
      return "Yes" if b else "No"

    print("Mode:", "Idle" if self.is_idle else "Interactive")  # noqa: T201
    print("ASCII:", yesify(self.is_ascii))  # noqa: T201
    print("Quiet:", yesify(self.is_quiet))  # noqa: T201
    print("Audio:", yesify(self.is_audio))  # noqa: T201
    print("Captions:", yesify(self.is_captions))  # noqa: T201
    print("Dated:", yesify(self.is_dated))  # noqa: T201
    print("Sleep interval:", self.naptime, "seconds")  # noqa: T201
    print("Max resolution:", f"{self.maxres}p" if self.maxres else "Unlimited")  # noqa: T201

  def do_config(self: Self, arg: str | Path = "") -> None:
    """
    Load a TOML configuration on a given path, default to config_file.

    config | config [path]
    """
    arg = Path(arg).expanduser()
    config = toml.load(arg if arg.is_file() else Path(self.config_file).expanduser())

    assert self.__annotations__ == self.__class__.__annotations__  # no shennanigans... for now  # noqa: S101
    for key, t in self.__annotations__.items():  # initialise annotated types
      if key not in self.__dict__ and key not in self.__class__.__dict__:
        if callable(t):
          self.__dict__[key] = t()
        else:
          logging.exception(
            f"An unusable type {t} was annotated as a field in {type(self)} and could not be initialised"
          )
          raise TypeError(key, t)

    for key, val in config.items():
      if (key in self.__dict__ or key in PYTDL.__dict__) and isinstance(val, type(getattr(self, key))):
        if isinstance(val, dict):
          strict_dict_update(getattr(self, key), val, [key])
        else:
          setattr(self, key, val)

    # Some fields must be Paths # TODO(alex): these don't propagate!
    for field in ("home", "local", "cookies", "queue_file", "history_file", "config_file", "secrets"):
      match getattr(self, field):
        case str(is_str):
          setattr(self, field, Path(is_str))
        case Path() | dict():
          pass
        case _:
          raise TypeError

    # self.secrets must be a dict as if loaded from TOML
    match self.secrets:
      case str(secrets_file):
        self.secrets = toml.load(Path(secrets_file))
      case Path() as secrets_file:
        self.secrets = toml.load(Path(secrets_file))
      case dict(secrets):
        pass
      case _:
        raise TypeError

    logging.config.dictConfig(self.log_config)

  def do_audio(self: Self, _arg: str = "") -> None:
    """Toggle whether PYTDL treat urls as only audio by default."""
    self.is_audio = not self.is_audio
    print("Audio!" if self.is_audio else "Not audio...")  # noqa: T201

  def do_captions(self: Self, _arg: str = "") -> None:
    """Toggle whether PYTDL treat urls as only captions by default."""
    self.is_captions = not self.is_captions
    print("Captions!" if self.is_captions else "Not captions...")  # noqa: T201

  def do_quiet(self: Self, _arg: str = "") -> None:
    """Toggle whether PYTDL is quiet or not."""
    self.is_quiet = not self.is_quiet
    print("Shh" if self.is_quiet else "BOO!")  # noqa: T201

  def do_dated(self: Self, _arg: str = "") -> None:
    """Toggle whether PYTDL dates videos by default."""
    self.is_dated = not self.is_dated
    print("Dating now" if self.is_dated else "Dateless...")  # noqa: T201

  def do_forced(self: Self, _arg: str = "") -> None:
    """Toggle whether to force redownloads of videos."""
    self.is_forced = not self.is_forced
    print("Force downloads" if self.is_forced else "Doesn't force downloads")  # noqa: T201

  def do_idle(self: Self, _arg: str = "") -> None:
    """Idle mode keeps you from having to interact with the batch downloader, letting you go do something else."""
    self.is_idle = not self.is_idle
    print("Idling" if self.is_idle else "Interactive")  # noqa: T201

  def do_naptime(self: Self, arg: str) -> None:
    """How long do we sleep between downloads (on average)?"""
    if arg.isdecimal():
      self.naptime = int(arg)
    self.naptime = max(self.naptime, 0)
    print(f"We sleep for {self.naptime}s on average.")  # noqa: T201

  def do_res(self: Self, arg: str) -> None:
    """
    Provide a maximum resolution to download to, or nothing to remove the limit:

    >>> res | res 1080
    """  # noqa: D415
    if arg.isdecimal():
      self.maxres = int(arg)
    else:
      self.maxres = 0
    print(f"We will go up to {self.maxres}p" if self.maxres else "We have no limits on resolution")  # noqa: T201

  ###################
  ## User Commands ##
  ###################

  def do_print(self: Self, arg: str) -> None:
    """
    Print the queue, or certain URLs in it:

    >>> print | print 0 | @ 0 | @ 1 2 5 | @ -1
    """  # noqa: D415
    print(f"There are {len(self.queue)} URLs in the queue")  # noqa: T201
    if len(self.queue):
      if len(arg):
        for url_ in arg.split():
          url = self.from_index(url_)
          if url:
            print(url)  # noqa: T201
      else:
        for url in self.queue:
          print(url)  # noqa: T201

  def do_info(self: Self, arg: str) -> None:
    """
    Print useful info for given URLs:

    >>> info [url] [...] | info 0 5 -2 [url] [...]
    """  # noqa: D415
    for url_ in arg.split():
      info = "No info found"
      try:
        url = u if (u := self.from_index(url_)) else url_
        info = self.url_info(url)
        print(f"URL: {url}")  # noqa: T201
        print(f"Title: {info['fulltitle']}")  # noqa: T201
        print("Playlist" if self.is_playlist(url) else "Livestream" if self.is_live(url) else "VOD")  # noqa: T201
      except KeyError as err:
        print(err)  # noqa: T201
      except Exception as err:
        print(info)  # noqa: T201
        print(err)  # noqa: T201
        raise

  def do_infodump(self: Self, urls: str) -> None:
    """
    Dumps all info of given URLs to JSON files in CWD:

    >>> dump [url] [...]
    """  # noqa: D415
    for url in urls.split():
      info = self.url_info(url)
      (self.local / "info" / f"{info.get('id') or 'dump'}.json").write_text(json.dumps(info))

  def do_echo(self: Self, arg: str) -> None:
    """Echoes all URLs as it would try to download them (cleaned up and with potential fixes for common typos etc)."""
    if len(arg) and len(q := arg.split()):
      for p in q:
        if self.is_url(p):
          print(self.clean_url(p))  # noqa: T201
        else:
          print(p)  # noqa: T201

  def do_add(self: Self, arg: str, *, allow_unsupported: bool = False) -> None:
    """
    Add a url to the list (space separated for multiple):

    >>> add [url] | [url] | [url] [url] [url] | add front [url] [url] [url]
    """  # noqa: D415
    temp = None
    if len(arg):
      if len(q := arg.split(maxsplit=1)) > 1 and q[0] == "front":
        arg = q[1]
        temp = dict(self.queue)
        self.queue = {}
      # TODO(alex): better valid URL check, fix common input errors (https://a.bchttps://c.de, missing http, etc)
      for url in arg.split():
        if len(url) > 4 and (allow_unsupported or self.is_supported(url)):  # noqa: PLR2004
          url = self.clean_url(url)
          self.queue[url] = url
    if temp:
      self.queue |= temp
    for url in self.queue:
      self.deleted.discard(url)  # If we add it back, it should stay, unless we delete again, etc.

  def do_del(self: Self, arg: str) -> None:
    """
    Delete a url from the queue and/or history:

    >>> del [url] | - [url]
    """  # noqa: D415
    for url in arg.split():
      if len(url) and url in self.queue and yesno(f"Do you want to remove {url} from the queue?"):
        del self.queue[url]
        self.deleted.add(url)
        if url in self.info_cache:
          del self.info_cache[url]
      if len(url) and url in self.history and yesno(f"Do you want to remove {url} from the history?"):
        self.history -= {url}
        if url in self.info_cache:
          del self.info_cache[url]

  def do_drop(self: Self, arg: str | Path) -> None:
    """
    Drop the queue:

    >>> drop | drop [queue file]
    """  # noqa: D415
    if isinstance(arg, str) and len(arg) == 0:
      arg = self.queue_file
    self.queue = {k: v for k, v in self.queue.items() if k not in self.history}
    if len(self.queue):
      print(f"There are {len(self.queue)} urls in the queue that have not been downloaded.")  # noqa: T201
    if yesno(f"Do you want to remove all {len(self.queue)} urls from the queue?") and yesno("Are you sure about this?"):
      self.queue.clear()
    if yesno(f"Do you want to remove all {len(self.readfile(arg))} urls the queue file?") and yesno(
      "Are you sure about this?"
    ):
      self.writefile(arg, [])
    self.do_forget()

  def do_forget(self: Self, arg: str | Path = "") -> None:
    """
    Forget all current known history:

    >>> forget | forget [history file]
    """  # noqa: D415
    if isinstance(arg, str) and len(arg) == 0:
      arg = self.history_file
    if yesno("Do you want to forget the history of dl'd URLs?") and yesno("Are you sure about this?"):
      self.history.clear()
      self.info_cache.clear()
    if yesno("Do you want to forget the history file?") and yesno("Are you sure about this?"):
      self.writefile(arg, [])

  def do_get(self: Self, arg: str | list[str]) -> None:
    """
    Get the video from given URLs:

    >>> get [url] [...] | ! [url] [...]
    """  # noqa: D415
    still_live, urls = [], arg.split() if isinstance(arg, str) else arg
    urls = list(map(self.clean_url, urls))
    if len(urls):
      set_title(f"downloading {len(urls)} URL{'s' * (len(urls) != 1)}")
      print(f"Getting {len(urls)} URL{'s' * (len(urls) != 1)}")  # noqa: T201
      try:
        for i, url in tqdm(enumerate(urls, 1), ascii=self.is_ascii, ncols=100, unit="vid"):
          if (
            self.is_supported(url)
            and (
              url not in self.history or self.is_forced or (not self.is_idle and yesno(f"Try download {url} again?"))
            )
          ) or "playlist" in url:
            set_title(f"[{i}/{len(urls)}] {url}")
            if self.is_live(url) and (self.is_idle or yesno("Currently live, shall we skip and try again later?")):
              still_live.append(url)
              continue
            self.download(url)
            sleep(randint(0, self.naptime * 2) + random())
      except KeyboardInterrupt:
        print()  # noqa: T201
        print("Stopped by user")  # noqa: T201
      except Exception:
        raise
    else:
      print("No videos to download")  # noqa: T201
    self.update_history()
    if still_live:
      self.do_wait(" ".join(still_live))

  def do_getall(self: Self, arg: str = "") -> None:
    """
    Get the videos in the queue, including any from a given file:

    >>> getall [file] | . [file]
    """  # noqa: D415
    set_title("organising queue")
    if len(arg) or len(self.queue) == 0:
      self.do_load(arg)
    self.do_get(list(self.queue))

  def do_load(self: Self, arg: str = "", *, allow_unsupported: bool = False) -> None:
    """
    Load the contents of a file into the queue (add a - to not load the history):

    >>> load [file] | load- [file] | : [file] | :- [file]
    """  # noqa: D415
    path, pre, get_history = arg, len(self.queue), True
    if path.startswith("-"):
      path, get_history = path.removeprefix("-"), False
    if len(path) == 0 or not Path(path).expanduser().is_file():
      path = self.queue_file
    for line in self.readfile(path):
      self.do_add(line, allow_unsupported=allow_unsupported)
    post = len(self.queue)
    if post > pre:
      print(f"Added {post - pre} URLs from {path}")  # noqa: T201
    if get_history:
      self.update_history()
    set_title(f"loaded {len(self.queue)} URLs {f', {len(self.queue) - pre} new' if pre else ''}")

  def do_save(self: Self, arg: str = "") -> None:
    """
    Save the queue to a file (defaults to queue_file, add a - to not save the history):

    >>> save [file] | save- [file] | # [file] | #- [file]
    """  # noqa: D415
    set_title("saving")
    path, queue, set_history = arg, dict(self.queue), True
    if path.startswith("-"):
      path, set_history = path.removeprefix("-"), False
    if len(path) == 0:
      path = self.queue_file
    if len(lines := self.readfile(path)):
      queue |= {line: line for line in lines}
    if len(queue):
      self.writefile(path, [url for url in queue if url not in self.history and url not in self.deleted])
    if set_history:
      self.update_history()

  def do_wait(self: Self, arg: str = "") -> None:
    """
    Wait on currently live videos, checking in slowing intervals from 10s to 10mins:

    >>> wait | wait [url] [...]
    """  # noqa: D415
    urls, i = arg.split(), 0
    if len(arg) == 0 or len(urls) == 0:
      urls = list(self.queue)
    elapsed, intervals = 0, [10, 30, 60]
    wait_next = list(zip(intervals, intervals[1:] + [3600 * 24], strict=True))
    while len(urls):
      url = urls.pop(0)
      set_title(f"waiting on {url}")
      if self.is_live(url):
        wait, next_wait = wait_next[i]
        elapsed += wait
        if elapsed > next_wait * 2 and i < len(intervals) - 1:
          i += 1
        set_title(f"waiting on {url}, checking in {naturaltime(wait, future=True)}")
        try:
          sleep(wait + randint(0, wait // 3) + random())  # w/ jitter
        except KeyboardInterrupt:
          if not yesno("Test if the URL is currently livestreaming?") and not yesno("Do you want to continue waiting?"):
            break
        if self.is_live(url):
          urls.append(url)
      if not self.is_live(url):
        self.do_get(url)
        elapsed, i = 0, 0  # reset since we just spent a chunk of time downloading

  def do_merge(self: Self, arg: str = "") -> None:
    """
    Merge subtitles within a given directory, recursively.

    Defaults to searching '~/Videos/Shows/', otherwise provide an argument for the path:

    >>> merge | merge [path-to-directory]
    """
    path = Path(arg).expanduser() if len(arg) else self.home / "Videos" / "Shows"
    merge_subs(path)

  def do_clean(self: Self, arg: str = "") -> None:
    """
    Cleans leading '0 ', trailing ' - ' and '.', and '  ' from file names, such as for missing fields.

    Defaults to searching '~/Videos/Shows/', otherwise provide an argument for the folder:

    >>> clean | clean [path-to-directory].
    """
    path = Path(arg).expanduser() if len(arg) else self.home / "Videos" / "Shows"
    vids = list(filter(Path.is_file, path.rglob("*")))
    for vid in vids:
      if vid.name.startswith("0 "):
        new_stem = vid.stem.removeprefix("0 ").strip().removesuffix(".").removesuffix(" -")
        while "  " in new_stem:
          new_stem = new_stem.replace("  ", " ")
        vid.rename(vid.with_stem(new_stem))

  def do_clear(self: Self, _arg: str = "") -> None:
    """Clear the screen."""
    if platform.system() == "Windows":
      term("cls")  # noqa: S607, S605
    else:
      term("clear")  # noqa: S605, S607

  def do_exit(self: Self, _arg: str = "") -> Literal[True]:
    """Exit PYTDL."""
    logging.debug("Exitting sequence started")
    arg = Path(_arg).expanduser()
    arg = arg if arg.is_file() else Path(self.queue_file).expanduser()
    self.do_save(_arg)
    set_title("exitting")
    logging.debug(f"Exitting, saved {len(self.readfile(arg))} URLs to {arg}")
    print(f"Exitting, saved {len(self.readfile(arg))} URLs to {arg}")  # noqa: T201
    sleep(2.0)
    logging.debug("Exit complete")
    return True

  ##################
  ## Cmd Handlers ##
  ##################

  def postcmd(self: Self, stop, _line) -> bool:  # noqa: ANN001, D102
    set_title(f"{len(self.queue)} queued URLs" if len(self.queue) else "")
    return stop

  def preloop(self: Self) -> None:  # noqa: D102
    set_title("starting up")
    self.do_config()
    self.do_config()  # in case of redirection
    logging.debug(f"Config file loaded ({self.config_file})")
    self.do_load(allow_unsupported=True)
    self.do_mode()

  #########################
  ## Shorthand Operators ##
  #########################

  def default(self: Self, arg: str) -> None:  # noqa: D102
    op, arg = arg[0], arg[1:].strip()
    # TODO(alex): come up with a general operator system? multi-char + multi-op + infix
    match op:
      case ".":
        self.do_getall(arg)
      case "!":
        self.do_get(arg)
      case "-":
        self.do_del(arg)
      case ":":
        self.do_load(arg)
      case "#":
        self.do_save(arg)
      case "*":
        self.update_history()
      case "@":
        self.do_print(arg)
      case _:
        self.do_add(f"{op}{arg}")


#######################
## Regular Functions ##
#######################


def strict_dict_update(old: dict, new: dict, path: list[str]) -> None:
  """Recursively update a dictionary according to the implicit schema of its existing keys/structure and types."""
  for k, v in new.items():
    pth = [*path, k]
    if k in old and isinstance(v, dict):
      strict_dict_update(old[k], v, pth)
    elif k in old and isinstance(v, type(old[k])):
      logging.info(f"Config {'.'.join(map(str, pth))} = {v}")
      old[k] = v
    elif k in old:
      logging.warning(
        f"Config {'.'.join(map(str, pth))} was set to {v} ({type(v)}) but the default is of type ({type(old[k])})"
      )
      old[k] = v
    else:
      logging.warning(f"Config {'.'.join(map(str, pth))} has been loaded but is not present in the default")
      old[k] = v


def set_title(s: str) -> None:
  """Set the console title."""
  print(f"\33]0;PYTDL: {s}\a", end="", flush=True)  # noqa: T201


def unique_list(xs: Iterable) -> list:
  """Reduce a list to only its unique elements `[1,1,2,7,2,4] -> [1,2,7,4]`."""
  return list(dict(zip(xs, it.repeat(0))))


def yesno(
  msg: str = "", *, accept_return: bool | None = True, yes: set[str] | None = None, no: set[str] | None = None
) -> bool:
  """Keep asking until they say yes or no."""
  if no is None:
    no = {"n", "no"}
  if yes is None:
    yes = {"y", "ye", "yes"}
  fmt = "[Y/n]" if accept_return else "[y/N]" if accept_return is not None else "[y/n]"
  while True:
    reply = input(f"\r{msg} {fmt}: ").strip().lower()
    if reply in yes or (not reply and accept_return):
      return True
    if reply in no or (not reply and accept_return is not None):
      return False


def filter_maker(level: str) -> Callable[..., bool]:
  """Create a filter to remove all below, say, "WARNING"."""
  level_int: int = getattr(logging, level)

  def fltr(record: logging.LogRecord) -> bool:
    return record.levelno <= level_int

  return fltr


def merge_subs(path: Path = Path()) -> None:
  """Merge .ass subtitles into .mp4 videos non-destructively (by switching to .mkv)."""
  vids = list(filter(Path.is_file, path.rglob("*.mp4")))
  subs = list(filter(Path.is_file, path.rglob("*.ass")))
  _pair: dict[Path, Path | None] = dict.fromkeys(vids)
  lang = {}
  for sub in subs:
    suffix = next(filter(langcodes.tag_is_valid, (s.removeprefix(".") for s in sub.suffixes)), None)
    if suffix:
      v = sub.with_stem(sub.stem.removesuffix(f".{suffix}")).with_suffix(".mp4")
      if v in _pair:
        lang[sub] = langcodes.get(suffix).to_alpha3()
        _pair[v] = sub
    else:
      print(f"We are missing a language code (i.e. en-US) on {sub}")  # noqa: T201

  pair: dict[Path, Path] = {vid: sub for vid, sub in _pair.items() if sub is not None}
  for vid, sub in pair.items():
    for _ in range(2):  # how many tries
      if (
        r := run(
          f'ffmpeg -v "warning" -i "{vid}" -i "{sub}" -map 0 -c:v copy -c:a copy -map "-0:s" -map "-0:d" -c:s copy -map "1:0" "-metadata:s:s:0" "language={lang[sub]}" "{vid.with_suffix(".mkv")}" ',  # noqa: E501
          check=False,
        )
      ).returncode:
        pprint(r)  # noqa: T203
      else:
        break
    else:
      continue  # couldn't merge
    if vid.with_suffix(".mkv").is_file():
      with suppress(Exception):
        vid.unlink()
        sub.unlink()
      # we fail to unlink if, say, someone is already watching it!


if __name__ == "__main__":
  logging.Formatter.default_time_format = "%Y-%m-%d-%H-%M-%S"
  pytdl = PYTDL()
  if len(sys.argv) >= 2:  # noqa: PLR2004
    pytdl.preloop()
    for op in map(str.strip, " ".join(sys.argv[1:]).split(",")):
      if op.startswith("cd "):
        os.chdir(Path(op.removeprefix("cd ")))
      else:
        pytdl.onecmd(op)
    pytdl.do_exit()
    pytdl.postloop()
  else:
    os.chdir(Path.home())  # so we're always somewhere safe
    pytdl.cmdloop()
