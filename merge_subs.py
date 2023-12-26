#!/usr/bin/env python3
from pathlib import Path
from pprint import pprint
from subprocess import run

import langcodes  # used to convert IETF BCP 47 (i.e., Crunchyroll's en-US) to ISO 639-2 (for ffmpeg)


def nodot(s):
  return s.removeprefix(".")


def merge_subs(path=Path()):
  "A handy utility to merge .ass subtitles into .mp4 videos non-destructively (by switching to .mkv)"
  vids = list(filter(Path.is_file, path.rglob("*.mp4")))
  subs = list(filter(Path.is_file, path.rglob("*.ass")))
  _pair: dict[Path, Path | None] = {vid: None for vid in vids}
  lang = {}
  for sub in subs:
    suffix = next(filter(langcodes.tag_is_valid, map(nodot, sub.suffixes)), None)
    if suffix:
      v = sub.with_stem(sub.stem.removesuffix(f".{suffix}")).with_suffix(".mp4")
      if v in _pair:
        lang[sub] = langcodes.get(suffix).to_alpha3()
        _pair[v] = sub
    else:
      print(f"We are missing a language code (i.e. en-US) on {sub}")

  pair: dict[Path, Path] = {vid: sub for vid, sub in _pair.items() if sub is not None}
  for vid, sub in pair.items():
    for _ in range(2):  # how many tries
      if (
        r := run(
          f'ffmpeg -v "warning" -i "{vid}" -i "{sub}" -map 0 -c:v copy -c:a copy -map "-0:s" -map "-0:d" -c:s copy -map "1:0" "-metadata:s:s:0" "language={lang[sub]}" "{vid.with_suffix(".mkv")}" ',  # noqa: E501
          check=False,
        )
      ).returncode:
        pprint(r)
      else:
        break
    else:
      continue  # couldn't merge
    if vid.with_suffix(".mkv").is_file():
      try:
        vid.unlink()
        sub.unlink()
      except Exception:  # we fail to unlink if, say, someone is already watching it!
        pass


if __name__ == "__main__":
  merge_subs()
