@REM Crunchyroll only!
@yt --sub-lang enUS --write-sub --embed-subs -o "~\Videos\Shows\%%(series)s\%%(season_number|)s %%(season|)s %%(episode_number)02d - %%(episode)s.%%(ext)s" --cookies "~\crunchycookies.txt" %*
