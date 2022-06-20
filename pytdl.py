from random import random, randint
from humanize import naturaltime
from yt_dlp import YoutubeDL
from ctypes import windll
from pathlib import Path
from time import sleep
from os import system
from tqdm import tqdm
from cmd import Cmd
import platform

from merge_subs import merge_subs

def yesno(msg = "", accept_return = True, replace_lists = False, yes_list = set(), no_list = set()):
  "Keep asking until they say yes or no"
  while True:
    reply = input(f"{msg} [y/N]: ").strip().lower()
    if reply in (yes_list if replace_lists else {"y", "ye", "yes"} | yes_list) or (accept_return and reply == ""):
      return True
    if reply in (no_list if replace_lists else {"n", "no"} | no_list): return False

def cleanurls(urls: str):
  return list(map(str.strip, urls.strip().split()))

class PYTdl(Cmd):
  intro = "Download videos iteractively or from files. Type help or ? for a list of commands."
  prompt = "pyt-dl> "
  queue, got = {}, set(),
  forced, idle, ascii, quiet, dated = False, True, False, True, False # behaviour switches
  sleepy, start, maxres = 10, "", None
  local = Path(__file__).parent
  default_file, history_file = local / "queue.txt", local / "history.txt"
  cookies, secrets = local / "cookies", local / "secrets"
  set_title = windll.kernel32.SetConsoleTitleW
  conf = { # yt-dlp configurations
    "yt": {
      "outtmpl": {"default": str(Path.home() / "Videos" / "%(title)s [%(id)s].%(ext)s")}
    },
    "dated": {
      "outtmpl": {"default": str(Path.home() / "Videos" / "%(uploader)s" / "%(release_date>%Y-%m-%d,timestamp>%Y-%m-%d,upload_date>%Y-%m-%d|20xx-xx-xx)s %(title)s [%(id)s].%(ext)s")}
    },
    "tw": {
      "outtmpl": {"default": str(Path.home() / "Videos" / "Streams" / "%(uploader)s" / "%(timestamp>%Y-%m-%d-%H-%M-%S,upload_date>%Y-%m-%d-%H-%M-%S|Unknown)s %(title)s.%(ext)s")}
    },
    "list": {
      "outtmpl": {"default": str(Path.home() / "Videos" / "%(playlist_title)s" / "%(playlist_index)03d %(title)s.%(ext)s")}
    },
    "crunchy": {
      "subtitleslangs": ["enUS"],
      "writesubtitles": True,
      # "embed_subs": True,
      "cookiefile": cookies / "crunchy.txt",
      "outtmpl": {"default": str(Path.home() / "Videos" / "Shows" / "%(series)s" / "%(season_number|)s %(season|)s %(episode_number)02d - %(episode)s.%(ext)s")}
    },
    "default": {
      # "rm_cache_dir": True,
      "merge_output_format": "mkv",
      "overwrites": False,
      "fixup": "warn",
      "retries": 20,
      "fragment_retries": 20,
      # "windowsfilenames": True
    }
  }
  
  def config(self, url: str):
    "Config for a given url: playlist, crunchyroll, twitch.tv, or youtube (default)"
    return {
      **(
        self.conf["list"] if "playlist" in url else self.conf["crunchy"] if "crunchyroll" in url else self.conf["tw"] if "twitch.tv" in url else self.conf["dated"] if self.dated else self.conf["yt"]
      ),
      **self.conf["default"],
      **({
        "format": f"bv*[height<={self.maxres}]+ba/b[height<={self.maxres}]"
      } if self.maxres else {}), **({"playlistreverse": yesno("{self.start}Do we start numbering this list from the first item (or the last)?")} if "playlist" in url else {}), "quiet":
        self.quiet
    }
  
  def download(self, url: str):
    "Actually download something"
    with YoutubeDL(self.config(url)) as ydl:
      r = ydl.download(url)
    if r:
      if not self.idle and yesno(f"{self.start}Did {url} download properly?"): self.got.add(url)
    else:
      self.got.add(url)
  
  def info(self, url: str):
    "Get the infodict for a video"
    # TODO: is "forcejson" better than dump single json?
    with YoutubeDL({"dump_single_json": True, "simulate": True, "quiet": True}) as ydl:
      return ydl.extract_info(url, download = False)
  
  def live(self, url: str) -> bool:
    try:
      info = self.info(url)
      if "is_live" in info:
        return info["is_live"]
    except:
      pass
    return False
  
  def readfile(self, path: str = ""):
    if len(str(path)) == 0: path = self.default_file
    if (f := Path(path)).is_file():
      with open(f) as o:
        return list(filter(None, map(str.strip, o.readlines())))
    return []
  
  def update_got(self):
    self.got |= set(self.readfile(self.history_file))
    if Path(self.history_file).is_file():
      with open(self.history_file, mode = "w") as o:
        for url in list(self.got):
          o.write(f"{url}\n")
  
  def do_quiet(self, arg: str):
    "Toggle whether the downloader is quiet or not"
    self.quiet = not self.quiet
    print("Shh" if self.quiet else "BOO!")
  
  def do_dated(self, arg: str):
    "Toggle whether the downloader dates videos by default"
    self.dated = not self.dated
    print("Dated" if self.dated else "Undated")
  
  def do_sleepy(self, arg: str):
    "How long do we sleep for (on average)? There is a lower bound of 5s."
    self.sleepy = int(arg)
    if self.sleepy < 5: self.sleepy = 5
    print(f"We sleep for {self.sleepy}s on average.")
  
  def do_res(self, arg: str):
    "Provide a maximum resolution to download to, or nothing to remove the limit: res | res 1080C"
    if len(arg.strip()):
      self.maxres = int(arg)
    else:
      self.maxres = None
    print(f"We will go up to {self.maxres}p" if self.maxres else "We have no limits on resolution")
  
  def do_print(self, arg: str):
    "Print the queue, or certain urls in it: print | print 0 | @ 0 | @ 1 2 5 |  @ -1"
    queue, arg = list(self.queue), arg.strip()
    if yesno(f"There are {len(queue)} urls in the queue, do you want to print?") and len(queue):
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
      print(f'Title: {info["fulltitle"]}')
      print(f'URL: {url}')
      print("Live" if info["is_live"] else "VOD")
    except KeyError as err:
      print(err)
    except Exception as err:
      print(info)
      print(err)
      raise err
  
  def do_add(self, arg: str):
    "Add a url to the list (space separated for multiple): add [url] | [url] | [url] [url] [url] | add front [url] [url] [url]"
    temp = None
    if len(arg.strip()):
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
      if len(url) and url in self.queue and yesno(f"Do you want to remove {url} from the queue?"):
        del self.queue[url]
      if len(url) and url in self.got and yesno(f"Do you want to remove {url} from the history?"):
        self.got = self.got - {url}
  
  def do_drop(self, arg: str):
    "Drop the queue"
    l1 = len(self.queue)
    self.queue = {k: v for k, v in self.queue.items() if k not in self.got}
    l2 = len(self.queue)
    if l1 > l2: print(f"Removed {l1-l2} urls from the queue that have been downloaded.")
    if yesno(f"Do you want to remove all {l2} urls from the queue?") and yesno("Are you sure about this?"):
      self.queue = {}
    if yesno("Do you want to drop the history of dl'd videos?"):
      self.got = set()
  
  def do_forgetaboutem(self, arg):
    "Forget about which ones you've already gotten"
    self.got = set()
  
  def do_force(self, arg: str):
    "Force idle/get/wait the video at a url (space separated for multiple): get [url] | ! [url] | ![url] | ![url] [url] [url]"
    live = []
    for url in cleanurls(arg):
      if len(url):
        exp = self.expected(url)
        self.set_title(f"pYT dl: [{exp}] {url}")
        if self.live(url):
          live.append(url)
          continue
        with YoutubeDL(self.config(url)) as ydl:
          r = ydl.download(url) # 0 is fine, 1 is issue
        if r:
          if not self.idle and yesno(f"Did {url} download properly?"): self.got.add(url)
        else:
          self.got.add(url)
      if url == ".":
        self.do_getall()
    if len(live): self.do_wait(" ".join(live))
  
  def do_get(self, arg: str, looping: bool = False):
    "Get the video at a url (space separated for multiple, double !! for idle mode): get [url] | ! [url] | ![url] | ![url] [url] [url]"
    self.start = "\r" if looping else ""
    live = []
    for url in cleanurls(arg):
      if len(url) and (url not in self.got or
                       (not self.idle and yesno(f"{self.start}Try download {url} again?"))) or self.expected(url) in {
                         "list"
                       }:
        self.set_title(f"pYT dl: {url}")
        if self.live(url) and (self.idle or yesno(f"{self.start}Currently live, shall we skip and try again later?")):
          live.append(url)
          continue
        self.download(url)
      if url == ".":
        self.do_getall()
    self.update_got()
    return live
  
  def do_getall(self, arg: str = ""):
    "Get the videos in the queue, including any from a given file: getall [file] | . [file]"
    self.set_title(f"pYT dl: organising queue")
    arg, live = arg.strip(), []
    for url in list(self.queue):
      if url in self.got:
        del self.queue[url]
    if len(arg) or len(self.queue) == 0:
      self.do_load(arg)
    if len(self.queue):
      self.set_title(f"pYT dl: downloading {len(self.queue)} videos")
      print(f"Getting {len(self.queue)} video{'s'*(len(self.queue) != 1)}")
      try:
        for url in tqdm(self.queue, ascii = self.ascii, ncols = 100, unit = "vid"):
          sleep(randint(5, self.sleepy * 2) + random())
          live += self.do_get(url, True)
      except KeyboardInterrupt:
        print()
        print("Stopped by user")
      except Exception as err:
        raise err
    else:
      print("No videos in the queue")
    if len(live): self.do_wait(" ".join(live))
  
  def do_load(self, arg: str = ""):
    "Load the contents of a file into the queue (add a ! after to not load the history): load [file] | : [file] | :! [file]"
    path, pre, get_history = arg.strip(), len(self.queue), True
    if len(path) and path[0] == "!": path, get_history = path[1:].strip(), False
    if len(path) == 0: path = self.default_file
    for line in self.readfile(path):
      self.do_add(line)
    post = len(self.queue)
    if post > pre:
      print(f"Added {post-pre} URLs from {path}")
    if get_history:
      self.update_got()
    self.set_title(f"pYT dl: loaded {len(self.queue)} videos {f', {len(self.queue)-pre} new' if pre else ''}")
  
  def do_save(self, arg: str = ""):
    "Save the queue to a file (add a ! after to not save the history): save [file] | # [file] | #! [file]"
    self.set_title("pYT dl: saving")
    path, queue, get_history = arg.strip(), dict(self.queue), True
    if len(path) and path[0] == "!": path, get_history = Path(path[1:].strip()), False
    elif len(path) == 0: path = self.default_file
    else: path = Path(path)
    if len(lines := self.readfile(path)): queue |= {line: line for line in lines if line not in self.got}
    if len(queue):
      with open(path, mode = "w+") as o:
        o.write("".join(f"{url}\n" for url in queue if url not in self.got))
    if get_history: self.update_got()
  
  def do_wait(self, arg: str = ""):
    "Wait on a currently live video, checking in increasing intervals from 10s to 10mins (no argument waits on queue): wait [url] | wait [url] [url] [url] | wait"
    urls, i = cleanurls(arg), 0
    if len(arg) == 0 or len(urls) == 0: urls = list(self.queue)
    elp, waits = 0, [10, 30, 60]
    wn = list(zip(waits, waits[1:] + [3600 * 24]))
    while len(urls):
      url = urls.pop(0)
      self.set_title(f"pYT dl: waiting on {url}")
      live = lambda: self.live(url)
      if live():
        w, n = wn[i]
        elp += w
        if elp > n * 2 and i < len(waits) - 1: i += 1
        self.set_title(f"pYT dl: waiting on {url}, checking in {naturaltime(w, future=True)}")
        try:
          sleep(w + randint(0, w // 3) + random()) # w/ jitter
        except KeyboardInterrupt:
          if not yesno("Test if the video is live right now?") and not yesno("Do you want to continue waiting?"):
            break
        if live():
          urls.append(url)
      if not live():
        self.do_get(url)
        elp, i = 0, 0 # reset since we just spent a chunk of time downloading
  
  def do_merge(self, arg: str = ""):
    "Merge subtitles within a given directory, recursively. Defaults to searching './Videos/', otherwise provide an argument for the path."
    path = Path(arg.strip()) if len(arg.strip()) else Path("./Videos/")
    merge_subs(path)
  
  def do_clean(self, arg: str = ""):
    "Cleans leading '0 's from videos downloaded with [sub] that aren't in a numbered season. Defaults to searching './Videos/Shows/', otherwise provide an argument for the path."
    path = len(arg.strip) if len(arg.strip()) else Path("./Videos/Shows/")
    vids = list(filter(Path.is_file, path.rglob("*")))
    for vid in vids:
      if vid.name.startswith("0 "):
        vid.rename(vid.parent / vid.name.removeprefix("0 "))
  
  def do_idle(self, arg = None):
    "Idle mode keeps you from having to interact with the batch downloader, letting you go do something else."
    self.idle = not self.idle
    print("Idling" if self.idle else "Interactive")
  
  def do_IDLE(self, arg = None):
    self.do_idle()
  
  def do_clear(self, arg = None):
    if platform.system() == "Windows":
      system("cls")
    else:
      system("clear")
  
  def do_mode(self, arg = None):
    "Prints details about the mode of operation and system."
    print(f"Mode: {'Idle' if self.idle else 'Interactive'}")
    print(f"OS: {platform.system()}")
  
  def do_exit(self, arg: str = ""):
    "Exit pyt-dl"
    self.do_save(arg)
    self.set_title(f"pYT dl: exitting")
    print("Exitting")
    return True
  
  def postcmd(self, stop, line):
    self.set_title(
      f"pYT dl: {'idle mode' if self.idle else 'interactive'}{f', {len(self.queue)} queued videos' if len(self.queue) else ''}"
    )
    return stop
  
  def preloop(self):
    self.set_title("pYT dl: starting up")
    self.do_load()
    self.do_mode()
  
  def default(self, arg: str):
    arg = arg.strip()
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
      self.update_got()
    elif op == "@":
      self.do_print(arg)
    else:
      self.do_add(f"{op}{arg}")

if __name__ == "__main__":
  PYTdl().cmdloop()
