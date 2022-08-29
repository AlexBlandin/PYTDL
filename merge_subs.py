#!/usr/bin/env python3
from subprocess import run
from pathlib import Path
from pprint import pprint

def merge_subs(path = Path()):
  "A handy utility to merge enUS.ass subtitles into an mp4 video non-destructively (by switching to mkv)"
  vids = list(filter(Path.is_file, path.rglob("*.mp4")))
  subs = list(filter(lambda p: p.stem.endswith(".enUS"), filter(Path.is_file, path.rglob("*.ass"))))
  pair = {vid: None for vid in vids}
  for sub in subs:
    v = sub.parent / (sub.stem.removesuffix(".enUS") + ".mp4")
    if v in pair:
      pair[v] = sub
  pair = {vid: sub for vid, sub in pair.items() if sub is not None}
  for vid, sub in pair.items():
    for _ in range(2): # how many tries
      if (
        r := run(
          f'ffmpeg -v "warning" -i "{vid}" -i "{sub}" -map 0 -c:v copy -c:a copy -map "-0:s" -map "-0:d" -c:s copy -map "1:0" "-metadata:s:s:0" "language=eng" "{vid.stem}.mkv" '
        )
      ).returncode:
        pprint(r)
      else:
        break
    else:
      continue # couldn't merge
    if (vid.parent / f"{vid.stem}.mkv").is_file():
      try:
        vid.unlink()
        sub.unlink()
      except: # we fail to unlink if, say, someone is already watching it!
        pass

if __name__ == "__main__":
  merge_subs()
