#!/usr/bin/env python3
import os
from pathlib import Path
from pprint import pprint
from subprocess import run

def merge_subs():
  "A handy utility to merge subtitles into a video"
  os.chdir(Path("C:\\Users\\alex\\Videos\\"))
  cwd = Path.cwd()
  vids, subs = [vid for vid in cwd.glob("./*.mp4")
                if vid.is_file()], [sub for sub in cwd.glob("./*.ass") if sub.is_file()]
  pair = {vid: sub for vid in vids for sub in subs if vid.stem == sub.stem[:-5]} # only supports `.mp4` w/ `.enUS.ass`
  for vid, sub in pair.items():
    for _ in range(2): # how many tries
      if (
        r := run(
          f'ffmpeg -v "warning" -i "{vid}" -i "{sub}" -map 0 -c copy -map "-0:s" -map "-0:d" "-c:s" copy -map "1:0" "-metadata:s:s:0" "language=eng" "{vid.stem}.mkv" '
        )
      ).returncode:
        pprint(r)
      else:
        break
    else:
      continue # couldn't merge
    if (out := cwd / f"{vid.stem}.mkv").is_file():
      vid.unlink()
      sub.unlink()

if __name__ == "__main__":
  merge_subs()
