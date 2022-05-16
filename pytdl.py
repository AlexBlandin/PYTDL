from humanize import naturalsize, naturaltime
from requests import get as request
from json import loads as load_json
from random import random, randint
from bs4 import BeautifulSoup
from subprocess import run
from ctypes import windll
from pprint import pprint
from pathlib import Path
from time import sleep
from os import system
from tqdm import tqdm
from sys import argv
from cmd import Cmd
import platform

from merge_subs import merge_subs

SHOULD_ASCII = False
set_title = windll.kernel32.SetConsoleTitleW

def argn(n: int):
  return argv[argv.index(n) + 1]

def yesno(msg = "", accept_return = True, replace_lists = False, yes_list = set(), no_list = set()):
  "Keep asking until they say yes or no"
  while True:
    reply = input(f"{msg} [y/N]: ").strip().lower()
    if reply in (yes_list if replace_lists else {"y", "ye", "yes"} | yes_list) or (accept_return and reply == ""):
      return True
    if reply in (no_list if replace_lists else {"n", "no"} | no_list): return False

def cleanurl(url: str):
  "Just performs cleaning/fixing as is useful for ytdl/recording."
  url = url.strip()
  us = url.split("://")
  promotable = ["twitch.tv", "youtube.com", "youtu.be", "crunchyroll.com"]
  promote = any([domain in url for domain in promotable])
  protocol = "https" if promote or "s" in us[0] else "http"
  url = f"{protocol}://{us[-1]}"
  if url.startswith("https://youtu.be/"):
    url = f"https://youtube.com/watch?v={url.removeprefix('https://youtu.be/')}"
  return url

def cleanurls(urls: str):
  return list(map(cleanurl, urls.strip().split()))

# Like str.join but works on normal iterables, just can't use the "".join(x for x in it) grammar trick if you want to change the sep
def join(it, sep: str = " "):
  return sep.join(map(str, it))

def plural(arr) -> str:
  return "s" if len(arr) != 1 else ""

class PYTdl(Cmd):
  intro = "Download videos iteractively or from files. Type help or ? for a list of commands."
  prompt = "pyt-dl> "
  queue, got, interpret, forced, idle, quiet = {}, set(), None, False, True, False
  default_file, history_file = "pyt_queue.txt", "pyt_history.txt"
  formats = set(["yt", "tw", "sub"])
  redirect = {"yt": "yt.bat", "tw": "tw.bat", "sub": "sub.bat"}
  sleepy = 10
  
  def expected(self, url: str):
    url = cleanurl(url)
    # TODO: use a mapping or dictionary setup to self.formats
    if self.interpret is not None:
      return self.interpret
    if "crunchyroll" in url:
      return "sub"
    elif "twitch.tv" in url:
      return "tw"
    else:
      return "yt"
  
  def live(self, url: str) -> bool:
    try:
      url = cleanurl(url)
      exp = self.expected(url)
      if exp in ["tw", "yt"]: # this is atrocious, too bad!
        r = run([f"{self.redirect[exp]}", url, "-j"], capture_output = True).stdout.decode("utf-8")
        if len(r):
          j = load_json(r)
          if "is_live" in j:
            return j["is_live"]
    except:
      pass
    return False
  
  def readfile(self, path: str = ""):
    if len(path) == 0: path = self.default_file
    if (f := Path(path)).is_file():
      with open(f) as o:
        return list(map(cleanurl, filter(None, map(str.strip, o.readlines()))))
    return []
  
  def update_got(self):
    self.got |= set(self.readfile(self.history_file))
    with open(self.history_file, mode = "w") as o:
      for url in list(self.got):
        o.write(f"{url}\n")
  
  def do_quiet(self, arg: str):
    "Toggle whether the downloader is quiet or not"
    self.quiet = not self.quiet
    print("Shh" if self.quiet else "BOO!")
  
  def do_sleepy(self, arg: str):
    "How long do we sleep for (on average)? There is a lower bound of 5s."
    self.sleepy = int(arg)
    if self.sleepy < 5: self.sleepy = 5
    print(f"We sleep for {self.sleepy}s on average.")
  
  def do_print(self, arg: str):
    "Print the queue, or certain urls in it: print | print 0 | @ 0 | @ 1 2 5 |  @ -1"
    queue, arg = list(self.queue), arg.strip()
    if yesno(f"There are {len(queue)} urls in the queue, do you want to print?") and len(queue):
      if len(arg):
        args = cleanurls(arg)
        for arg in args:
          if arg.isdecimal() or (len(arg) > 1 and arg[0] == "-" and arg[1:].isdecimal()):
            url = queue[int(arg)]
            print(f"[{self.expected(url)}] {url}")
      else:
        for url in queue:
          print(f"[{self.expected(url)}] {url}")
  
  def do_info(self, url: str):
    "Print info about a video: info [url]"
    url = cleanurl(url)
    exp = self.expected(url)
    r = run([f"{self.redirect[exp]}", url, "-j"], capture_output = True).stdout.decode("utf-8")
    if len(r):
      j = ""
      try:
        j = load_json(r)
        print(f'Title: {j["fulltitle"]}')
        print(f'URL: {url}')
        print(f'Live? {"yes" if j["is_live"] else "no"}')
        # print(f': {j[""]}')
      except KeyError as err:
        print(err)
      except Exception as err:
        print(err)
        print(f"{r = }")
        print(f"{j = }")
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
  
  def do_as(self, arg: str):
    "Interpret as a given download scheme: yt | tw | sub"
    if len(exp := arg.strip()) and exp in self.formats:
      self.interpret = exp
      print(f"Using {exp} for now")
    else:
      self.interpret = None
      print("Automatically detecting download scheme")
  
  def do_force(self, arg: str):
    "Force idle/get/wait the video at a url (space separated for multiple): get [url] | ! [url] | ![url] | ![url] [url] [url]"
    live = []
    for url in cleanurls(arg):
      if len(url):
        exp = self.expected(url)
        set_title(f"pYT dl: [{exp}] {url}")
        if self.live(url):
          live.append(url)
          continue
        if (r := run([f"{self.redirect[exp]}", url] + (["-q"] * self.quiet))).returncode:
          print()
          pprint(r)
          if not self.idle and yesno(f"Did {url} download properly?"): self.got.add(url)
        else:
          self.got.add(url)
      if url == ".":
        self.do_getall()
    if len(live): self.do_wait(" ".join(live))
  
  def do_get(self, arg: str, looping: bool = False):
    "Get the video at a url (space separated for multiple, double !! for idle mode): get [url] | ! [url] | ![url] | ![url] [url] [url]"
    start = "\r" if looping else ""
    live = []
    for url in cleanurls(arg):
      if len(url) and (url not in self.got or (not self.idle and yesno(f"{start}Try download {url} again?"))):
        exp = self.expected(url)
        set_title(f"pYT dl: [{exp}] {url}")
        if self.live(url) and (self.idle or yesno(f"{start}Currently live, shall we skip and try again later?")):
          live.append(url)
          continue
        if (r := run([f"{self.redirect[exp]}", url] + (["-q"] * self.quiet))).returncode:
          print()
          pprint(r)
          if not self.idle and yesno(f"{start}Did {url} download properly?"): self.got.add(url)
        else:
          self.got.add(url)
      if url == ".":
        self.do_getall()
    self.update_got()
    return live
  
  def do_getall(self, arg = ""):
    "Get the videos in the queue, including any from a given file: getall [file] | . [file]"
    set_title(f"pYT dl: organising queue")
    arg, live = arg.strip(), []
    for url in list(self.queue):
      if url in self.got:
        del self.queue[url]
    if len(arg) or len(self.queue) == 0:
      self.do_load(arg)
    if len(self.queue):
      set_title(f"pYT dl: downloading {len(self.queue)} videos")
      print(f"Getting {len(self.queue)} video{plural(self.queue)}")
      try:
        for url in tqdm(self.queue, ascii = SHOULD_ASCII, ncols = 100, unit = "vid"):
          sleep(randint(5, self.sleepy*2) + random())
          live += self.do_get(url, True)
      except KeyboardInterrupt:
        print()
        print("Stopped by user")
      except Exception as err:
        raise err
    else:
      print("No videos in the queue")
    if len(live): self.do_wait(" ".join(live))
  
  def do_load(self, arg = ""):
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
    set_title(f"pYT dl: loaded {len(self.queue)} videos {f', {len(self.queue)-pre} new' if pre else ''}")
  
  def do_save(self, arg = ""):
    "Save the queue to a file (add a ! after to not save the history): save [file] | # [file] | #! [file]"
    set_title("pYT dl: saving")
    path, queue, get_history = arg.strip(), dict(self.queue), True
    if len(path) and path[0] == "!": path, get_history = path[1:].strip(), False
    if len(path) == 0: path = self.default_file
    if len(lines := self.readfile(path)): queue |= {line: line for line in lines if line not in self.got}
    if len(queue):
      with open(path, mode = "w") as o:
        o.write("".join(f"{url}\n" for url in queue if url not in self.got))
    if get_history: self.update_got()
  
  def do_wait(self, arg = ""):
    "Wait on a currently live video, checking in increasing intervals from 10s to 10mins (no argument waits on queue): wait [url] | wait [url] [url] [url] | wait"
    urls, i = cleanurls(arg), 0
    if len(arg) == 0 or len(urls) == 0: urls = list(self.queue)
    elp, waits = 0, [10, 30, 60]
    wn = list(zip(waits, waits[1:] + [3600 * 24]))
    while len(urls):
      url = urls.pop(0)
      set_title(f"pYT dl: waiting on {url}")
      live = lambda: self.live(url)
      if live():
        w, n = wn[i]
        elp += w
        if elp > n * 2 and i < len(waits) - 1: i += 1
        set_title(f"pYT dl: waiting on {url}, checking in {naturaltime(w, future=True)}")
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
  
  def do_merge(self, arg = ""):
    "Merge subtitles within a given directory, recursively. Defaults to searching './Videos/', otherwise provide an argument for the path."
    path = Path(arg.strip()) if len(arg.strip()) else Path("./Videos/")
    merge_subs(path)
  
  def do_cleading(self, arg = ""):
    "Cleans leading '0 's from videos downloaded with [sub] that aren't in a numbered season. Defaults to searching './Videos/Shows/', otherwise provide an argument for the path."
    path = len(arg.strip) if len(arg.strip()) else Path("./Videos/Shows/")
    vids = list(filter(Path.is_file, path.rglob("*.mkv")))
    for vid in vids:
      if vid.name.startswith("0 "):
        vid.rename(vid.parent / vid.name.removeprefix("0 "))
  
  def do_idle(self, arg = None):
    "Idle mode keeps you from having to interact with the batch downloader, letting you go do something else."
    self.idle = not self.idle
    print("Idling" if self.idle else "Interactive")
  
  def do_IDLE(self, arg = None):
    self.do_idle(arg)
  
  def do_clear(self, arg = None):
    if platform.system() == "Windows":
      system("cls")
    else:
      system("clear")
  
  def do_mode(self, arg = None):
    "Prints details about the mode of operation and system."
    print(f"Mode: {'Idle' if self.idle else 'Interactive'}")
    print(f"OS: {platform.system()}")
    print(f"Queue: {self.default_file}")
    print(f"History: {self.history_file}")
    print(f"Download Formats: {', '.join(self.formats)}")
  
  def do_exit(self, arg = ""):
    "Exit pyt-dl"
    self.do_save(arg)
    set_title(f"pYT dl: exitting")
    print("Exitting")
    return True
  
  def postcmd(self, stop, line):
    set_title(
      f"pYT dl: {'idle mode' if self.idle else 'interactive'}{f', {len(self.queue)} queued videos' if len(self.queue) else ''}"
    )
    return stop
  
  def preloop(self):
    set_title("pYT dl: starting up")
    self.do_load(argn("-l") if "-l" in argv else (argn("-ld") if "-ld" in argv else ""))
    self.default_file = argn("-d") if "-d" in argv else (argn("-ld") if "-ld" in argv else self.default_file)
    self.history_file = argn("-h") if "-h" in argv else self.history_file
    self.idle = "-i" not in argv or "--interactive" not in argv
    self.do_mode()
  
  def default(self, arg: str):
    arg = arg.strip()
    op, arg = arg[0], arg[1:]
    if op == ".": # TODO: do a better job than this, come up with a general operator system (multi-char + multi-op + infix)
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
  set_title = windll.kernel32.SetConsoleTitleW
  PYTdl().cmdloop()
