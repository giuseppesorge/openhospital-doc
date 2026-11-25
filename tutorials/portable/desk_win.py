"""Records the tutorial "Download, install and start the Windows portable package" on the desktop of a Windows runner.

Windows, buttons, links and files are found by their name with UI Automation (pywinauto), then the real pointer
moves there and clicks. The Swing windows of Open Hospital are found by their title. Writes raw.mp4, the captions
(vtt and srt) and one screenshot per step; captions and music are added afterwards on Linux.

Usage: python desk_win.py <version> <out dir>
Needs: ffmpeg (gdigrab), pywinauto.
"""
import ctypes
import ctypes.wintypes
import os
import re
import subprocess
import sys
import time

from pywinauto import Desktop, keyboard

user32 = ctypes.windll.user32
user32.SetProcessDPIAware()
W, H = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
uia = Desktop(backend='uia')


class Rec:
    def __init__(self, out):
        self.out = out
        os.makedirs(out, exist_ok=True)
        self.cues, self.cur, self.n, self.proc = [], None, 0, None

    def start(self):
        self.proc = subprocess.Popen(['ffmpeg', '-loglevel', 'error', '-f', 'gdigrab', '-draw_mouse', '1', '-framerate', '25',
                                      '-i', 'desktop', '-c:v', 'libx264', '-preset', 'veryfast', '-pix_fmt', 'yuv420p',
                                      '-y', os.path.join(self.out, 'raw.mp4')], stdin=subprocess.PIPE)
        self.t0 = time.time()
        time.sleep(1.5)

    def shot(self, name):
        subprocess.run(['ffmpeg', '-loglevel', 'error', '-f', 'gdigrab', '-i', 'desktop', '-frames:v', '1', '-y',
                        os.path.join(self.out, name)], check=False)

    def caption(self, text, hold=1.5):
        now = time.time() - self.t0
        if self.cur:
            self.cues.append((self.cur[0], now, self.cur[1]))
        self.cur = (now, text) if text else None
        self.n += 1
        self.shot(f'step{self.n:02d}.png')
        time.sleep(hold)

    def stop(self, name):
        self.caption('', 0)
        if self.proc:
            self.proc.communicate(b'q', timeout=120)

        def ts(s, sep):
            return f'{int(s // 3600):02d}:{int(s % 3600 // 60):02d}:{int(s % 60):02d}{sep}{int(s * 1000) % 1000:03d}'

        body = lambda sep: ''.join(f'{i}\n{ts(a, sep)} --> {ts(b, sep)}\n{t}\n\n' for i, (a, b, t) in enumerate(self.cues, 1))
        with open(os.path.join(self.out, f'{name}.en.vtt'), 'w', encoding='utf-8') as f:
            f.write('WEBVTT\n\n' + body('.'))
        with open(os.path.join(self.out, f'{name}.srt'), 'w', encoding='utf-8') as f:
            f.write(body(','))


def pointer():
    p = ctypes.wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(p))
    return p.x, p.y


def move(x, y):
    x0, y0 = pointer()
    for k in range(1, 26):
        f = k / 25
        f = f * f * (3 - 2 * f)
        user32.SetCursorPos(round(x0 + (x - x0) * f), round(y0 + (y - y0) * f))
        time.sleep(0.02)
    time.sleep(0.3)


def click(where, button='left', double=False):
    """where: (x, y) or a pywinauto element."""
    if not isinstance(where, tuple):
        r = where.rectangle()
        where = ((r.left + r.right) // 2, (r.top + r.bottom) // 2)
    move(*where)
    down, up = (0x0002, 0x0004) if button == 'left' else (0x0008, 0x0010)
    for _ in range(2 if double else 1):
        user32.mouse_event(down, 0, 0, 0, 0)
        time.sleep(0.05)
        user32.mouse_event(up, 0, 0, 0, 0)
        time.sleep(0.12)
    time.sleep(0.8)


def keys(k, pause=0.05):
    keyboard.send_keys(k, pause=pause, with_spaces=True)
    time.sleep(0.5)


def slow(text):
    """One key at a time: Swing loses characters typed too fast."""
    for ch in text:
        keyboard.send_keys(ch)
        time.sleep(0.25)
    time.sleep(0.4)


def wait(fn, timeout, what):
    end = time.time() + timeout
    while time.time() < end:
        try:
            got = fn()
            if got:
                return got
        except Exception:
            pass
        time.sleep(1)
    raise RuntimeError(f'not found: {what}')


def window(title_re, timeout=60):
    return wait(lambda: next((w for w in uia.windows() if re.fullmatch(title_re, w.window_text())), None), timeout, title_re)


def find(parent, timeout=30, **kw):
    return wait(lambda: parent.child_window(**kw).wrapper_object(), timeout, kw)


def top_titles():
    titles = []

    def cb(h, _):
        if user32.IsWindowVisible(h):
            n = user32.GetWindowTextLengthW(h)
            b = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(h, b, n + 1)
            if b.value:
                titles.append(b.value)
        return True

    user32.EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)(cb), 0)
    return titles


def swing(title, timeout):
    return wait(lambda: title in top_titles(), timeout, f'window {title}')


def activate(title):
    h = user32.FindWindowW(None, title)
    if h:
        user32.SetForegroundWindow(h)
        time.sleep(0.5)


def run(ver, out):
    pkg = f'OpenHospital-v{ver}-windows_x86_64-portable'
    downloads = os.path.join(os.environ['USERPROFILE'], 'Downloads')
    # the console of the runner agent stays open on the desktop: out of sight
    for t in top_titles():
        if 'HostedComputeAgent' in t:
            user32.ShowWindow(user32.FindWindowW(None, t), 6)  # SW_MINIMIZE
    time.sleep(1)
    r = Rec(out)
    r.start()
    r.caption('Open Hospital on Windows: download, install and start the portable package.', 3)

    r.caption('Open Microsoft Edge and go to open-hospital.org.', 0.5)
    taskbar = uia.window(class_name='Shell_TrayWnd')
    edge = taskbar.child_window(title_re='.*Edge.*', control_type='Button')
    if edge.exists(timeout=2):
        click(edge.wrapper_object())
    else:  # not pinned: from the Start menu
        keys('{VK_LWIN}')
        time.sleep(1.5)
        slow('edge')
        keys('{ENTER}')
    browser = window('.*Microsoft.*Edge.*', 60)
    browser.set_focus()
    time.sleep(1)
    browser.maximize()
    time.sleep(1.5)
    keys('^l')
    slow('www.open-hospital.org')
    keys('{ENTER}')
    menu = find(browser, 60, title_re='(?i)download', control_type='Hyperlink', found_index=0)
    time.sleep(2)
    close = browser.child_window(title_re='[×xX]', control_type='Hyperlink', found_index=0)
    if close.exists(timeout=2):
        click(close.wrapper_object())
    r.caption('Click DOWNLOAD.')
    click(menu)
    name = f'{pkg}.zip'
    r.caption('Under the latest release, choose the portable package for Windows, 64 bit.', 0.5)
    text = find(browser, 60, title_re=re.escape(name) + '.*', control_type='Text', found_index=0)
    move(W // 2, H // 2)
    for _ in range(80):  # scroll with the wheel until the link is well inside the window
        b, t = browser.rectangle(), text.rectangle()
        if b.top + 200 < t.top < b.bottom - 150:
            break
        user32.mouse_event(0x0800, 0, 0, ctypes.c_uint(-120).value, 0)
        time.sleep(0.25)
    time.sleep(1)
    click(text)
    target = os.path.join(downloads, name)
    wait(lambda: os.path.exists(target) and not any(f.endswith('.crdownload') for f in os.listdir(downloads)), 600, 'download')
    time.sleep(2)
    r.caption('The package is in the Downloads folder. Close the browser.', 2)
    browser.set_focus()
    keys('%{F4}')
    time.sleep(2)

    r.caption('Open File Explorer, then Downloads.', 0.5)
    files = taskbar.child_window(title_re='.*File Explorer.*', control_type='Button')
    if files.exists(timeout=2):
        click(files.wrapper_object())
    else:
        keys('{VK_LWIN down}e{VK_LWIN up}')
    explorer = window('.*(File Explorer|Quick access|This PC|Home).*', 30)
    time.sleep(1.5)
    click(find(explorer, 20, title='Downloads', control_type='TreeItem', found_index=0))
    explorer = window('Downloads.*', 30)
    time.sleep(1.5)
    r.caption('Right-click the package and choose Extract All.', 0.5)
    item = find(explorer, 30, title_re=re.escape(pkg) + r'(\.zip)?', control_type='ListItem')
    click(item, button='right')
    click(find(uia, 15, title_re='Extract All.*', control_type='MenuItem'))
    dialog = window('.*Extract Compressed.*', 30)
    time.sleep(1.5)
    r.caption('Click Extract. It takes a minute.', 0.5)
    click(find(dialog, 15, title='Extract', control_type='Button'))
    folder = window(re.escape(pkg), 900)  # opens by itself at the end
    time.sleep(2)
    r.caption('Open the folder inside.', 0.5)
    click(find(folder, 30, title=pkg, control_type='ListItem'), double=True)
    find(folder, 30, title_re='RELEASE_NOTES.*', control_type='ListItem')
    time.sleep(1.5)
    r.caption('Type cmd in the address bar and press Enter: a command prompt opens in this folder.', 0.5)
    folder.set_focus()
    keys('%d')
    slow('cmd')
    keys('{ENTER}')
    window('.*cmd.exe.*', 30).set_focus()
    time.sleep(1.5)
    r.caption('Start Open Hospital with oh.bat.')
    slow('oh.bat')
    keys('{ENTER}')
    time.sleep(4)
    r.caption('The menu shows version, language and mode. Press Enter to start.', 3)
    keys('{ENTER}')
    r.caption('The first start creates the database, then the application opens.', 0)
    swing('Login', 600)
    time.sleep(2)
    activate('Login')
    r.caption('Log in. The first user is admin, with password admin.')
    slow('admin')
    keys('{TAB}')
    slow('admin')
    time.sleep(1)
    keys('{ENTER}')
    try:
        swing('Help us improve Open Hospital', 40)
        time.sleep(1)
        r.caption('Open Hospital asks whether it may send anonymous usage data. Choose one of the options.', 4)
        activate('Help us improve Open Hospital')
        keys('%{F4}')
    except RuntimeError:
        pass
    swing('OH', 60)
    time.sleep(1)
    r.caption('Open Hospital is running. Next time, open the folder and start oh.bat again.', 5)
    r.stop('windows-portable')
    with open(os.path.join(out, 'windows.txt'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(top_titles()))


if __name__ == '__main__':
    ver, out = sys.argv[1], os.path.abspath(sys.argv[2])
    try:
        run(ver, out)
    except Exception:
        subprocess.run(['ffmpeg', '-loglevel', 'error', '-f', 'gdigrab', '-i', 'desktop', '-frames:v', '1', '-y',
                        os.path.join(out, 'failed.png')])
        with open(os.path.join(out, 'windows.txt'), 'w', encoding='utf-8') as f:
            f.write('\n'.join(top_titles()))
        raise
