// Records one tutorial: scenario JSON -> video (mp4), subtitles (vtt), one screenshot per step.
import { chromium } from 'playwright';
import { readFileSync, writeFileSync, mkdirSync, renameSync } from 'fs';
import { execFileSync } from 'child_process';
const sc = JSON.parse(readFileSync(process.argv[2], 'utf8'));
const out = `out/${sc.id}`; mkdirSync(out, { recursive: true });
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1280, height: 720 }, recordVideo: { dir: out, size: { width: 1280, height: 720 } } });
await ctx.addInitScript(() => {
  addEventListener('DOMContentLoaded', () => {
    const c = document.createElement('div'); c.id = '__cur';
    c.style.cssText = 'position:fixed;z-index:99999;left:640px;top:360px;width:22px;height:22px;border-radius:50%;background:rgba(220,40,40,.55);border:2px solid #fff;pointer-events:none;transition:left .6s,top .6s;transform:translate(-50%,-50%)';
    const k = document.createElement('div'); k.id = '__cap';
    k.style.cssText = 'position:fixed;z-index:99998;left:50%;bottom:28px;transform:translateX(-50%);max-width:80%;padding:10px 18px;background:rgba(0,0,0,.78);color:#fff;font:20px/1.35 sans-serif;border-radius:8px;pointer-events:none;text-align:center';
    document.body.append(c, k);
  });
});
const page = await ctx.newPage();
const t0 = Date.now(); const cues = [];
const sleep = ms => page.waitForTimeout(ms);
async function caption(t) { await page.evaluate(t => { const k = document.getElementById('__cap'); if (k) k.textContent = t; }, t); }
async function moveTo(sel) {
  const box = await page.locator(sel).first().boundingBox();
  await page.evaluate(([x, y]) => { const c = document.getElementById('__cur'); c.style.left = x + 'px'; c.style.top = y + 'px'; }, [box.x + box.width / 2, box.y + box.height / 2]);
  await sleep(800);
}
const start = process.env.OH_UI_URL ?? sc.start; // address of the web UI under test
if (!start) throw new Error('set OH_UI_URL to the address of the web UI');
await page.goto(start);
let i = 0;
for (const s of sc.steps) {
  i++;
  if (s.wait && !s.click) await page.waitForSelector(s.wait, { timeout: 30000 });
  const start = (Date.now() - t0) / 1000;
  await caption(s.caption); await sleep(1500);
  for (const [sel, val] of Object.entries(s.type || {})) { await moveTo(sel); await page.locator(sel).click(); await page.locator(sel).pressSequentially(val, { delay: 120 }); }
  if (s.point) await moveTo(s.point);
  await page.screenshot({ path: `${out}/step${String(i).padStart(2, '0')}.png` });
  if (s.click) { await moveTo(s.click); await page.locator(s.click).first().click(); }
  if (s.waitUrl) await page.waitForURL(u => u.toString().includes(s.waitUrl), { timeout: 30000 });
  if (s.wait && s.click) await page.waitForSelector(s.wait, { timeout: 30000 });
  await sleep(s.hold || 1500);
  await caption(s.caption);
  cues.push([start, (Date.now() - t0) / 1000, s.caption]);
}
const video = await page.video().path(); await ctx.close(); await browser.close();
const f = x => new Date(x * 1000).toISOString().slice(11, 23);
writeFileSync(`${out}/${sc.id}.en.vtt`, 'WEBVTT\n\n' + cues.map(([a, b, t], n) => `${n + 1}\n${f(a)} --> ${f(b)}\n${t}\n`).join('\n'));
execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-i', video, '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', `${out}/${sc.id}.mp4`]);
renameSync(video, `${out}/raw.webm`);
console.log('done', out, cues.length, 'steps', ((Date.now() - t0) / 1000).toFixed(1) + 's');
