#!/bin/bash
# Records the tutorial "Install and start the Linux portable package" on the X display $DISPLAY,
# which needs a window manager. The terminal is driven with xdotool, the captions are burnt in at the end.
# Usage: linux-portable.sh <version> <out dir>
# Needs: xterm, xdotool, wmctrl, ffmpeg (with libass), bc.
set -eu
ver=$1
out=$(realpath -m "$2")
size=${SIZE:-1600x1000}
id=linux-portable
pkg=OpenHospital-v$ver-linux_x86_64-portable
url=https://github.com/informatici/openhospital/releases/download/v$ver/$pkg.tar.gz
mkdir -p "$out"
work=$HOME/Downloads
mkdir -p "$work"
cd "$work"

titles() { wmctrl -l | cut -d' ' -f5-; }
waitwin() { # title regex, seconds
	for _ in $(seq "${2:-60}"); do
		titles | grep -qE "^($1)\$" && return 0
		sleep 1
	done
	echo "window '$1' not found, open: $(titles | tr '\n' '|')" >&2
	return 1
}
waitgone() { while pgrep -x "$1" >/dev/null; do sleep 0.5; done; }
now() { echo "$(date +%s.%N) - $t0" | bc; }
n=0
cap() { # closes the running caption and opens the next one, with a screenshot of the screen
	if [ -n "${cur:-}" ]; then echo "$cs|$(now)|$cur" >> "$out/cues"; fi
	cur=$1
	cs=$(now)
	n=$((n + 1))
	ffmpeg -loglevel error -f x11grab -video_size "$size" -i "$DISPLAY" -frames:v 1 -y "$out/$(printf 'step%02d' $n).png"
	sleep "${2:-1.5}"
}
typ() { xdotool type --delay 90 "$1"; sleep 0.4; }
key() { xdotool key "$@"; sleep 0.4; }

# on failure keep a picture of the screen and close the recording
trap 'cp "$work"/*/data/log/*.log "$out"/ 2>/dev/null; ffmpeg -loglevel error -f x11grab -video_size "$size" -i "$DISPLAY" -frames:v 1 -y "$out/failed.png"; kill -INT "${rec:-0}" 2>/dev/null' ERR

xterm -xrm 'XTerm*allowTitleOps: false' -fa 'DejaVu Sans Mono' -fs 13 -geometry 110x34+40+30 -title Terminal -e env PS1='$ ' bash --norc &
waitwin Terminal
xdotool search --name '^Terminal$' windowactivate --sync
sleep 1
rm -f "$out/cues"
ffmpeg -loglevel error -f x11grab -draw_mouse 0 -framerate 25 -video_size "$size" -i "$DISPLAY" \
	-c:v libx264 -preset veryfast -pix_fmt yuv420p -y "$out/raw.mp4" < /dev/null &
rec=$!
t0=$(date +%s.%N)
sleep 1

cap "Open Hospital on Linux: install and start the portable package." 3
cap "Download the package for Linux from the releases of Open Hospital on GitHub."
typ "wget -q --show-progress $url"
key Return
sleep 2
waitgone wget
sleep 1
cap "Unpack it and go into its folder."
typ "tar xzf $pkg.tar.gz"
key Return
sleep 1
waitgone tar
typ "cd $pkg && ls"
key Return
sleep 2
cap "Start Open Hospital."
typ "./oh.sh"
key Return
sleep 3
cap "The menu shows version, language and mode. Press Enter to start." 3
key Return
cap "The first start creates the database, then the application opens." 0
waitwin Login 300
sleep 2
cap "Log in. The first user is admin, with password admin."
typ admin
key Tab
typ admin
sleep 1
key Return
if waitwin 'Help us improve Open Hospital' 30; then
	sleep 1
	cap "Open Hospital asks whether it may send anonymous usage data. Choose one of the options." 4
	wmctrl -c 'Help us improve Open Hospital'
fi
waitwin OH 60
sleep 1
cap "Open Hospital is running. Next time just start ./oh.sh again." 5
cap ""
kill -INT "$rec"
wait "$rec" || true
titles > "$out/windows.txt"

# captions: vtt to publish, srt to burn in
awk -F'|' 'function t(s,  h,m){h=int(s/3600);m=int(s%3600/60);return sprintf("%02d:%02d:%06.3f",h,m,s-h*3600-m*60)}
	$3!=""{printf "%d\n%s --> %s\n%s\n\n", ++i, t($1), t($2), $3}' "$out/cues" > "$out/body"
{ printf 'WEBVTT\n\n'; cat "$out/body"; } > "$out/$id.en.vtt"
sed -E 's/([0-9]{2}:[0-9]{2}:[0-9]{2})\.([0-9]{3})/\1,\2/g' "$out/body" > "$out/$id.srt"
ffmpeg -loglevel error -i "$out/raw.mp4" \
	-vf "subtitles=$out/$id.srt:force_style='FontName=DejaVu Sans,FontSize=13,BorderStyle=4,BackColour=&H30000000,Outline=6,Shadow=0,MarginV=24'" \
	-c:v libx264 -pix_fmt yuv420p -movflags +faststart -y "$out/$id.mp4"
rm -f "$out/body"
echo "done $(wc -l < "$out/cues") captions in $out"
