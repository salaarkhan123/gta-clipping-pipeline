#!/bin/bash
# Audio for the transcription benchmark (scripts/transcribe_bench.py), made from the owner's eval footage.
#
# Usage: scripts/prep_bench_audio.sh [footage dir] [out dir]
#   default: ~/ClutchClips-eval  ->  ~/ClutchClips-eval/bench-audio
#
# Writes, all 16 kHz mono FLAC (what Groq recommends; Deepgram and AssemblyAI take it as is):
#   masters/<video>.flac          the first audio track of each video, whole
#   bench-30-valorant.flac        valorant, 0:00-30:00
#   bench-60-gta5.flac            gta5, 0:00-60:00
#   bench-120-mixed.flac          gta5 + gta-online + forza joined in that order, cut at 120:00
#   bench-120-mixed.txt           where each video starts and ends in the 120-minute file
#   SHA256SUMS                    checksums of everything above (check with `sha256sum -c SHA256SUMS`)
# Audio never goes into git.
set -euo pipefail
SRC="${1:-$HOME/ClutchClips-eval}"
OUT="${2:-$SRC/bench-audio}"
FF=(ffmpeg -nostdin -hide_banner -loglevel error -y -protocol_whitelist file,pipe)
mkdir -p "$OUT/masters"

for v in forza gta6 valorant fortnite gta5 gta-online; do
  [ -f "$OUT/masters/$v.flac" ] || "${FF[@]}" -i "$SRC/$v.mp4" -map 0:a:0 -vn -ac 1 -ar 16000 -c:a flac "$OUT/masters/$v.flac"
done

"${FF[@]}" -i "$OUT/masters/valorant.flac" -t 1800 -c:a flac "$OUT/bench-30-valorant.flac"
"${FF[@]}" -i "$OUT/masters/gta5.flac" -t 3600 -c:a flac "$OUT/bench-60-gta5.flac"

list="$OUT/.concat.txt"
: > "$list"
: > "$OUT/bench-120-mixed.txt"
at=0
for v in gta5 gta-online forza; do
  echo "file '$OUT/masters/$v.flac'" >> "$list"
  len=$(ffprobe -v error -protocol_whitelist file,pipe -show_entries format=duration -of csv=p=0 "$OUT/masters/$v.flac")
  end=$(echo "$at + $len" | bc)
  [ "$(echo "$end > 7200" | bc)" = 1 ] && end=7200
  printf '%s\t%.1f\t%.1f\n' "$v" "$at" "$end" >> "$OUT/bench-120-mixed.txt"
  at=$(echo "$at + $len" | bc)
done
"${FF[@]}" -f concat -safe 0 -i "$list" -t 7200 -c:a flac "$OUT/bench-120-mixed.flac"
rm -f "$list"

cd "$OUT"
shasum -a 256 masters/*.flac bench-*.flac bench-120-mixed.txt > SHA256SUMS
du -sh "$OUT"
