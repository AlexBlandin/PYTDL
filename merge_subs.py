#!/usr/bin/env python3
from subprocess import run
from pathlib import Path
from pprint import pprint

import langcodes # used to convert IETF BCP 47 (i.e., Crunchyroll) to ISO 639-2 (for ffmpeg)

nodot = lambda s: s.removeprefix(".")
def merge_subs(path = Path()):
  "A handy utility to merge .ass subtitles into .mp4 videos non-destructively (by switching to .mkv)"
  vids = list(filter(Path.is_file, path.rglob("*.mp4")))
  subs = list(filter(Path.is_file, path.rglob("*.ass")))
  pair = {vid: None for vid in vids}
  lang = {}
  for sub in subs:
    l = next(filter(langcodes.tag_is_valid, map(nodot, sub.suffixes)), None)
    if l:
      v = sub.with_stem(sub.stem.removesuffix("."+l)).with_suffix(".mp4")
      if v in pair:
        lang[sub] = langcodes.get(l).to_alpha3()
        pair[v] = sub
    else:
      print("We are missing a language code (i.e. en-US) on", sub)
  
  pair: dict[Path, Path] = {vid: sub for vid, sub in pair.items() if sub is not None}
  for vid, sub in pair.items():
    for _ in range(2): # how many tries
      if (
        r := run(
          f'ffmpeg -v "warning" -i "{vid}" -i "{sub}" -map 0 -c:v copy -c:a copy -map "-0:s" -map "-0:d" -c:s copy -map "1:0" "-metadata:s:s:0" "language={lang[sub]}" "{vid.with_suffix(".mkv")}" '
        )
      ).returncode:
        pprint(r)
      else:
        break
    else:
      continue # couldn't merge
    if vid.with_suffix(".mkv").is_file():
      try:
        vid.unlink()
        sub.unlink()
      except: # we fail to unlink if, say, someone is already watching it!
        pass

if __name__ == "__main__":
  merge_subs()
