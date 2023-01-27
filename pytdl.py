from collections import ChainMap
from pathlib import Path
from typing import Any
from random import randint, random
from time import sleep
from cmd import Cmd
from os import system as term
import logging.handlers
import logging.config
import platform
import logging # TODO: logging # setup, so just need to call logging.warning() etc directly now
import json
import os

from merge_subs import merge_subs
from humanize import naturaltime
from yt_dlp import YoutubeDL
from tqdm import tqdm
import pytomlpp as toml

# TODO: better outtmpl approach, so we can have
# 1: optional fields without added whitespace
# 2: dynamic truncation from fields we can safely truncate (title, etc) so we never lose id etc
# TODO: look into post-processing, can we clean up file names, etc, may help with these

# TODO: MRU caching to a file so we don't need to make so many spurious lookups between bootup, etc

def set_title(s: str):
  print(f"\33]0;PYTDL: {s}\a", end = "", flush = True)

def yesno(msg = "", accept_return = True, replace_lists = False, yes_list = set(), no_list = set()):
  "Keep asking until they say yes or no"
  yes_list = yes_list if replace_lists else {"y", "ye", "yes"} | yes_list
  no_list = no_list if replace_lists else {"n", "no"} | no_list
  fmt = "[Y/n]" if accept_return else "[y/N]"
  while True:
    reply = input(f"\r{msg} {fmt}: ").strip().lower()
    if reply in yes_list or (accept_return and reply == ""):
      return True
    if reply in no_list: return False

def filter_maker(level):
  level: int = getattr(logging, level)
  
  def filter(record: logging.LogRecord) -> bool:
    return record.levelno <= level
  
  return filter

class PYTDL(Cmd):
  """
  PYTDL itself.
  
  Can be configured with config_file (uses TOML).
  """
  intro = "Download videos iteractively or from files. Type help or ? for a list of commands."
  prompt = "PYTDL> "
  queue: dict[str, str] = {}
  "Which URLs will we download from next"
  history: set[str] = set()
  "Which URLs have we downloaded from (successfully) already"
  deleted: set[str] = set()
  "Which URLs have we deleted from the queue or history"
  info_cache: dict[str, dict[str, Any]] = {}
  "URL info we can save between uses"
  local = Path(__file__).parent
  "The local path is where PYTDL is installed"
  cookies = local / "cookies"
  "Where we keep cookies for yt-dlp to use"
  
  #################
  # Configuration #
  #################
  
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
  secrets = toml.load(local / "secrets.toml")
  "Where to load secrets (usernames/passwords, etc)"
  
  log_config = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
      "simple": {
        "format": "{levelname:<8s} :: {message}",
        "style": "{"
      },
      "precise": {
        "format": "{asctime} {levelname:8s} :: {message}",
        "style": "{"
      }
    },
    "filters": {
      "warnings_and_below": {
        "()": "__main__.filter_maker",
        "level": "WARNING"
      }
    },
    "handlers": {
      "stdout": {
        "class": "logging.StreamHandler",
        "level": "INFO",
        "formatter": "simple",
        "stream": "ext://sys.stdout",
        "filters": ["warnings_and_below"]
      },
      "stderr": {
        "class": "logging.StreamHandler",
        "level": "ERROR",
        "formatter": "simple",
        "stream": "ext://sys.stderr"
      },
      "file": {
        "class": "logging.handlers.RotatingFileHandler",
        "formatter": "precise",
        "filename": local / "debug.log",
        "level": "DEBUG",
        "maxBytes": 1024*1024,
        "backupCount": 3
      }
    },
    "root": {
      "level": "DEBUG",
      "handlers": ["stderr", "stdout", "file"]
    }
  }
  "The configuration for logging, such that we can provide a log file and terminal output."
  
  template = {
    "audio": {
      "format": "bestaudio/best",
      "postprocessors": [{
        "key": "FFmpegExtractAudio"
      }]
    },
    "captions": {
      "allsubtitles": True,
      "skip_download": True,
      "writesubtitles": True,
    },
    "dated": { # TODO: do a better day of setting this so it can be included in any...
      "outtmpl": {
        "default":
          str(
            Path.home() / "Videos" /
            "%(timestamp>%Y-%m-%d,release_date>%Y-%m-%d,upload_date>%Y-%m-%d|20xx-xx-xx)s %(title.:100)s [%(id)s].%(ext)s"
          )
      }
    },
    "show": {
      "outtmpl": {
        "default":
          str(
            Path.home() / "Videos" / "Shows" / "%(series)s" /
            "%(season_number|)s %(season|)s %(episode_number)02d - %(episode|)s.%(ext)s"
          )
      }
    },
    "playlist": {
      "outtmpl": {
        "default":
          str(
            Path.home() / "Videos" / "%(playlist_title)s" /
            "%(playlist_autonumber,playlist_index|)03d %(title.:100)s.%(ext)s"
          )
      }
    },
    "podcast": {
      "outtmpl": {
        "default": str(Path.home() / "Videos" / "Podcasts" / "%(title.:100)s %(webpage_url_basename)s [%(id)s].%(ext)s")
      }
    },
    "ja": {
      # japasm
    },
    "twitter": {
      # switch around so it used uploader_id,uploader bc display names are funky
    },
    "twitch": {
      # "wait_for_video": (3,10) # TODO: how does this one work? should I use it?
      # "live_from_start": True # TODO: is this how I want it to handle it?
      "fixup": "never",
      "outtmpl": {
        "default":
          str(
            Path.home() / "Videos" / "Streams" / "%(uploader,uploader_id|Unknown)s" /
            "%(timestamp>%Y-%m-%d-%H-%M-%S,release_date>%Y-%m-%d,upload_date>%Y-%m-%d|20xx-xx-xx)s %(title)s.%(ext)s"
          )
      }
    },
    "crunchyroll": {
      "subtitleslangs": ["en-US"],
      "writesubtitles": True,
      # "username": secrets["crunchyroll"]["username"], # example of how it looks
      # "password": secrets["crunchyroll"]["password"], # example of how it looks
      "cookiefile": str(cookies / "crunchy.txt"),
      "outtmpl": {
        "default":
          str(
            Path.home() / "Videos" / "Shows" / "%(series)s" /
            "%(season_number|0)s %(season|)s %(episode_number)02d - %(episode|)s.%(ext)s"
          )
      }
    },
    "default": {
      "outtmpl": {
        "default": str(Path.home() / "Videos" / "%(uploader,uploader_id|Unknown)s %(timestamp>%Y-%m-%d-%H-%M-%S,release_date>%Y-%m-%d,upload_date>%Y-%m-%d|20xx-xx-xx)s %(title.:100)s [%(id)s].%(ext)s")
      },
      # "rm_cache_dir": True,
      "merge_output_format": "mkv",
      "overwrites": False,
      "fixup": "never", # "warn",
      "retries": 20,
      "fragment_retries": 20,
      # "sleep_interval": # TODO: dynamically fill in if a playlist etc has been submitted
      # "max_sleep_interval:" # upper bound for random sleep
      # "add_metadata": True, # hopefully added in a future update
      # "embed_metadata": True, # hopefully added in a future update
      # "trim_file_name": True, # figure out how to do this better
      # "logger": log, # TODO: this
      # "download_archive": # set/path of already downloaded files, TODO: look into this
      "windowsfilenames": True,
      "consoletitle": True, # dlp sets progress in the console title
    }
  }
  "The templates that control yt-dlp, such as output file templates, formats, and such settings."
  
  #############################
  # Format/Template Selection #
  #############################
  
  def config(self, url: str, *, take_input = True) -> ChainMap[str, bool | str]:
    "Config for a given url: playlist, crunchyroll, twitch.tv, or youtube (default)"
    return ChainMap(
      {"quiet": self.is_quiet},
      self.template["audio"] if self.is_audio else self.template["captions"] if self.is_captions else {},
      {"playlistreverse": yesno("Do we start numbering this list from the first item (often the oldest)?")}
      if take_input and self.is_playlist(url) else {},
      {"format": f"bv*[height<={self.maxres}]+ba/b[height<={self.maxres}]"} if self.maxres else {},
      self.template["playlist"] if self.is_playlist(url) else self.template["show"] if self.is_show(url) else
      self.template["crunchyroll"] if self.is_crunchyroll(url) else self.template["twitch"] if self.is_twitch(url) else
      self.template["podcast"] if self.is_podcast(url) else self.template["dated"] if self.is_dated else {},
      self.template["default"],
    )
  
  #########################
  # URL/Video Information #
  #########################
  
  def filter_info(self, info: dict) -> dict[str, dict[str, Any]]:
    "Cleans an infodict of useless fields"
    # TODO: remove useless info (fragments, etc.) so we have less mem. footprint
    return info
  
  def url_info(self, url: str) -> dict[str, dict[str, Any]]:
    "Get the infodict for a URL"
    if url in self.info_cache and not ("is_live" in self.info_cache[url] and self.info_cache[url]["is_live"]):
      return self.info_cache[url]
    
    with YoutubeDL({"simulate": True, "quiet": True, "no_warnings": True, "consoletitle": True}) as ydl:
      info = ydl.extract_info(url, download = False)
    info = self.filter_info(info)
    self.info_cache[url] = info
    return info
  
  def is_supported(self, url: str) -> bool:
    try:
      self.url_info(url)
    except:
      if not self.is_quiet:
        print(url, "is not supported")
      return False
    finally:
      return True
  
  def is_show(self, url: str) -> bool:
    "Is a URL for a show? If so, it'll have a different folder structure."
    # info = self.url_info(url)
    return self.is_crunchyroll(url)
  
  def is_playlist(self, url: str) -> bool:
    "Is a URL actually a playlist? If so, it'll be downloaded differently."
    info = self.url_info(url)
    return ("playlist" in url or "youtube.com/c/" in url) or (
      info.get("playlist") is not None or info.get("playlist_title") is not None or info.get("playlist_id") is not None
    )
  
  def is_live(self, url: str) -> bool:
    "Is a video currently live? If so, we may need to wait until it's not."
    try:
      info = self.url_info(url)
      if "is_live" in info:
        return info["is_live"]
    except:
      pass
    return False
  
  def is_podcast(self, url: str) -> bool:
    "Is a URL a podcast?"
    return "podcast" in url
  
  def is_twitch(self, url: str) -> bool:
    "Is a URL for twitch.tv?"
    return "twitch.tv" in url
  
  def is_crunchyroll(self, url: str) -> bool:
    "Is a URL for Crunchyroll?"
    return "crunchyroll" in url
  
  #######
  # I/O #
  #######
  
  def ensure_dir(self, url: str | Path):
    "Ensure we can place a URL's resultant file in its expected directory, recursively (ignoring templates)."
    for parent in [
      parent for parent in Path(self.config(url, take_input = False)["outtmpl"]["default"]).expanduser().parents
      if not parent.exists() and "%(" not in parent.name and ")s" not in parent.name
    ][::-1]:
      parent.mkdir()
  
  def readfile(self, path: str | Path) -> list[str]:
    "Reads lines from a file"
    if (f := Path(path).expanduser()).is_file():
      return list(filter(None, map(str.strip, f.read_text(encoding = "utf8").splitlines())))
    return []
  
  def writefile(self, path: str | Path, lines: list):
    "Writes lines to a file"
    f = Path(path).expanduser()
    f.write_text("\n".join(filter(None, lines)), encoding = "utf8", newline = "\n")
  
  def update_history(self):
    "Update the history file"
    self.history |= set(self.readfile(self.history_file))
    self.writefile(self.history_file, sorted(self.history))
  
  def fixerupper(self, url: str):
    if "piped.kavin.rocks/" in url:
      url = url.replace("piped.kavin.rocks/", "youtube.com/")
    if "imgur.artemislena.eu/" in url:
      if "imgur.artemislena.eu/gallery/" in url:
        url = url.replace("imgur.artemislena.eu/gallery/", "imgur.com/gallery/")
      else:
        url = url.replace("imgur.artemislena.eu/", "i.imgur.com/")
    return url
  
  def download(self, url: str):
    "Actually download something"
    url = self.fixerupper(url)
    with YoutubeDL(self.config(url)) as ydl:
      self.ensure_dir(url)
      try:
        r = ydl.download(url)
      except KeyboardInterrupt as err:
        raise err
      except Exception as err:
        print(err)
        r = 1
    if r:
      if not self.is_idle and yesno(f"Did {url} download properly?"): self.history.add(url)
    else:
      self.history.add(url)
  
  #################
  # User Settings #
  #################
  
  def do_mode(self, arg = ""):
    "Prints details about the mode of operation and system."
    yesify = lambda b: "Yes" if b else "No"
    print("Mode:", "Idle" if self.is_idle else "Interactive")
    print("ASCII:", yesify(self.is_ascii))
    print("Quiet:", yesify(self.is_quiet))
    print("Audio:", yesify(self.is_audio))
    print("Captions:", yesify(self.is_captions))
    print("Dated:", yesify(self.is_dated))
    print("Sleep interval:", self.naptime, "seconds")
    print("Max resolution:", f"{self.maxres}p" if self.maxres else "Unlimited")
  
  def do_config(self, arg: str = ""):
    "Load a TOML configuration on a given path, default to config_file: config | config [path]"
    arg = Path(arg).expanduser()
    config = toml.load(arg if arg.is_file() else Path(self.config_file).expanduser())
    
    def __rec(old, new):
      for k, v in new.items():
        if isinstance(v, dict) and k in old:
          __rec(old[k], v)
        elif k in old:
          old[k] = v
    
    for key, val in config.items():
      if (key in self.__dict__ or key in PYTDL.__dict__) and (isinstance(val, type(self.__getattribute__(key)))):
        if isinstance(val, dict):
          __rec(self.__getattribute__(key), val)
        else:
          self.__setattr__(key, val)
    
    logging.config.dictConfig(self.log_config)
  
  def do_audio(self, arg = ""):
    "Toggle whether PYTDL treat urls as only audio by default"
    self.is_audio = not self.is_audio
    print("Audio!" if self.is_audio else "Not audio...")
  
  def do_captions(self, arg = ""):
    "Toggle whether PYTDL treat urls as only captions by default"
    self.is_captions = not self.is_captions
    print("Captions!" if self.is_captions else "Not captions...")
  
  def do_quiet(self, arg = ""):
    "Toggle whether PYTDL is quiet or not"
    self.is_quiet = not self.is_quiet
    print("Shh" if self.is_quiet else "BOO!")
  
  def do_dated(self, arg = ""):
    "Toggle whether PYTDL dates videos by default"
    self.is_dated = not self.is_dated
    print("Dating now" if self.is_dated else "Dateless...")
  
  def do_forced(self, arg = ""):
    "Toggle whether to force redownloads of videos"
    self.is_forced = not self.is_forced
    print("Force downloads" if self.is_forced else "Doesn't force downloads")
  
  def do_idle(self, arg = ""):
    "Idle mode keeps you from having to interact with the batch downloader, letting you go do something else."
    self.is_idle = not self.is_idle
    print("Idling" if self.is_idle else "Interactive")
  
  def do_naptime(self, arg: str):
    "How long do we sleep between downloads (on average)?"
    if arg.isdecimal(): self.naptime = int(arg)
    if self.naptime < 0: self.naptime = 0
    print(f"We sleep for {self.naptime}s on average.")
  
  def do_res(self, arg: str):
    "Provide a maximum resolution to download to, or nothing to remove the limit: res | res 1080"
    if arg.isdecimal():
      self.maxres = int(arg)
    else:
      self.maxres = 0
    print(f"We will go up to {self.maxres}p" if self.maxres else "We have no limits on resolution")
  
  #################
  # User Commands #
  #################
  
  def from_index(self, i: str) -> str | None:
    "Gets the i'th URL in the queue"
    queue = list(self.queue)
    if i.isdecimal() or (len(i) > 1 and i[0] == "-" and i[1:].isdecimal()):
      return queue[int(i)]
    return None
  
  def do_print(self, arg: str):
    "Print the queue, or certain URLs in it: print | print 0 | @ 0 | @ 1 2 5 | @ -1"
    print(f"There are {len(self.queue)} URLs in the queue")
    if len(self.queue):
      if len(arg):
        for url in arg.split():
          url = self.from_index(url)
          if url:
            print(url)
      else:
        for url in self.queue:
          print(url)
  
  def do_info(self, arg: str):
    "Print useful info for given URLs: info [url] [...] | info 0 5 -2 [url] [...]"
    for url in arg.split():
      try:
        if (u := self.from_index(url)):
          url = u
        info = self.url_info(url)
        print(f"URL: {url}")
        print(f"Title: {info['fulltitle']}")
        print("Twitch.tv" if self.is_twitch(url) else "Crunchyroll" if self.is_crunchyroll(url) else "Default")
        print("Playlist" if self.is_playlist(url) else "Livestream" if self.is_live(url) else "VOD")
      except KeyError as err:
        print(err)
      except Exception as err:
        print(info)
        print(err)
        raise err
  
  def do_infodump(self, urls: str):
    "Dumps all info of given URLs to JSON files in CWD: dump [url] [...]"
    for url in urls.split():
      info = self.url_info(url)
      Path(f"{info['id']}.json").write_text(json.dumps(info))
  
  def do_add(self, arg: str, /, check_supported = True):
    "Add a url to the list (space separated for multiple): add [url] | [url] | [url] [url] [url] | add front [url] [url] [url]"
    temp = None
    if len(arg):
      if len(q := arg.split(maxsplit = 1)) > 1:
        if q[0] == "front":
          arg = q[1]
          temp = dict(self.queue)
          self.queue = {}
      for url in arg.split():
        if len(url) > 4: # TODO: valid URL check, common typo fixes (https://a.bchttps://c.de, etc)
          if not check_supported or self.is_supported(url):
            self.queue[url] = url
    if temp: self.queue |= temp
    for url in self.queue:
      self.deleted.discard(url) # If we add it back, it should stay, unless we delete again, etc.
  
  def do_del(self, arg: str):
    "Delete a url from the queue and/or history: del [url] | - [url]"
    for url in arg.split():
      if len(url) and url in self.queue and yesno(f"Do you want to remove {url} from the queue?"):
        del self.queue[url]
        self.deleted.add(url)
        if url in self.info_cache: del self.info_cache[url]
      if len(url) and url in self.history and yesno(f"Do you want to remove {url} from the history?"):
        self.history -= {url}
        if url in self.info_cache: del self.info_cache[url]
  
  def do_drop(self, arg: str):
    "Drop the queue: drop | drop [queue file]"
    path = arg
    if len(path) == 0:
      path = self.queue_file
    self.queue = {k: v for k, v in self.queue.items() if k not in self.history}
    if len(self.queue): print(f"There are {len(self.queue)} urls in the queue that have not been downloaded.")
    if yesno(f"Do you want to remove all {len(self.queue)} urls from the queue?") and yesno("Are you sure about this?"):
      self.queue.clear()
    if yesno(f"Do you want to remove all {len(self.readfile(arg))} urls the queue file?"
             ) and yesno("Are you sure about this?"):
      self.writefile(self.queue_file, "")
    self.do_forget(self)
  
  def do_forget(self, arg: str = ""):
    "Forget all current known history: forget | forget [history file]"
    if len(arg) == 0:
      arg = self.history_file
    if yesno("Do you want to forget the history of dl'd videos?") and yesno("Are you sure about this?"):
      self.history.clear()
      self.info_cache.clear()
    if yesno("Do you want to forget the history file?") and yesno("Are you sure about this?"):
      self.writefile(arg, "")
  
  def do_get(self, arg: str | list[str]):
    "Get the video from given URLs: get [url] [...] | ! [url] [...]"
    still_live, urls = [], arg.split() if isinstance(arg, str) else arg
    if len(urls):
      set_title(f"downloading {len(urls)} video{'s'*(len(urls) != 1)}")
      print(f"Getting {len(urls)} video{'s'*(len(urls) != 1)}")
      try:
        for i, url in tqdm(enumerate(urls, 1), ascii = self.is_ascii, ncols = 100, unit = "vid"):
          if self.is_supported(url) and (
            url not in self.history or self.is_forced or (not self.is_idle and yesno(f"Try download {url} again?"))
          ) or "playlist" in url:
            set_title(f"[{i}/{len(urls)}] {url}")
            if self.is_live(url) and (self.is_idle or yesno(f"Currently live, shall we skip and try again later?")):
              still_live.append(url)
              continue
            self.download(url)
            sleep(randint(0, self.naptime * 2) + random())
      except KeyboardInterrupt:
        print()
        print("Stopped by user")
      except Exception as err:
        raise err
    else:
      print("No videos to download")
    self.update_history()
    if len(still_live): self.do_wait(" ".join(still_live))
  
  def do_getall(self, arg: str = ""):
    "Get the videos in the queue, including any from a given file: getall [file] | . [file]"
    set_title("organising queue")
    if len(arg) or len(self.queue) == 0:
      self.do_load(arg)
    self.do_get(self.queue)
  
  def do_load(self, arg: str = "", /, check_supported = True):
    "Load the contents of a file into the queue (add a - to not load the history): load [file] | load- [file] | : [file] | :- [file]"
    path, pre, get_history = arg, len(self.queue), True
    if path.startswith("-"):
      path, get_history = path.removeprefix("-"), False
    if len(path) == 0 or not Path(path).expanduser().is_file():
      path = self.queue_file
    for line in self.readfile(path):
      self.do_add(line, check_supported = check_supported)
    post = len(self.queue)
    if post > pre:
      print(f"Added {post-pre} URLs from {path}")
    if get_history: self.update_history()
    set_title(f"loaded {len(self.queue)} videos {f', {len(self.queue)-pre} new' if pre else ''}")
  
  def do_save(self, arg: str = ""):
    "Save the queue to a file (defaults to queue_file, add a - to not save the history): save [file] | save- [file] | # [file] | #- [file]"
    set_title("saving")
    path, queue, set_history = arg, dict(self.queue), True
    if path.startswith("-"):
      path, set_history = path.removeprefix("-"), False
    if len(path) == 0:
      path = self.queue_file
    if len(lines := self.readfile(path)):
      queue |= {line: line for line in lines}
    if len(queue):
      self.writefile(path, (url for url in queue if url not in self.history and url not in self.deleted))
    if set_history: self.update_history()
  
  def do_wait(self, arg: str = ""):
    "Wait on currently live videos, checking in slowing intervals from 10s to 10mins: wait | wait [url] [...]"
    urls, i = arg.split(), 0
    if len(arg) == 0 or len(urls) == 0: urls = list(self.queue)
    elapsed, intervals = 0, [10, 30, 60]
    wait_next = list(zip(intervals, intervals[1:] + [3600 * 24]))
    while len(urls):
      url = urls.pop(0)
      set_title(f"waiting on {url}")
      if self.is_live(url):
        wait, next_wait = wait_next[i]
        elapsed += wait
        if elapsed > next_wait * 2 and i < len(intervals) - 1: i += 1
        set_title(f"waiting on {url}, checking in {naturaltime(wait, future=True)}")
        try:
          sleep(wait + randint(0, wait // 3) + random()) # w/ jitter
        except KeyboardInterrupt:
          if not yesno("Test if the video is live now?") and not yesno("Do you want to continue waiting?"):
            break
        if self.is_live(url):
          urls.append(url)
      if not self.is_live(url):
        self.do_get(url)
        elapsed, i = 0, 0 # reset since we just spent a chunk of time downloading
  
  def do_merge(self, arg: str = ""):
    "Merge subtitles within a given directory, recursively. Defaults to searching '~/Videos/Shows/', otherwise provide an argument for the path."
    path = Path(arg).expanduser() if len(arg) else Path.home() / "Videos" / "Shows"
    merge_subs(path)
  
  def do_clean(self, arg: str = ""):
    "Cleans leading '0 ' and trailing ' - ' and '.' from videos, such as for single-season shows without titles on its episodes. Defaults to searching '~/Videos/Shows/', otherwise provide an argument for the folder: clean | clean [path-to-directory]"
    path = Path(arg).expanduser() if len(arg) else Path.home() / "Videos" / "Shows"
    vids = list(filter(Path.is_file, path.rglob("*")))
    for vid in vids:
      if vid.name.startswith("0 "):
        vid.rename(vid.with_stem(vid.stem.removeprefix("0 ").strip().removesuffix(".").removesuffix(" -")))
  
  def do_clear(self, arg = None):
    "Clear the screen"
    if platform.system() == "Windows":
      term("cls")
    else:
      term("clear")
  
  def do_exit(self, arg = ""):
    "Exit PYTDL"
    logging.debug("Exitting sequence started")
    self.do_save(arg)
    set_title(f"exitting")
    arg = Path(arg).expanduser()
    arg = arg if arg.is_file() else Path(self.queue_file).expanduser()
    logging.debug(f"Exitting, saved {len(self.readfile(arg))} videos to {arg}")
    print(f"Exitting, saved {len(self.readfile(arg))} videos to {arg}")
    sleep(2.0)
    logging.debug("Exit complete")
    return True
  
  ################
  # Cmd Handlers #
  ################
  
  def postcmd(self, stop, line):
    set_title(f"{len(self.queue)} queued videos" if len(self.queue) else "")
    return stop
  
  def preloop(self):
    set_title("starting up")
    self.do_config()
    self.do_config() # in case of redirection
    logging.debug(f"Config file loaded ({self.config_file})")
    self.do_load(check_supported = False)
    self.do_mode()
  
  #######################
  # Shorthand Operators #
  #######################
  
  def default(self, arg: str):
    op, arg = arg[0], arg[1:].strip()
    # TODO: come up with a general operator system? multi-char + multi-op + infix
    if op == ".":
      self.do_getall(arg)
    elif op == "!":
      self.do_get(arg)
    elif op == "-":
      self.do_del(arg)
    elif op == ":":
      self.do_load(arg)
    elif op == "#":
      self.do_save(arg)
    elif op == "*":
      self.update_history()
    elif op == "@":
      self.do_print(arg)
    else:
      self.do_add(f"{op}{arg}")

if __name__ == "__main__":
  os.chdir(Path.home()) # so we're always somewhere safe
  logging.Formatter.default_time_format = "%Y-%m-%d-%H-%M-%S" # so we 
  PYTDL().cmdloop()
