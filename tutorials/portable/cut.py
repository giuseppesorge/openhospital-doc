#!/usr/bin/env python3
"""Shortens the waits of a recorded tutorial to a few seconds and burns the captions in, on a black band under
the screen so they never cover it.

Usage: cut.py raw.mp4 captions.vtt waits.txt out.mp4 out.vtt [pointer.txt]
waits.txt has one wait per line, "start end" in seconds, as written by the recorder. Of each wait the first
HEAD and the last TAIL seconds stay; the captions are moved to match. pointer.txt ("time x y" per line) draws
the mouse pointer, for recordings where the system hides it.
"""
import os
import re
import subprocess
import sys
import tempfile

HEAD, TAIL = 2.5, 1.5
# an arrow like the Windows one, about 12x19 pixels, white with a black border
ARROW = 'm 0 0 l 0 17 l 4 13 l 7 19 l 10 18 l 7 12 l 12 12'
BAND = 120  # pixels added under the screen for the captions
STYLE = "FontName=DejaVu Sans,FontSize=12,BorderStyle=1,Outline=0,Shadow=0,MarginV=5,MarginL=10,MarginR=10"


def seconds(s):
    h, m, rest = s.split(':')
    return int(h) * 3600 + int(m) * 60 + float(rest)


def stamp(t, sep):
    ms = round(t * 1000)
    return f'{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d}{sep}{ms % 1000:03d}'


def pointer_ass(track, end, moved, w, h):
    """The pointer as a drawing that stays at each recorded position until the next one."""
    head = (f'[Script Info]\nScriptType: v4.00+\nPlayResX: {w}\nPlayResY: {h}\n\n[V4+ Styles]\n'
            'Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BorderStyle, Outline, Shadow, Alignment\n'
            'Style: P,Arial,20,&H00FFFFFF,&H00000000,1,1.2,0,7\n\n[Events]\n'
            'Format: Layer, Start, End, Style, Text\n')
    ass = lambda t: f'{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}'
    lines = []
    for (t, x, y), nxt in zip(track, track[1:] + [(None, 0, 0)]):
        a, b = moved(t), moved(nxt[0]) if nxt[0] is not None else end
        if b - a >= 0.01:
            lines.append(f'Dialogue: 0,{ass(a)},{ass(b)},P,{{\\pos({x:.0f},{y:.0f})\\p1}}{ARROW}{{\\p0}}\n')
    return head + ''.join(lines)


def main():
    src, vtt, waits, out, out_vtt = sys.argv[1:6]
    track = sys.argv[6] if len(sys.argv) > 6 else None
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
        drawn = ''
        if track:
            w, h = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height',
                                   '-of', 'csv=p=0', src], capture_output=True, text=True, check=True).stdout.strip().split(',')
            ass = os.path.join(tmp, 'pointer.ass')
            with open(ass, 'w', encoding='utf-8') as f:
                f.write(pointer_ass([tuple(map(float, l.split())) for l in open(track, encoding='utf-8') if l.strip()],
                                    moved(duration), moved, int(w), int(h)))
            drawn = f'subtitles={ass},'
        parts = ''.join(f'[0:v]trim=start={a:.3f}:end={b:.3f},setpts=PTS-STARTPTS[p{i}];' for i, (a, b) in enumerate(keep))
        graph = (parts + ''.join(f'[p{i}]' for i in range(len(keep))) + f'concat=n={len(keep)}:v=1:a=0,' + drawn
                 + f'pad=iw:ih+{BAND}:0:0:black,' + f"subtitles={srt}:force_style='{STYLE}'[v]")
        subprocess.run(['ffmpeg', '-loglevel', 'error', '-i', src, '-filter_complex', graph, '-map', '[v]',
                        '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', '-y', out], check=True)
    print(f'{src}: {duration:.0f}s -> {moved(duration):.0f}s, {len(cuts)} waits shortened')


if __name__ == '__main__':
    main()
