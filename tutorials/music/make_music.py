#!/usr/bin/env python3
"""Background music for the tutorial videos, synthesized from scratch (no samples, no licence).

Usage: make_music.py <seconds> <out.wav> [calm|happy]
calm:  four slow chords (Cmaj7 Am7 Fmaj7 G6) with sparse soft bells.
happy: C G Am F at 104 bpm, plucked arpeggio in eighths, light bass and shaker.
Reverb, filter and fades are added by ffmpeg (add_music.sh).
"""
import math
import random
import struct
import sys
import wave

RATE = 44100
TWO_PI = 2 * math.pi

CALM_CHORDS = [  # MIDI notes
    [48, 55, 59, 64],  # Cmaj7
    [45, 52, 55, 60],  # Am7
    [41, 48, 52, 57],  # Fmaj7
    [43, 50, 52, 59],  # G6
]
HAPPY_CHORDS = [
    [48, 52, 55, 60],  # C
    [43, 50, 55, 59],  # G
    [45, 52, 57, 60],  # Am
    [41, 48, 53, 57],  # F
]


def hz(note):
    return 440.0 * 2 ** ((note - 69) / 12)


def pad(buf, chords, step, gain):
    """Each chord fades in and out with a raised cosine, overlapping the next one."""
    n = len(buf)
    length = step + 1.0
    t0 = -0.5
    k = 0
    while t0 < n / RATE:
        start = max(0, int(t0 * RATE))
        end = min(n, int((t0 + length) * RATE))
        for note in chords[k % len(chords)]:
            for detune in (-0.0015, 0.0015):  # two slightly detuned voices for warmth
                w = TWO_PI * hz(note) * (1 + detune) / RATE
                for i in range(start, end):
                    env = 0.5 - 0.5 * math.cos(TWO_PI * (i / RATE - t0) / length)
                    buf[i] += gain * env * math.sin(w * i)
        t0 += step
        k += 1


def pluck(buf, t, note, gain, decay, seconds, harmonic=0.15):
    n = len(buf)
    w = TWO_PI * hz(note) / RATE
    start = int(t * RATE)
    for j in range(min(int(seconds * RATE), n - start)):
        d = j / RATE
        env = min(1.0, d / 0.005) * math.exp(-d * decay)
        buf[start + j] += gain * env * (math.sin(w * j) + harmonic * math.sin(2 * w * j))


def calm(buf, seconds):
    step = 5.0
    pad(buf, CALM_CHORDS, step, 0.035)
    rng = random.Random(1582)
    t = 1.0
    while t < seconds - 2:
        if rng.random() < 0.7:
            chord = CALM_CHORDS[int((t + 0.5) // step) % len(CALM_CHORDS)]
            pluck(buf, t, rng.choice(chord) + 12, 0.05, 1.8, 2.5)
        t += 1.25


def happy(buf, seconds):
    beat = 60 / 104
    bar = 4 * beat
    pad(buf, HAPPY_CHORDS, bar, 0.018)
    pattern = [0, 1, 2, 3, 2, 1, 2, 3]  # chord-tone index per eighth note
    rng = random.Random(1582)
    t = 0.0
    k = 0
    while t < seconds:
        chord = HAPPY_CHORDS[k % len(HAPPY_CHORDS)]
        for e, idx in enumerate(pattern):
            te = t + e * beat / 2
            if te >= seconds:
                break
            pluck(buf, te, chord[idx] + 12, 0.045 if e % 2 == 0 else 0.032, 7.0, 0.6, 0.3)
            if e in (0, 4):  # bass on beats 1 and 3
                pluck(buf, te, chord[0] - 12, 0.11, 3.0, 1.0, 0.25)
            if e % 2 == 1:  # soft shaker on the off-beats
                start = int(te * RATE)
                prev = 0.0
                for j in range(min(int(0.06 * RATE), len(buf) - start)):
                    x = rng.uniform(-1, 1)
                    buf[start + j] += 0.012 * math.exp(-j / RATE * 60) * (x - prev)  # crude high-pass
                    prev = x
        t += bar
        k += 1


def main():
    seconds = float(sys.argv[1])
    out = sys.argv[2]
    style = sys.argv[3] if len(sys.argv) > 3 else 'calm'
    buf = [0.0] * int(seconds * RATE)
    {'calm': calm, 'happy': happy}[style](buf, seconds)
    peak = max(abs(v) for v in buf) or 1.0
    with wave.open(out, 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(RATE)
        wav.writeframes(b''.join(struct.pack('<h', int(v / peak * 0.8 * 32767)) for v in buf))


if __name__ == '__main__':
    main()
