import { expect, test, type Page } from '@playwright/test';
import { writeFileSync } from 'node:fs';
import { canvasCentre, nodeCount, openGraph, resetServerState } from '../helpers';

/*
 * Frame-rate measurement for the knowledge graph, with every layer on (the full estate).
 * Not part of the normal run: `E2E_PERF=1 npm run e2e -- e2e/perf` prints a table and writes test-results/graph-fps.json.
 * Headless Chromium here draws with software rendering, so absolute numbers are pessimistic. The comparison between
 * the expanded and the folded graph is what matters.
 */
test.skip(!process.env.E2E_PERF, 'set E2E_PERF=1 to run the frame-rate measurement');
test.describe.configure({ mode: 'serial' });

interface Result { state: string; nodes: number; layoutMs: number; fps: number; p50: number; p95: number; worst: number; over33: number; frames: number; drawP50: number; drawP95: number; drawMax: number }
const results: Result[] = [];

async function everything(page: Page) {
  await page.getByRole('button', { name: /^Layers/ }).click();
  for (const l of ['Applications', 'APIs', 'Data stores', 'Capabilities', 'Cloud resources', 'Owners']) await page.getByRole('checkbox', { name: l }).check();
  await page.keyboard.press('Escape');
}

/** Pans and zooms for a fixed script while a rAF loop records how long each frame took. */
async function measure(page: Page, state: string, started: number): Promise<Result> {
  const g = page.getByTestId('force-graph');
  await expect(g).toHaveAttribute('data-settled', 'true', { timeout: 120_000 });
  const layoutMs = Date.now() - started;
  const { x, y } = await canvasCentre(page);
  await page.mouse.move(5, 5);
  await page.evaluate(() => {
    const w = window as unknown as { __frames: number[]; __stop: boolean; __draw: number[] };
    w.__frames = []; w.__stop = false; w.__draw = [];
    // time every animation-frame callback except our own: this is what the graph spends drawing a frame
    const raf = window.requestAnimationFrame.bind(window);
    window.requestAnimationFrame = (cb) => raf((ts) => { const a = performance.now(); cb(ts); const d = performance.now() - a; if (cb !== (tick as FrameRequestCallback) && d > 0.3) w.__draw.push(d); });
    let last = performance.now();
    function tick(t: number) { w.__frames.push(t - last); last = t; if (!w.__stop) requestAnimationFrame(tick); }
    requestAnimationFrame(tick);
  });
  const t0 = Date.now();
  await page.mouse.move(x, y);
  for (let i = 0; i < 25; i++) { await page.mouse.wheel(0, -120); await page.waitForTimeout(16); }       // zoom in
  for (let i = 0; i < 25; i++) { await page.mouse.wheel(0, 120); await page.waitForTimeout(16); }        // and back out
  await page.mouse.down();
  for (let i = 0; i < 60; i++) await page.mouse.move(x + Math.sin(i / 6) * 160, y + Math.cos(i / 6) * 90);  // pan around
  await page.mouse.up();
  for (let i = 0; i < 60; i++) { await page.mouse.move(x + (i % 30) * 9, y + Math.sin(i) * 120); await page.waitForTimeout(8); } // hover sweep
  const secs = (Date.now() - t0) / 1000;
  const frames = await page.evaluate(() => { const w = window as unknown as { __frames: number[]; __stop: boolean }; w.__stop = true; return w.__frames.slice(1); });
  // frames are only produced while something changes, so count the busy ones
  const busy = frames.filter((f) => f < 250).sort((a, b) => a - b);
  const q = (p: number) => busy[Math.min(busy.length - 1, Math.floor(busy.length * p))] ?? 0;
  const draw = (await page.evaluate(() => (window as unknown as { __draw: number[] }).__draw)).sort((a, b) => a - b);
  const dq = (p: number) => Math.round((draw[Math.min(draw.length - 1, Math.floor(draw.length * p))] ?? 0) * 10) / 10;
  return {
    state, nodes: await nodeCount(page), layoutMs, drawP50: dq(0.5), drawP95: dq(0.95), drawMax: Math.round(draw[draw.length - 1] ?? 0),
    fps: Math.round(busy.length / secs), p50: Math.round(q(0.5) * 10) / 10, p95: Math.round(q(0.95) * 10) / 10, worst: Math.round(busy[busy.length - 1] ?? 0),
    over33: busy.filter((f) => f > 33.4).length, frames: busy.length,
  };
}

test.beforeEach(async ({ request }) => resetServerState(request));

test('expanded: all 635 nodes', async ({ page }) => {
  await openGraph(page);
  const t = Date.now();
  await everything(page);
  results.push(await measure(page, 'expanded', t));
});

test('folded: every domain a bubble', async ({ page }) => {
  await openGraph(page);
  await everything(page);
  await expect(page.getByTestId('force-graph')).toHaveAttribute('data-settled', 'true', { timeout: 120_000 });
  const t = Date.now();
  await page.getByRole('button', { name: /^Fold domains/ }).click();
  await page.getByRole('button', { name: 'Fold all', exact: true }).click();
  await page.keyboard.press('Escape');
  results.push(await measure(page, 'folded', t));
});

test.afterAll(async () => {
  console.log('\nstate     nodes  layout(ms)  fps  frame p50/p95/worst (ms)  frames>33ms  draw p50/p95/max (ms)');
  for (const r of results) console.log(`${r.state.padEnd(9)} ${String(r.nodes).padStart(5)}  ${String(r.layoutMs).padStart(10)}  ${String(r.fps).padStart(3)}  ${`${r.p50}/${r.p95}/${r.worst}`.padEnd(24)} ${String(r.over33).padStart(11)}  ${r.drawP50}/${r.drawP95}/${r.drawMax}`);
  writeFileSync('test-results/graph-fps.json', JSON.stringify(results, null, 2));
});
