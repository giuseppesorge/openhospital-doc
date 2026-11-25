#!/usr/bin/env python3
"""Shortens the waits of a recorded tutorial to a few seconds and burns the captions in.

Usage: cut.py raw.mp4 captions.vtt waits.txt out.mp4 out.vtt
waits.txt has one wait per line, "start end" in seconds, as written by the recorder. Of each wait the first
HEAD and the last TAIL seconds stay; the captions are moved to match.
"""
import os
import re
import subprocess
import sys
import tempfile

HEAD, TAIL = 2.5, 1.5
STYLE = "FontName=DejaVu Sans,FontSize=15,BorderStyle=4,BackColour=&H30000000,Outline=6,Shadow=0,MarginV=40"


def seconds(s):
    h, m, rest = s.split(':')
    return int(h) * 3600 + int(m) * 60 + float(rest)


def stamp(t, sep):
    ms = round(t * 1000)
    return f'{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d}{sep}{ms % 1000:03d}'


def main():
    src, vtt, waits, out, out_vtt = sys.argv[1:6]
    duration = float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', src],
                                    capture_output=True, text=True, check=True).stdout)
    cuts = []
    for line in open(waits, encoding='utf-8'):
        if line.strip():
            a, b = map(float, line.split())
            if b - a > HEAD + TAIL + 1:
                cuts.append((a + HEAD, b - TAIL))

    def moved(t):
        """Time t of the recording in the shortened video."""
        return t - sum(min(t, b) - a for a, b in cuts if t > a)

    keep, start = [], 0.0
    for a, b in cuts:
        keep.append((start, a))
        start = b
    keep.append((start, duration))

    cues = re.findall(r'(\d\d:\d\d:\d\d\.\d+) --> (\d\d:\d\d:\d\d\.\d+)\n(.*?)\n\n', open(vtt, encoding='utf-8').read() + '\n\n', re.S)
    cues = [(moved(seconds(a)), moved(seconds(b)), text) for a, b, text in cues]
    body = lambda sep: ''.join(f'{i}\n{stamp(a, sep)} --> {stamp(b, sep)}\n{t}\n\n' for i, (a, b, t) in enumerate(cues, 1))
    with open(out_vtt, 'w', encoding='utf-8') as f:
        f.write('WEBVTT\n\n' + body('.'))

    with tempfile.TemporaryDirectory() as tmp:
        srt = os.path.join(tmp, 'captions.srt')
        with open(srt, 'w', encoding='utf-8') as f:
            f.write(body(','))
        parts = ''.join(f'[0:v]trim=start={a:.3f}:end={b:.3f},setpts=PTS-STARTPTS[p{i}];' for i, (a, b) in enumerate(keep))
        graph = (parts + ''.join(f'[p{i}]' for i in range(len(keep))) + f'concat=n={len(keep)}:v=1:a=0,'
                 + f"subtitles={srt}:force_style='{STYLE}'[v]")
        subprocess.run(['ffmpeg', '-loglevel', 'error', '-i', src, '-filter_complex', graph, '-map', '[v]',
                        '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', '-y', out], check=True)
    print(f'{src}: {duration:.0f}s -> {moved(duration):.0f}s, {len(cuts)} waits shortened')


if __name__ == '__main__':
    main()
