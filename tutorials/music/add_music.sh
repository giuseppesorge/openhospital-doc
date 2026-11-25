#!/bin/sh
# Add the generated background music to a silent tutorial video.
# Usage: add_music.sh in.mp4 out.mp4 [calm|happy]
set -eu
in=$1
out=$2
style=${3:-calm}
here=$(cd "$(dirname "$0")" && pwd)
dur=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$in")
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
python3 -I "$here/make_music.py" "$dur" "$tmp/music.wav" "$style"
case $style in
  happy) tone="lowpass=f=5000,aecho=0.8:0.6:90:0.2" ;;
  *) tone="lowpass=f=2500,aecho=0.8:0.7:120|260:0.3|0.2" ;;
esac
fade_out=$(echo "$dur - 3" | bc)
ffmpeg -y -loglevel error -i "$in" -i "$tmp/music.wav" \
  -filter_complex "[1:a]$tone,afade=t=in:d=2,afade=t=out:st=$fade_out:d=3,loudnorm=I=-26:TP=-3,aformat=channel_layouts=stereo[a]" \
  -map 0:v -map "[a]" -c:v copy -c:a aac -b:a 128k -ar 44100 -shortest -movflags +faststart "$out"
