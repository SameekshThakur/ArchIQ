import { expect, test } from '@playwright/test';
import { canvasCentre, nodeCount, openGraph, picture, resetServerState, zoomOf, zoomToNode } from './helpers';

test.beforeEach(async ({ request }) => resetServerState(request));
test.afterEach(async ({ request }) => resetServerState(request));

test.describe('knowledge graph', () => {
  test('draws the estate and settles', async ({ page }) => {
    await openGraph(page);
    expect(await nodeCount(page)).toBeGreaterThan(50);
    await expect(page.getByRole('toolbar', { name: 'Graph controls' })).toBeVisible();
  });

  test('find in view zooms to the node and isolates its neighbourhood', async ({ page }) => {
    await openGraph(page);
    const before = await zoomOf(page);
    const wide = await picture(page);
    await zoomToNode(page, 'Claims Intake Portal');
    expect(await zoomOf(page)).toBeGreaterThan(before * 2);
    await expect(page.getByRole('button', { name: 'Clear selection' })).toBeVisible();
    expect((await picture(page)).equals(wide)).toBe(false);
    // clicking the background lets go of it
    await page.getByRole('button', { name: 'Clear selection' }).click();
    await expect(page.getByRole('button', { name: 'Clear selection' })).toHaveCount(0);
  });

  test('find in view works from the keyboard and explains an empty result', async ({ page }) => {
    await openGraph(page);
    const box = page.getByRole('combobox', { name: 'Find a node in this view' });
    await box.fill('zzzz-nothing');
    await expect(page.getByText(/nothing in this view matches/i)).toBeVisible();
    await box.fill('claims');
    await page.keyboard.press('ArrowDown');
    await page.keyboard.press('Enter');
    await expect(page.getByRole('button', { name: 'Clear selection' })).toBeVisible();
  });

  /*
   * Regression: hovering used to restart the layout, and a press that wobbled by a pixel was read as a drag, which both
   * moved the graph and swallowed the click so nothing could be selected.
   */
  test('hovering does not move anything', async ({ page }) => {
    await openGraph(page);
    await zoomToNode(page, 'Claims Intake Portal');
    await page.getByRole('button', { name: 'Clear selection' }).click();
    const { x, y } = await canvasCentre(page);

    // 1. the picture with the pointer parked outside the graph
    await page.mouse.move(5, 5);
    await page.waitForTimeout(400);
    const before = await picture(page);

    // 2. hovering a node and wiggling over it must leave nothing still animating
    await page.mouse.move(x - 40, y - 40);
    await page.mouse.move(x, y, { steps: 8 });
    for (let i = 0; i < 20; i++) await page.mouse.move(x + (i % 5) * 2, y + (i % 3) * 2);
    await page.mouse.move(x, y);
    await page.waitForTimeout(600);
    const hovered = await picture(page);
    await page.waitForTimeout(1800);
    expect((await picture(page)).equals(hovered), 'the picture kept changing while hovering').toBe(true);

    // 3. and once the pointer leaves, the layout is exactly where it was
    await page.mouse.move(5, 5);
    await page.waitForTimeout(600);
    expect((await picture(page)).equals(before), 'hovering shifted the layout').toBe(true);
  });

  test('a click that wobbles a little still selects the node', async ({ page }) => {
    await openGraph(page);
    await zoomToNode(page, 'Claims Intake Portal');
    await page.getByRole('button', { name: 'Clear selection' }).click();
    const { x, y } = await canvasCentre(page);
    await page.mouse.move(x, y, { steps: 6 });
    await page.mouse.down();
    await page.mouse.move(x + 2, y + 1);
    await page.mouse.move(x + 3, y + 2);
    await page.mouse.up();
    await expect(page.getByRole('heading', { name: /Claims Intake Portal/ })).toBeVisible();
  });

  test('dragging a node pans the view without selecting or shuffling anything', async ({ page }) => {
    await openGraph(page);
    await zoomToNode(page, 'Claims Intake Portal');
    await page.getByRole('button', { name: 'Clear selection' }).click();
    const { x, y } = await canvasCentre(page);
    await page.mouse.move(x, y, { steps: 4 });
    await page.mouse.down();
    await page.mouse.move(x + 90, y + 50, { steps: 10 });
    await page.mouse.up();
    await page.waitForTimeout(600);
    await expect(page.getByRole('heading', { name: /Claims Intake Portal/ })).toHaveCount(0);
    const first = await picture(page);
    await page.waitForTimeout(1800);
    expect((await picture(page)).equals(first)).toBe(true); // nothing is still moving
  });

  test('domain and criticality filters narrow the view and clear again', async ({ page }) => {
    await openGraph(page);
    const total = await nodeCount(page);
    await page.getByRole('button', { name: /^Domains/ }).click();
    await page.getByRole('checkbox', { name: /^Claims/ }).check();
    await page.keyboard.press('Escape');
    await expect.poll(() => nodeCount(page)).toBeLessThan(total);
    const claimsOnly = await nodeCount(page);
    await page.getByRole('button', { name: /^Criticality/ }).click();
    await page.getByRole('checkbox', { name: /critical/i }).first().check();
    await page.keyboard.press('Escape');
    await expect.poll(() => nodeCount(page)).toBeLessThanOrEqual(claimsOnly);
    await page.getByRole('button', { name: 'Clear filters' }).click();
    await expect.poll(() => nodeCount(page)).toBe(total);
  });

  test('a filter that leaves nothing says so and offers a way back', async ({ page }) => {
    await openGraph(page);
    await page.getByRole('button', { name: /^Layers/ }).click();
    for (const l of ['Applications', 'Data stores']) await page.getByRole('checkbox', { name: l }).uncheck();
    await page.keyboard.press('Escape');
    await expect(page.getByText('No nodes match')).toBeVisible();
  });

  test('views are saved on the server, survive a reload, and can be deleted', async ({ page }) => {
    await openGraph(page);
    const total = await nodeCount(page);
    await page.getByRole('button', { name: /^Domains/ }).click();
    await page.getByRole('checkbox', { name: /^Claims/ }).check();
    await page.keyboard.press('Escape');
    await expect.poll(() => nodeCount(page)).toBeLessThan(total);

    await page.getByRole('button', { name: /^Views/ }).click();
    await page.getByLabel('Save the current view').fill('E2E claims only');
    await page.getByRole('button', { name: 'Save', exact: true }).click();
    await expect(page.getByRole('status').filter({ hasText: 'Saved' })).toBeVisible();

    await page.reload();
    await expect(page.getByTestId('force-graph')).toHaveAttribute('data-settled', 'true', { timeout: 30_000 });
    expect(await nodeCount(page)).toBe(total); // a fresh load is unfiltered
    await page.getByRole('button', { name: /^Views/ }).click();
    await page.getByRole('button', { name: /^E2E claims only/ }).click();
    await expect.poll(() => nodeCount(page)).toBeLessThan(total);
    await expect(page.getByRole('button', { name: /^Domains/ })).toContainText('1');

    await page.getByRole('button', { name: /^Views/ }).click();
    await page.getByRole('button', { name: 'Delete view E2E claims only' }).click();
    await expect(page.getByText('None yet')).toBeVisible();
  });

  test('saving a view needs a name', async ({ page }) => {
    await openGraph(page);
    await page.getByRole('button', { name: /^Views/ }).click();
    await page.getByRole('button', { name: 'Save', exact: true }).click();
    await expect(page.getByText('Give the view a name first.')).toBeVisible();
  });

  test('exports a PNG of the current view', async ({ page }) => {
    await openGraph(page);
    await page.getByRole('button', { name: 'Export' }).click();
    const [download] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: /PNG image/ }).click()]);
    expect(download.suggestedFilename()).toMatch(/^archiq-knowledge-graph-\d{4}-\d{2}-\d{2}\.png$/);
    const bytes = await (await import('node:fs/promises')).readFile((await download.path())!);
    expect([...bytes.subarray(0, 8)]).toEqual([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
    expect(bytes.length).toBeGreaterThan(20_000);
  });

  test('exports a valid SVG of the whole graph', async ({ page }) => {
    await openGraph(page);
    await page.getByRole('button', { name: 'Export' }).click();
    const [download] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: /SVG vector/ }).click()]);
    expect(download.suggestedFilename()).toMatch(/\.svg$/);
    const svg = (await (await import('node:fs/promises')).readFile((await download.path())!, 'utf8'));
    expect(svg.startsWith('<svg xmlns="http://www.w3.org/2000/svg"')).toBe(true);
    expect(svg).toContain('Knowledge graph');
    expect(svg).toContain('CLAIMS'); // domain territory label
    expect((svg.match(/<circle/g) ?? []).length).toBeGreaterThan(40);
    // it must be well-formed XML
    const ok = await page.evaluate((s) => !new DOMParser().parseFromString(s, 'image/svg+xml').querySelector('parsererror'), svg);
    expect(ok).toBe(true);
  });

  test('full screen keeps the toolbar working and shows a details card', async ({ page }) => {
    await openGraph(page);
    await page.getByRole('button', { name: 'Full screen' }).click();
    await expect.poll(() => page.evaluate(() => !!document.fullscreenElement)).toBe(true);
    await expect(page.getByRole('button', { name: 'Exit full screen' })).toBeVisible();

    // menus are not portalled to <body>, so they must still be visible here
    await page.getByRole('button', { name: /^Domains/ }).click();
    await expect(page.getByRole('checkbox', { name: /^Claims/ })).toBeVisible();
    await page.keyboard.press('Escape');

    // the canvas fills the screen
    const size = await page.evaluate(() => {
      const c = document.querySelector('canvas')!.getBoundingClientRect();
      return { w: c.width / innerWidth, h: c.height / innerHeight };
    });
    expect(size.w).toBeGreaterThan(0.9);
    expect(size.h).toBeGreaterThan(0.8);

    await zoomToNode(page, 'Claims Intake Portal');
    await page.getByRole('button', { name: 'Clear selection' }).click();
    const { x, y } = await canvasCentre(page);
    await page.mouse.move(x, y, { steps: 5 });
    await page.mouse.click(x, y);
    await expect(page.getByRole('dialog', { name: /Claims Intake Portal details/ })).toBeVisible();

    await page.getByRole('button', { name: 'Exit full screen' }).click();
    await expect.poll(() => page.evaluate(() => !!document.fullscreenElement)).toBe(false);
  });
});
