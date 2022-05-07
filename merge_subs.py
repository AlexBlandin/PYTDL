#!/usr/bin/env python3
import os
from pathlib import Path
from pprint import pprint
from subprocess import run

def merge_subs():
  "A handy utility to merge enUS.ass subtitles into an mp4 video non-destructively (aka, switch to mkv)"
  vids, subs = list(filter(Path.is_file, Path().glob("*.mp4"))), list(filter(Path.is_file, Path().glob("*.ass")))
  pair = { # only supports .mp4 + .enUS.ass
    vid: sub
    for vid in vids for sub in subs if vid.stem == sub.stem.removesuffix(".enUS")
  }
  for vid, sub in pair.items():
    for _ in range(2): # how many tries
      if (
        r := run(
          f'ffmpeg -v "warning" -i "{vid}" -i "{sub}" -map 0 -c copy -map "-0:s" -map "-0:d" -c:s copy -map "1:0" "-metadata:s:s:0" "language=eng" "{vid.stem}.mkv" '
        )
      ).returncode:
        pprint(r)
      else:
        break
    else:
      continue # couldn't merge
    if Path(f"{vid.stem}.mkv").is_file():
      try: # we fail to unlink if, say, someone is already watching it!
        vid.unlink()
        sub.unlink()
      except:
        pass

if __name__ == "__main__":
  merge_subs()
