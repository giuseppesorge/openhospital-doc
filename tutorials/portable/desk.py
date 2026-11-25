#!/usr/bin/env python3
"""Records a desktop tutorial with real mouse and keyboard on the X display $DISPLAY.

Things on the screen are found by their text: in the browser through Playwright, everywhere else
by reading the screen with tesseract. The pointer then moves there with xdotool, so the video shows
what a person would do. Captions are written as WebVTT and burnt into the video at the end.

Usage: desk.py linux-portable <version> <out dir>
Needs: xdotool, wmctrl, ffmpeg (with libass), tesseract, Python playwright with Google Chrome.
"""
import csv
import io
import os
import re
import subprocess
import sys
import time

SIZE = os.environ.get('SIZE', '1280x800')
DISPLAY = os.environ['DISPLAY']


def run(*cmd, **kw):
    return subprocess.run(cmd, check=True, **kw)


class Desk:
    def __init__(self, out):
        self.out = out
        os.makedirs(out, exist_ok=True)
        self.cues = []
        self.cur = None
        self.n = 0
        self.rec = None

    # recording and captions

    def start(self):
        self.rec = subprocess.Popen(['ffmpeg', '-loglevel', 'error', '-f', 'x11grab', '-draw_mouse', '1', '-framerate', '25',
                                     '-video_size', SIZE, '-i', DISPLAY, '-c:v', 'libx264', '-preset', 'veryfast',
                                     '-pix_fmt', 'yuv420p', '-y', f'{self.out}/raw.mp4'], stdin=subprocess.PIPE)
        self.t0 = time.time()
        time.sleep(1)

    def caption(self, text, hold=1.5):
        now = time.time() - self.t0
        if self.cur:
            self.cues.append((self.cur[0], now, self.cur[1]))
        self.cur = (now, text) if text else None
        self.n += 1
        self.shot(f'{self.out}/step{self.n:02d}.png')
        time.sleep(hold)

    def stop(self, name):
        self.caption('', 0)
        assert self.rec
        self.rec.communicate(b'q', timeout=60)

        def ts(s, sep):
            return f'{int(s // 3600):02d}:{int(s % 3600 // 60):02d}:{int(s % 60):02d}{sep}{int(s * 1000) % 1000:03d}'

        body = lambda sep: ''.join(f'{i}\n{ts(a, sep)} --> {ts(b, sep)}\n{t}\n\n' for i, (a, b, t) in enumerate(self.cues, 1))
        with open(f'{self.out}/{name}.en.vtt', 'w') as f:
            f.write('WEBVTT\n\n' + body('.'))
        with open(f'{self.out}/{name}.srt', 'w') as f:
            f.write(body(','))
        style = "FontName=DejaVu Sans,FontSize=15,BorderStyle=4,BackColour=&H30000000,Outline=6,Shadow=0,MarginV=40"
        run('ffmpeg', '-loglevel', 'error', '-i', f'{self.out}/raw.mp4', '-vf', f"subtitles={self.out}/{name}.srt:force_style='{style}'",
            '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', '-y', f'{self.out}/{name}.mp4')

    def shot(self, path):
        run('ffmpeg', '-loglevel', 'error', '-f', 'x11grab', '-video_size', SIZE, '-i', DISPLAY, '-frames:v', '1', '-y', path)

    # finding things on the screen

    def find(self, text, timeout=20, region=None):
        """Centre of the first line on the screen that contains text (case-insensitive), or an error after timeout."""
        want = text.lower().split()
        end = time.time() + timeout
        while True:
            path = f'{self.out}/ocr.png'
            self.shot(path)
            scale = 2
            png = subprocess.run(['ffmpeg', '-loglevel', 'error', '-i', path, '-vf', f'scale=iw*{scale}:ih*{scale},format=gray',
                                  '-f', 'image2pipe', '-vcodec', 'png', '-'], capture_output=True, check=True).stdout
            tsv = subprocess.run(['tesseract', '-', '-', '--psm', '11', 'tsv'], input=png, capture_output=True).stdout.decode()
            words = [r for r in csv.DictReader(io.StringIO(tsv), delimiter='\t', quoting=csv.QUOTE_NONE)
                     if r.get('text', '').strip() and float(r['conf']) > 30]
            for i in range(len(words)):
                got = words[i:i + len(want)]
                if len(got) == len(want) and all(g['text'].lower().startswith(w) for g, w in zip(got, want)):
                    x1 = min(int(g['left']) for g in got)
                    y1 = min(int(g['top']) for g in got)
                    x2 = max(int(g['left']) + int(g['width']) for g in got)
                    y2 = max(int(g['top']) + int(g['height']) for g in got)
                    x, y = (x1 + x2) // 2 // scale, (y1 + y2) // 2 // scale
                    if region is None or (region[0] <= x <= region[2] and region[1] <= y <= region[3]):
                        return x, y
            if time.time() > end:
                os.replace(path, f'{self.out}/notfound.png')
                raise RuntimeError(f'text not found on screen: {text}')
            time.sleep(1)

    def window(self, title, timeout=60):
        end = time.time() + timeout
        while time.time() < end:
            out = subprocess.run(['wmctrl', '-l'], capture_output=True, text=True).stdout
            if any(re.fullmatch(title, line.split(None, 3)[3]) for line in out.splitlines() if len(line.split(None, 3)) == 4):
                return
            time.sleep(1)
        raise RuntimeError(f'window not found: {title}')

    # mouse and keyboard

    def move(self, x, y):
        out = subprocess.run(['xdotool', 'getmouselocation', '--shell'], capture_output=True, text=True).stdout
        pos = dict(line.split('=') for line in out.split())
        x0, y0 = int(pos['X']), int(pos['Y'])
        steps = 25
        for k in range(1, steps + 1):
            f = k / steps
            f = f * f * (3 - 2 * f)  # ease in and out
            run('xdotool', 'mousemove', str(round(x0 + (x - x0) * f)), str(round(y0 + (y - y0) * f)))
            time.sleep(0.02)
        time.sleep(0.3)

    def click(self, where, button=1, double=False):
        x, y = self.find(where) if isinstance(where, str) else where
        self.move(x, y)
        run('xdotool', 'click', *(['--repeat', '2', '--delay', '120'] if double else []), str(button))
        time.sleep(0.8)

    def type(self, text, delay=90):
        run('xdotool', 'type', '--delay', str(delay), text)
        time.sleep(0.4)

    def key(self, *keys):
        run('xdotool', 'key', *keys)
        time.sleep(0.5)


def linux_portable(d, ver):
    from playwright.sync_api import sync_playwright
    pkg = f'OpenHospital-v{ver}-linux_x86_64-portable'
    downloads = os.path.expanduser('~/Downloads')
    os.makedirs(downloads, exist_ok=True)

    d.window('Desktop', 60)
    time.sleep(2)
    d.start()
    d.caption('Open Hospital on Linux: download, install and start the portable package.', 3)

    with sync_playwright() as p:
        d.caption('Open the web browser and go to open-hospital.org.', 0.5)
        ctx = p.chromium.launch_persistent_context(os.path.expanduser('~/.tutorial-chrome'), channel='chrome', headless=False,
                                                   no_viewport=True, accept_downloads=True,
                                                   args=['--start-maximized', '--no-first-run', '--no-default-browser-check', '--test-type'])
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        time.sleep(3)
        d.key('ctrl+l')
        d.type('www.open-hospital.org')
        d.key('Return')
        page.wait_for_load_state('domcontentloaded')
        time.sleep(3)

        def at(locator):
            """Screen position of an element of the page."""
            box = locator.bounding_box()
            sx, sy, ow, oh, iw, ih = page.evaluate('[screenX, screenY, outerWidth, outerHeight, innerWidth, innerHeight]')
            return (round(sx + (ow - iw) / 2 + box['x'] + box['width'] / 2),
                    round(sy + oh - ih + box['y'] + box['height'] / 2))

        cookie = page.locator('.iubenda-cs-close-btn').first
        if cookie.count() and cookie.is_visible():
            d.click(at(cookie))
        d.caption('Click DOWNLOAD.')
        d.click(at(page.locator('header a[href*="/download"]:visible').first))
        page.wait_for_load_state('domcontentloaded')
        time.sleep(3)
        link = page.locator(f'a[href$="{pkg}.tar.gz"]').first
        d.caption('Under the latest release, choose the portable package for Linux, 64 bit.', 0.5)
        d.move(640, 500)
        for _ in range(60):  # scroll with the wheel until the link is well inside the window
            box = link.bounding_box()
            if box and 150 < box['y'] < page.evaluate('innerHeight') - 150:
                break
            run('xdotool', 'click', '5')
            time.sleep(0.25)
        time.sleep(1)
        got = []  # the link may open a new tab: listen to every page
        ctx.on('page', lambda pg: pg.on('download', got.append))
        for pg in ctx.pages:
            pg.on('download', got.append)
        d.click(at(link))
        for _ in range(600):
            if got:
                break
            time.sleep(1)
        if not got:
            raise RuntimeError('the download did not start')
        got[0].save_as(f'{downloads}/{pkg}.tar.gz')
        time.sleep(2)
        d.caption('The package is in the Downloads folder.', 1)
        ctx.close()

    d.caption('Open your home folder, then Downloads.', 0.5)
    d.click('Home', double=True)
    d.window('.*user.*', 30)
    time.sleep(1.5)
    d.click('Downloads', double=True)
    time.sleep(1.5)
    d.caption('Right-click the package and choose Extract Here.', 0.5)
    d.click('OpenHospital', button=3)
    d.click('Extract Here')
    d.find(pkg[:24], timeout=180)
    time.sleep(2)
    d.caption('Open the new folder.', 0.5)
    d.click(d.find('OpenHospital'), double=True)
    time.sleep(2)
    d.caption('Right-click an empty area and choose Open Terminal Here.', 0.5)
    x, y = d.find('oh.sh')
    d.click((x + 300, y + 200), button=3)
    d.click('Open Terminal Here')
    time.sleep(2.5)
    d.caption('Start Open Hospital with ./oh.sh.')
    d.type('./oh.sh')
    d.key('Return')
    time.sleep(3)
    d.caption('The menu shows version, language and mode. Press Enter to start.', 3)
    d.key('Return')
    d.caption('The first start creates the database, then the application opens.', 0)
    d.window('Login', 300)
    time.sleep(2)
    d.caption('Log in. The first user is admin, with password admin.')
    d.type('admin')
    d.key('Tab')
    d.type('admin')
    time.sleep(1)
    d.key('Return')
    try:
        d.window('Help us improve Open Hospital', 30)
        time.sleep(1)
        d.caption('Open Hospital asks whether it may send anonymous usage data. Choose one of the options.', 4)
        run('wmctrl', '-c', 'Help us improve Open Hospital')
    except RuntimeError:
        pass
    d.window('OH', 60)
    time.sleep(1)
    d.caption('Open Hospital is running. Next time, open the folder and start ./oh.sh again.', 5)
    d.stop('linux-portable')


if __name__ == '__main__':
    what, ver, out = sys.argv[1:4]
    desk = Desk(os.path.abspath(out))
    try:
        {'linux-portable': linux_portable}[what](desk, ver)
    except Exception:
        desk.shot(f'{desk.out}/failed.png')
        if desk.rec:
            desk.rec.communicate(b'q', timeout=60)
        raise
