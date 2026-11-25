#!/usr/bin/env python3
"""Cut the still (black) screen at the start of a recorded tutorial, before the application appears.

Usage: tighten.py in.mp4 in.vtt out.mp4 out.vtt
The subtitles are shifted by the same amount.
"""
import re
import subprocess
import sys


def ts(s):
    h, m, rest = s.split(':')
    return int(h) * 3600 + int(m) * 60 + float(rest)


def fmt(t):
    return f'{int(t // 3600):02d}:{int(t % 3600 // 60):02d}:{t % 60:06.3f}'


def main():
    src, vtt, out, out_vtt = sys.argv[1:5]
    log = subprocess.run(['ffmpeg', '-i', src, '-vf', 'freezedetect=n=0.003:d=1', '-an', '-f', 'null', '-'],
                         capture_output=True, text=True).stderr
    m = re.search(r'freeze_start: ([\d.]+).*?freeze_end: ([\d.]+)', log, re.S)
    cut = float(m.group(2)) if m and float(m.group(1)) == 0 else 0.0
    first = re.search(r'(\d\d:\d\d:\d\d\.\d+) -->', open(vtt, encoding='utf-8').read())
    if first:
        cut = min(cut, ts(first.group(1)))  # never cut into the first caption

    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-ss', f'{cut:.3f}', '-i', src,
                    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', out], check=True)
    text = open(vtt, encoding='utf-8').read()
    text = re.sub(r'\d\d:\d\d:\d\d\.\d+', lambda t: fmt(max(0.0, ts(t.group(0)) - cut)), text)
    open(out_vtt, 'w', encoding='utf-8').write(text)
    print(f'{src}: cut {cut:.1f}s at the start')


if __name__ == '__main__':
    main()
