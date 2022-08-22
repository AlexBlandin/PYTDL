from collections import ChainMap
from pathlib import Path
from random import randint, random
from time import sleep
from cmd import Cmd
from os import system as term
import platform

from humanize import naturaltime
from yt_dlp import YoutubeDL
from tqdm import tqdm
import rtoml

from merge_subs import merge_subs

def cleanurls(urls: str):
  return list(map(str.strip, urls.split()))

class PYTdl(Cmd):
  """
  pYT dl itself.
  
  Can be configured with config_file (uses TOML).
  """
  intro = "Download videos iteractively or from files. Type help or ? for a list of commands."
  prompt = "pyt-dl> "
  prefix = ""
  queue, history, deleted = {}, set(), set()
  local = Path(__file__).parent
  cookies, secrets = local / "cookies", local / "secrets"
  
  # Configuration settings
  is_forced: bool = False # Do we get videos despite the download history?
  is_idle: bool = True # Do we avoid prompting for user action?
  is_ascii: bool = False # Do we use ASCII only progress bars?
  is_quiet: bool = True # Do we try to avoid continuous printouts?
  is_dated: bool = False # Do we use a dated output by default? (Excludes site-specific downloads i.e. twitch.tv)
  
  naptime: int = 3 # average wait-time between downloads
  maxres: int = 0 # highest resolution for videos, if any (0 is uncapped)
  
  queue_file: str | Path = local / "queue.txt" # Where to save download queue
  history_file: str | Path = local / "history.txt" # Where to save download history
  config_file: str | Path = local / "config.toml" # Configuration file to load
  
  ytdlp = { # yt-dlp configurations
    "dated": {
      "outtmpl": {"default": str(Path.home() / "Videos" / "%(release_date>%Y-%m-%d,timestamp>%Y-%m-%d,upload_date>%Y-%m-%d|20xx-xx-xx)s %(title)s [%(id)s].%(ext)s")}
    },
    "twitch": {
      "fixup": "never",
      "outtmpl": {"default": str(Path.home() / "Videos" / "Streams" / "%(uploader)s" / "%(timestamp>%Y-%m-%d-%H-%M-%S,upload_date>%Y-%m-%d-%H-%M-%S|20xx-xx-xx)s %(title)s.%(ext)s")}
    },
    "playlist": {
      "outtmpl": {"default": str(Path.home() / "Videos" / "%(playlist_title)s" / "%(playlist_index)03d %(title)s.%(ext)s")}
    },
    "crunchyroll": {
      "subtitleslangs": ["enUS"],
      "writesubtitles": True,
      # "embed_subs": True,
      "cookiefile": cookies / "crunchy.txt",
      "outtmpl": {"default": str(Path.home() / "Videos" / "Shows" / "%(series)s" / "%(season_number|)s %(season|)s %(episode_number)02d - %(episode)s.%(ext)s")}
    },
    "default": {
      "outtmpl": {"default": str(Path.home() / "Videos" / "%(title)s [%(id)s].%(ext)s")},
      # "rm_cache_dir": True,
      "merge_output_format": "mkv",
      "overwrites": False,
      "fixup": "never", # "warn",
      "retries": 20,
      "fragment_retries": 20,
      # "add_metadata": True, # hopefully added in a future update
      # "embed_metadata": True, # hopefully added in a future update
      # "windowsfilenames": True
    }
  }
  
  def set_title(self, s: str):
    print(f"\33]0;{s}\a", end = "", flush = True)
  
  def yesno(self, msg = "", accept_return = True, replace_lists = False, yes_list = set(), no_list = set()):
    "Keep asking until they say yes or no"
    yes_list = yes_list if replace_lists else {"y", "ye", "yes"} | yes_list
    no_list = no_list if replace_lists else {"n", "no"} | no_list
    while True:
      reply = input(f"{self.prefix}{msg} [y/N]: ").strip().lower()
      if reply in yes_list or (accept_return and reply == ""):
        return True
      if reply in no_list: return False
  
  def config(self, url: str):
    "Config for a given url: playlist, crunchyroll, twitch.tv, or youtube (default)"
    return ChainMap(
      {"quiet": self.is_quiet},
      {"playlistreverse": self.yesno("Do we start numbering this list from the first item (or the last)?")}
      if "playlist" in url else {},
      {"format": f"bv*[height<={self.maxres}]+ba/b[height<={self.maxres}]"} if self.maxres else {},
      self.ytdlp["playlist"] if "playlist" in url else self.ytdlp["crunchyroll"] if "crunchyroll" in url else
      self.ytdlp["twitch"] if "twitch.tv" in url else self.ytdlp["dated"] if self.is_dated else {},
      self.ytdlp["default"],
    )
  
  def ensure_dir(self, url: str | Path):
    "Ensure we can place a URL's resultant file in its expected directory, recursively (ignoring templates)."
    for parent in [
      parent for parent in Path(self.config(url)["outtmpl"]["default"]).expanduser().parents
      if not parent.exists() and "%(" not in parent.name and ")s" not in parent.name
    ][::-1]:
      parent.mkdir()
  
  def download(self, url: str):
    "Actually download something"
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
      if not self.is_idle and self.yesno(f"Did {url} download properly?"): self.history.add(url)
    else:
      self.history.add(url)
  
  def info(self, url: str):
    "Get the infodict for a video"
    # TODO: is "forcejson" better than dump single json?
    with YoutubeDL({"dump_single_json": True, "simulate": True, "quiet": True}) as ydl:
      return ydl.extract_info(url, download = False)
  
  def is_live(self, url: str) -> bool:
    "Is the video currently live? If so, we may need to wait until it's not."
    try:
      info = self.info(url)
      if "is_live" in info:
        return info["is_live"]
    except:
      pass
    return False
  
  def readfile(self, path: str | Path):
    "Reads lines from a file"
    if (f := Path(path).expanduser()).is_file():
      return list(filter(None, map(str.strip, f.read_text(encoding = "utf8").splitlines())))
    return []
  
  def writefile(self, path: str | Path, lines: list):
    "Writes lines to a file"
    f = Path(path).expanduser()
    f.write_text("\n".join(filter(None, lines)), encoding = "utf8", newline = "\n")
  
  def do_config(self, arg: str = ""):
    "Load a TOML configuration on a given path, default to config_file: config | config [path]"
    arg = Path(arg).expanduser()
    config = rtoml.load(arg if arg.is_file() else Path(self.config_file).expanduser())
    
    def __rec(old, new):
      for k, v in new.items():
        if isinstance(v, dict) and k in old:
          __rec(old[k], v)
        elif k in old:
          old[k] = v
    
    for key, val in config.items():
      if (key in self.__dict__ or key in PYTdl.__dict__) and (isinstance(val, type(self.__getattribute__(key)))):
        if isinstance(val, dict):
          __rec(self.__getattribute__(key), val)
        else:
          self.__setattr__(key, val)
  
  def update_history(self):
    "Update the history file"
    self.history |= set(self.readfile(self.history_file))
    self.writefile(self.history_file, sorted(self.history))
  
  def do_quiet(self, arg):
    "Toggle whether the downloader is quiet or not"
    self.is_quiet = not self.is_quiet
    print("Shh" if self.is_quiet else "BOO!")
  
  def do_dated(self, arg):
    "Toggle whether the downloader dates videos by default"
    self.is_dated = not self.is_dated
    print("Dated" if self.is_dated else "Undated")
  
  def do_forced(self, arg):
    "Toggle whether to force redownloads of videos"
    self.is_forced = not self.is_forced
    print("Forces" if self.is_forced else "Skips")
  
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
  
  def do_print(self, arg: str):
    "Print the queue, or certain urls in it: print | print 0 | @ 0 | @ 1 2 5 |  @ -1"
    queue = list(self.queue)
    if self.yesno(f"There are {len(queue)} urls in the queue, do you want to print?") and len(queue):
      if len(arg):
        args = cleanurls(arg)
        for arg in args:
          if arg.isdecimal() or (len(arg) > 1 and arg[0] == "-" and arg[1:].isdecimal()):
            url = queue[int(arg)]
            print(url)
      else:
        for url in queue:
          print(url)
  
  def do_info(self, url: str):
    "Print info about a video: info [url]"
    info = self.info(url)
    try:
      print(f"Title: {info['fulltitle']}")
      print(f"URL: {url}")
      print(
        "Live" if info["is_live"] else "VOD"
      ) # TODO: better language and perhaps even detect if it's a VOD of a stream vs just a regular video
    except KeyError as err:
      print(err)
    except Exception as err:
      print(info)
      print(err)
      raise err
  
  def do_add(self, arg: str):
    "Add a url to the list (space separated for multiple): add [url] | [url] | [url] [url] [url] | add front [url] [url] [url]"
    temp = None
    if len(arg):
      if len(q := arg.split(maxsplit = 1)) > 1:
        if q[0] == "front":
          arg = q[1]
          temp = dict(self.queue)
          self.queue = {}
      self.queue |= {url: url for url in cleanurls(arg) if len(url) > 4}
    if temp: self.queue |= temp
  
  def do_del(self, arg: str):
    "Delete a url from the queue and/or history: del [url] | - [url]"
    for url in cleanurls(arg):
      if len(url) and url in self.queue and self.yesno(f"Do you want to remove {url} from the queue?"):
        del self.queue[url]
        self.deleted.add(url)
      if len(url) and url in self.history and self.yesno(f"Do you want to remove {url} from the history?"):
        self.history -= {url}
  
  def do_drop(self, arg: str):
    "Drop the queue"
    self.queue = {k: v for k, v in self.queue.items() if k not in self.history}
    if len(self.queue): print(f"There are {len(self.queue)} urls in the queue that have not been downloaded.")
    if self.yesno(f"Do you want to remove all {len(self.queue)} urls from the queue?"
                  ) and self.yesno("Are you sure about this?"):
      self.queue = {}
    self.do_forget(self)
  
  def do_forget(self, arg):
    "Forget all current known history"
    if self.yesno("Do you want to forget the history of dl'd videos?"):
      self.history.clear()
    if self.yesno("Do you want to forget the history file?"):
      self.writefile(self.history_file, "")
  
  def do_get(self, arg: str | list[str]):
    "Get the video at a url (space separated for multiple, double !! for idle mode): get [url] | ! [url] | ![url] | ![url] [url] [url]"
    still_live, urls = [], cleanurls(arg) if isinstance(arg, str) else arg
    self.prefix = "\r" if len(urls) > 1 else ""
    if len(urls):
      self.set_title(f"pYT dl: downloading {len(urls)} video{'s'*(len(urls) != 1)}")
      print(f"Getting {len(urls)} video{'s'*(len(urls) != 1)}")
      try:
        for i, url in tqdm(enumerate(urls, 1), ascii = self.is_ascii, ncols = 100, unit = "vid"):
          if len(url) and (
            url not in self.history or self.is_forced or
            (not self.is_idle and self.yesno(f"Try download {url} again?"))
          ) or "playlist" in url:
            self.set_title(f"pYT dl: [{i}/{len(urls)}] {url}")
            if self.is_live(url
                            ) and (self.is_idle or self.yesno(f"Currently live, shall we skip and try again later?")):
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
    self.set_title(f"pYT dl: organising queue")
    if len(arg) or len(self.queue) == 0:
      self.do_load(arg)
    self.do_get(self.queue)
  
  def do_load(self, arg: str = ""):
    "Load the contents of a file into the queue (add a - to not load the history): load [file] | load- [file] | : [file] | :- [file]"
    path, pre, get_history = arg, len(self.queue), True
    if path.startswith("-"):
      path, get_history = path.removeprefix("-"), False
    if len(path) == 0 or not Path(path).expanduser().is_file():
      path = self.queue_file
    for line in self.readfile(path):
      self.do_add(line)
    post = len(self.queue)
    if post > pre:
      print(f"Added {post-pre} URLs from {path}")
    if get_history: self.update_history()
    self.set_title(f"pYT dl: loaded {len(self.queue)} videos {f', {len(self.queue)-pre} new' if pre else ''}")
  
  def do_save(self, arg: str = ""):
    "Save the queue to a file (defaults to queue_file, add a - to not save the history): save [file] | save- [file] | # [file] | #- [file]"
    self.set_title("pYT dl: saving")
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
    "Wait on currently live videos, checking in slowing intervals from 10s to 10mins: wait [url] | wait [url] [url] [url] | wait"
    urls, i = cleanurls(arg), 0
    if len(arg) == 0 or len(urls) == 0: urls = list(self.queue)
    elapsed, intervals = 0, [10, 30, 60]
    wait_next = list(zip(intervals, intervals[1:] + [3600 * 24]))
    while len(urls):
      url = urls.pop(0)
      self.set_title(f"pYT dl: waiting on {url}")
      if self.is_live(url):
        wait, next_wait = wait_next[i]
        elapsed += wait
        if elapsed > next_wait * 2 and i < len(intervals) - 1: i += 1
        self.set_title(f"pYT dl: waiting on {url}, checking in {naturaltime(wait, future=True)}")
        try:
          sleep(wait + randint(0, wait // 3) + random()) # w/ jitter
        except KeyboardInterrupt:
          if not self.yesno("Test if the video is live now?") and not self.yesno("Do you want to continue waiting?"):
            break
        if self.is_live(url):
          urls.append(url)
      if not self.is_live(url):
        self.do_get(url)
        elapsed, i = 0, 0 # reset since we just spent a chunk of time downloading
  
  def do_merge(self, arg: str = ""):
    "Merge subtitles within a given directory, recursively. Defaults to searching '~/Videos/', otherwise provide an argument for the path."
    path = Path(arg).expanduser() if len(arg) else Path.home() / "Videos"
    merge_subs(path)
  
  def do_clean(self, arg: str = ""):
    "Cleans leading '0 's from videos downloaded with [sub] that aren't in a numbered season. Defaults to searching '~/Videos/Shows/', otherwise provide an argument for the path."
    path = Path(arg).expanduser() if len(arg) else Path.home() / "Videos" / "Shows"
    vids = list(filter(Path.is_file, path.rglob("*")))
    for vid in vids:
      if vid.name.startswith("0 "):
        vid.rename(vid.parent / vid.name.removeprefix("0 "))
  
  def do_idle(self, arg = None):
    "Idle mode keeps you from having to interact with the batch downloader, letting you go do something else."
    self.is_idle = not self.is_idle
    print("Idling" if self.is_idle else "Interactive")
  
  def do_clear(self, arg = None):
    "Clear the screen"
    if platform.system() == "Windows":
      term("cls")
    else:
      term("clear")
  
  def do_mode(self, arg = None):
    "Prints details about the mode of operation and system."
    yesify = lambda b: "Yes" if b else "No"
    print("Mode:", "Idle" if self.is_idle else "Interactive")
    print("ASCII:", yesify(self.is_ascii))
    print("Quiet:", yesify(self.is_quiet))
    print("Dated:", yesify(self.is_dated))
    print("Sleep interval:", self.naptime, "seconds")
    print("Max resolution:", f"{self.maxres}p" if self.maxres else "Unlimited")
  
  def do_exit(self, arg = ""):
    "Exit pYT dl"
    self.do_save(arg)
    self.set_title(f"pYT dl: exitting")
    arg = Path(arg).expanduser()
    arg = arg if arg.is_file() else Path(self.queue_file).expanduser()
    print(f"Exitting, saved {len(self.readfile(arg))} videos to {arg}")
    return True
  
  def postcmd(self, stop, line):
    self.set_title(
      f"pYT dl: {'idle mode' if self.is_idle else 'interactive'}{f', {len(self.queue)} queued videos' if len(self.queue) else ''}"
    )
    return stop
  
  def preloop(self):
    self.set_title("pYT dl: starting up")
    self.do_config()
    self.do_config() # in case of redirection
    self.do_load()
    self.do_mode()
  
  def default(self, arg: str):
    op, arg = arg[0], arg[1:].strip()
    # come up with a general operator system? multi-char + multi-op + infix
    if op == ".": # TODO: improve
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
  PYTdl().cmdloop()
