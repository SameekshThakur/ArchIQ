import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';
import { openGraph, resetServerState, setTheme } from './helpers';

const PAGES = ['/', '/graph', '/discovery', '/documents', '/standards', '/reviews'];

async function violations(page: Page) {
  const r = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']).analyze();
  return r.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical').map((v) => `${v.id}: ${v.nodes.slice(0, 3).map((n) => n.target.join(' ')).join(' | ')}`);
}

for (const theme of ['dark', 'light'] as const) {
  test.describe(`accessibility, ${theme} theme`, () => {
    test.beforeEach(async ({ page, request }) => { await resetServerState(request); await setTheme(page, theme); });

    for (const path of PAGES) {
      test(`${path} has no serious violations`, async ({ page }) => {
        await page.goto(path);
        await page.waitForLoadState('networkidle');
        if (path === '/graph') await expect(page.getByTestId('force-graph')).toHaveAttribute('data-settled', 'true', { timeout: 30_000 });
        expect(await violations(page)).toEqual([]);
      });
    }

    test('graph toolbar menus have no serious violations when open', async ({ page }) => {
      await openGraph(page);
      for (const name of [/^Layers/, /^Domains/, /^Criticality/, /^Relationships/, /^Fold domains/, /^Colour/, /^Views/, /^Export/]) {
        await page.getByRole('button', { name }).click();
        await page.waitForTimeout(400); // the menu fades in; measuring contrast mid-fade gives false alarms
        expect(await violations(page), String(name)).toEqual([]);
        await page.keyboard.press('Escape');
      }
    });

    test('the graph table view and its connections panel have no serious violations', async ({ page }) => {
      await openGraph(page);
      await page.getByRole('button', { name: 'Table', exact: true }).click();
      await page.locator('#node-table-filter').fill('Claims Intake Portal');
      await page.getByRole('row', { name: /Claims Intake Portal/ }).first().click();
      await page.waitForTimeout(400);
      expect(await violations(page)).toEqual([]);
      await page.getByRole('button', { name: /^Export/ }).click();
      await page.waitForTimeout(400);
      expect(await violations(page)).toEqual([]);
    });

    test('the graph with folded domains and a focused canvas has no serious violations', async ({ page }) => {
      await openGraph(page);
      await page.getByRole('button', { name: /^Fold domains/ }).click();
      await page.getByRole('button', { name: 'Fold all' }).click();
      await page.keyboard.press('Escape');
      await page.getByTestId('force-graph').focus();
      await page.waitForTimeout(800);
      expect(await violations(page)).toEqual([]);
    });

    test('the top bar buttons are named by what they show', async ({ page }) => {
      await page.goto('/');
      await expect(page.getByRole('button', { name: /Search or ask/ })).toBeVisible();
      await expect(page.getByRole('button', { name: /Scope: / })).toBeVisible();
    });
  });
}

test.describe('exports follow the theme', () => {
  test('a light-theme SVG has a light background and dark text', async ({ page }) => {
    await setTheme(page, 'light');
    await openGraph(page);
    await page.getByRole('button', { name: 'Export' }).click();
    const [download] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: /SVG vector/ }).click()]);
    const svg = await (await import('node:fs/promises')).readFile((await download.path())!, 'utf8');
    const lum = (c: string) => {
      const m = c.match(/rgba?\(([^)]+)\)/)?.[1].split(',').map(Number) ?? [];
      return m.length ? (0.2126 * m[0] + 0.7152 * m[1] + 0.0722 * m[2]) / 255 : NaN;
    };
    const bg = svg.match(/<rect width="100%" height="100%" fill="([^"]+)"/)?.[1] ?? '';
    const title = svg.match(/font-weight="600" fill="([^"]+)"[^>]*>Knowledge graph/)?.[1] ?? svg.match(/fill="([^"]+)">Knowledge graph/)?.[1] ?? '';
    expect(lum(bg), `background ${bg}`).toBeGreaterThan(0.85);
    expect(lum(title), `title ${title}`).toBeLessThan(0.3);
  });

  test('a dark-theme SVG has a dark background', async ({ page }) => {
    await setTheme(page, 'dark');
    await openGraph(page);
    await page.getByRole('button', { name: 'Export' }).click();
    const [download] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: /SVG vector/ }).click()]);
    const svg = await (await import('node:fs/promises')).readFile((await download.path())!, 'utf8');
    const bg = svg.match(/<rect width="100%" height="100%" fill="([^"]+)"/)?.[1] ?? '';
    const nums = bg.match(/\d+/g)?.map(Number) ?? [255, 255, 255];
    expect((0.2126 * nums[0] + 0.7152 * nums[1] + 0.0722 * nums[2]) / 255).toBeLessThan(0.2);
  });
});
