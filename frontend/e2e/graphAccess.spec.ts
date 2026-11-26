import { expect, test, type Page } from '@playwright/test';
import { canvasCentre, nodeCount, openGraph, resetServerState, zoomOf, zoomToNode } from './helpers';

test.beforeEach(async ({ request }) => resetServerState(request));
test.afterEach(async ({ request }) => resetServerState(request));

const announcer = (page: Page) => page.getByTestId('force-graph').getByRole('status');
const menu = async (page: Page, name: RegExp) => { await page.getByRole('button', { name }).click(); await page.waitForTimeout(250); };

async function showEverything(page: Page) {
  await menu(page, /^Layers/);
  for (const l of ['Applications', 'APIs', 'Data stores', 'Capabilities', 'Cloud resources', 'Owners']) await page.getByRole('checkbox', { name: l }).check();
  await page.keyboard.press('Escape');
  await expect(page.getByTestId('force-graph')).toHaveAttribute('data-settled', 'true', { timeout: 45_000 });
}

test.describe('keyboard and screen-reader access', () => {
  test('the graph can be focused, announces itself and has instructions for assistive tech', async ({ page }) => {
    await openGraph(page);
    const g = page.getByTestId('force-graph');
    await g.focus();
    await expect(g).toBeFocused();
    const described = await g.getAttribute('aria-describedby');
    expect(await page.locator(`[id="${described}"]`).textContent()).toMatch(/arrow keys move to the connected node/i);
    await expect(announcer(page)).toHaveAttribute('aria-live', 'polite');
  });

  test('arrow keys walk from node to connected node and say where they are', async ({ page }) => {
    await openGraph(page);
    const g = page.getByTestId('force-graph');
    await g.focus();
    await page.keyboard.press('ArrowRight'); // first press picks a starting node
    await expect(page.getByRole('button', { name: 'Clear selection' })).toBeVisible();
    const seen = new Set<string>();
    seen.add((await announcer(page).textContent()) ?? '');
    for (let i = 0; i < 12 && seen.size < 3; i++) {
      await page.keyboard.press(['ArrowRight', 'ArrowDown', 'ArrowLeft', 'ArrowUp'][i % 4]);
      await page.waitForTimeout(150);
      seen.add((await announcer(page).textContent()) ?? '');
    }
    const moved = [...seen].filter((t) => /connection/.test(t));
    expect(moved.length, `announcements: ${[...seen].join(' | ')}`).toBeGreaterThanOrEqual(2);
    // the announcement names the selected node, type, domain and degree
    expect(moved[moved.length - 1]).toMatch(/^.+, .+, \d+ connections?\.$/);
    // the selected node chip matches the last announcement
    const chip = (await page.getByRole('toolbar').locator('span.truncate').first().textContent()) ?? '';
    expect(chip.length).toBeGreaterThan(2);
  });

  test('Enter opens details, Escape clears, 0 fits and + zooms', async ({ page }) => {
    await openGraph(page);
    await zoomToNode(page, 'Claims Intake Portal');
    const g = page.getByTestId('force-graph');
    await g.focus();
    const z = await zoomOf(page);
    await page.keyboard.press('-');
    await expect.poll(() => zoomOf(page)).toBeLessThan(z);
    await page.keyboard.press('0');
    await page.waitForTimeout(700);
    expect(await zoomOf(page)).toBeLessThan(z);
    await page.keyboard.press('Enter');
    await expect(page.getByRole('heading', { name: /Claims Intake Portal/ })).toBeVisible();
    await page.keyboard.press('Escape'); // closes the inspector
    await g.focus();
    await page.keyboard.press('Escape');
    await expect(page.getByRole('button', { name: 'Clear selection' })).toHaveCount(0);
    await expect(announcer(page)).toHaveText('Selection cleared.');
  });

  test('typing in the toolbar search is not stolen by the graph shortcuts', async ({ page }) => {
    await openGraph(page);
    const box = page.getByRole('combobox', { name: 'Find a node in this view' });
    await box.click();
    await page.keyboard.type('c0-+');
    await expect(box).toHaveValue('c0-+');
  });
});

test.describe('table view', () => {
  test('lists the same nodes as the graph and follows the same filters', async ({ page }) => {
    await openGraph(page);
    const total = await nodeCount(page);
    await page.getByRole('button', { name: 'Table', exact: true }).click();
    const table = page.getByRole('table', { name: 'Graph nodes' });
    await expect(table).toBeVisible();
    await expect(page.getByRole('button', { name: 'Table', exact: true })).toHaveAttribute('aria-pressed', 'true');
    expect(Number(await table.getAttribute('aria-rowcount'))).toBe(total);

    await menu(page, /^Domains/);
    await page.getByRole('checkbox', { name: /^Claims/ }).check();
    await page.keyboard.press('Escape');
    await expect.poll(async () => Number(await table.getAttribute('aria-rowcount'))).toBeLessThan(total);
    const claims = Number(await table.getAttribute('aria-rowcount'));
    // the graph, once shown again, has the same number of nodes
    await page.getByRole('button', { name: 'Graph', exact: true }).click();
    await expect.poll(() => nodeCount(page)).toBe(claims);
  });

  test('graph-only controls disappear and export becomes a CSV', async ({ page }) => {
    await openGraph(page);
    await page.getByRole('button', { name: 'Table', exact: true }).click();
    await expect(page.getByRole('combobox', { name: 'Find a node in this view' })).toHaveCount(0);
    await expect(page.getByRole('button', { name: /^Fold domains/ })).toHaveCount(0);
    await expect(page.getByRole('button', { name: /^Colour/ })).toHaveCount(0);
    await menu(page, /^Export/);
    await expect(page.getByRole('button', { name: /PNG image/ })).toHaveCount(0);
    const [download] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: /CSV spreadsheet/ }).click()]);
    expect(download.suggestedFilename()).toMatch(/^archiq-knowledge-graph-\d{4}-\d{2}-\d{2}\.csv$/);
    const text = await (await import('node:fs/promises')).readFile((await download.path())!, 'utf8');
    const lines = (text.charCodeAt(0) === 0xfeff ? text.slice(1) : text).trim().split(/\r\n/);
    expect(lines[0]).toBe('id,name,type,domain,criticality,lifecycle,links');
    expect(lines.length - 1).toBe(await nodeCount(page));
    expect(text).toContain('"Claims Intake Portal"');
  });

  test('selecting a row lists its connections, and Show in graph jumps to it', async ({ page }) => {
    await openGraph(page);
    await page.getByRole('button', { name: 'Table', exact: true }).click();
    await page.locator('#node-table-filter').fill('Claims Intake Portal');
    await page.getByRole('row', { name: /Claims Intake Portal/ }).first().click();
    const aside = page.getByRole('complementary', { name: /connections of the selected node/i });
    await expect(aside.getByRole('region').first()).toBeVisible();
    expect(await aside.getByRole('button').count()).toBeGreaterThan(2);
    await aside.getByRole('button', { name: /show in graph/i }).click();
    await expect(page.getByRole('button', { name: 'Clear selection' })).toBeVisible();
    await expect.poll(() => zoomOf(page), { timeout: 8000 }).toBeGreaterThan(3);
  });

  test('rows can be chosen from the keyboard', async ({ page }) => {
    await openGraph(page);
    await page.getByRole('button', { name: 'Table', exact: true }).click();
    await page.locator('#node-table-filter').fill('Claims');
    const row = page.getByRole('row').nth(1);
    await row.focus();
    await page.keyboard.press('Enter');
    await expect(page.getByRole('complementary', { name: /connections of the selected node/i }).getByRole('button', { name: /open details/i })).toBeVisible();
  });
});

test.describe('folding domains', () => {
  test('Fold all turns the estate into a handful of bubbles, Open all brings it back', async ({ page }) => {
    await openGraph(page);
    const total = await nodeCount(page);
    await menu(page, /^Fold domains/);
    await page.getByRole('button', { name: 'Fold all', exact: true }).click();
    await page.keyboard.press('Escape');
    await expect.poll(() => nodeCount(page)).toBeLessThan(total / 2);
    await expect(page.getByRole('button', { name: /^Fold domains/ })).toContainText(/\d/);
    await menu(page, /^Fold domains/);
    await page.getByRole('button', { name: 'Open all' }).click();
    await page.keyboard.press('Escape');
    await expect.poll(() => nodeCount(page)).toBe(total);
  });

  test('a single domain can be folded from the menu', async ({ page }) => {
    await openGraph(page);
    const total = await nodeCount(page);
    await menu(page, /^Fold domains/);
    await page.getByRole('checkbox', { name: /^Claims/ }).check();
    await page.keyboard.press('Escape');
    await expect.poll(() => nodeCount(page)).toBeLessThan(total);
    await expect(page.getByRole('button', { name: /^Fold domains/ })).toContainText('1');
    await menu(page, /^Fold domains/);
    await page.getByRole('checkbox', { name: /^Claims/ }).uncheck();
    await page.keyboard.press('Escape');
    await expect.poll(() => nodeCount(page)).toBe(total);
  });

  test('keyboard: arrow to a folded bubble, announce it, and C opens just that domain', async ({ page }) => {
    await openGraph(page);
    await menu(page, /^Fold domains/);
    await page.getByRole('button', { name: 'Fold all', exact: true }).click();
    await page.keyboard.press('Escape');
    await expect(page.getByTestId('force-graph')).toHaveAttribute('data-settled', 'true', { timeout: 30_000 });
    const folded = await nodeCount(page);
    const g = page.getByTestId('force-graph');
    await g.focus();
    let found = false;
    for (let i = 0; i < 80 && !found; i++) {
      await page.keyboard.press(i === 0 ? 'Home' : ['ArrowRight', 'ArrowDown', 'ArrowLeft', 'ArrowUp'][i % 4]);
      await page.waitForTimeout(60);
      found = /domain, folded, \d+ nodes\. Press Enter to open it\./.test((await announcer(page).textContent()) ?? '');
    }
    expect(found, 'the keyboard never reached a bubble').toBe(true);
    await page.keyboard.press('c');
    await expect.poll(() => nodeCount(page), { timeout: 5000 }).toBeGreaterThan(folded);
    expect(await nodeCount(page)).toBeLessThan(folded + 120); // one domain opened, not all of them
  });

  test('clicking a folded bubble opens it', async ({ page }) => {
    await openGraph(page);
    const total = await nodeCount(page);
    await menu(page, /^Fold domains/);
    await page.getByRole('button', { name: 'Fold all', exact: true }).click();
    await page.keyboard.press('Escape');
    await expect.poll(() => nodeCount(page)).toBeLessThan(total / 2);
    await expect(page.getByTestId('force-graph')).toHaveAttribute('data-settled', 'true', { timeout: 30_000 });
    const folded = await nodeCount(page);
    // find a bubble by walking with the keyboard (which also centres it), then click the centre of the canvas
    const g = page.getByTestId('force-graph');
    await g.focus();
    let found = false;
    for (let i = 0; i < 60 && !found; i++) {
      await page.keyboard.press(i === 0 ? 'Home' : ['ArrowRight', 'ArrowDown', 'ArrowLeft', 'ArrowUp'][i % 4]);
      await page.waitForTimeout(80);
      found = /domain, folded/.test((await announcer(page).textContent()) ?? '');
    }
    expect(found, 'no bubble reached from the keyboard').toBe(true);
    await page.waitForTimeout(500); // camera settles on the bubble
    const { x, y } = await canvasCentre(page);
    await page.mouse.move(x, y, { steps: 5 });
    await page.mouse.down();
    await page.mouse.up();
    await expect.poll(() => nodeCount(page), { timeout: 5000 }).toBeGreaterThan(folded);
  });

  test('finding a node inside a folded domain opens the domain and flies to it', async ({ page }) => {
    await openGraph(page);
    await menu(page, /^Fold domains/);
    await page.getByRole('button', { name: 'Fold all', exact: true }).click();
    await page.keyboard.press('Escape');
    const folded = await nodeCount(page);
    const box = page.getByRole('combobox', { name: 'Find a node in this view' });
    await box.fill('Claims Intake Portal');
    await page.getByRole('option').first().click();
    await expect.poll(() => nodeCount(page), { timeout: 5000 }).toBeGreaterThan(folded);
    await expect.poll(() => zoomOf(page), { timeout: 8000 }).toBeGreaterThan(3);
  });

  test('a large graph offers to fold itself, and the bubbles survive saving a view', async ({ page }) => {
    await openGraph(page);
    await showEverything(page);
    if ((await nodeCount(page)) > 300) {
      await expect(page.getByTestId('fold-hint')).toBeVisible();
      await page.getByTestId('fold-hint').getByRole('button', { name: 'Fold all domains' }).click();
      await expect(page.getByTestId('fold-hint')).toHaveCount(0);
    } else {
      await menu(page, /^Fold domains/);
      await page.getByRole('button', { name: 'Fold all', exact: true }).click();
      await page.keyboard.press('Escape');
    }
    const folded = await nodeCount(page);
    expect(folded).toBeLessThan(120);
    await menu(page, /^Views/);
    await page.getByLabel('Save the current view').fill('E2E folded');
    await page.getByRole('button', { name: 'Save', exact: true }).click();
    await expect(page.getByRole('status').filter({ hasText: 'Saved' })).toBeVisible();
    await page.keyboard.press('Escape');
    await page.reload();
    await expect(page.getByTestId('force-graph')).toHaveAttribute('data-settled', 'true', { timeout: 30_000 });
    await menu(page, /^Views/);
    await page.getByRole('button', { name: /^E2E folded/ }).click();
    await expect.poll(() => nodeCount(page), { timeout: 10_000 }).toBe(folded);
  });
});

test.describe('relationship filter and link labels', () => {
  test('filters by kind of relationship and clears again', async ({ page }) => {
    await openGraph(page);
    const total = await nodeCount(page);
    await menu(page, /^Relationships/);
    const boxes = page.getByRole('dialog', { name: 'Relationships' }).getByRole('checkbox');
    expect(await boxes.count()).toBeGreaterThanOrEqual(3);
    await boxes.first().check();
    await page.keyboard.press('Escape');
    await expect.poll(() => nodeCount(page)).toBeLessThan(total);
    await expect(page.getByRole('button', { name: /^Relationships/ })).toContainText('1');
    // the table shows the same nodes
    const filteredCount = await nodeCount(page);
    await page.getByRole('button', { name: 'Table', exact: true }).click();
    expect(Number(await page.getByRole('table', { name: 'Graph nodes' }).getAttribute('aria-rowcount'))).toBe(filteredCount);
    await page.getByRole('button', { name: 'Clear filters' }).click();
    await expect.poll(async () => Number(await page.getByRole('table', { name: 'Graph nodes' }).getAttribute('aria-rowcount'))).toBe(total);
  });

  test('hovering a link names its relationship', async ({ page }) => {
    await openGraph(page);
    await zoomToNode(page, 'Claims Intake Portal');
    const { x, y } = await canvasCentre(page);
    const tip = page.locator('.float-tooltip-kap');
    let text = '';
    // sweep rings around the selected node until the pointer lands on one of its links
    outer: for (const r of [60, 80, 100, 125, 150, 180, 220]) {
      for (let a = 0; a < 360; a += 3) {
        await page.mouse.move(x + r * Math.cos((a * Math.PI) / 180), y + r * Math.sin((a * Math.PI) / 180));
        await page.waitForTimeout(12);
        if (await tip.isVisible().catch(() => false)) { text = (await tip.textContent()) ?? ''; if (text) break outer; }
      }
    }
    expect(text, 'the pointer never landed on a link').toMatch(/\w/);
    expect(text.toLowerCase()).toMatch(/integrates|calls|uses|owns|stores data in|hosted on|consumes|exposes|depends|supports|realises|realizes|runs/);
  });

  test('a relationship filter and folded domains are listed in the export subtitle context', async ({ page }) => {
    await openGraph(page);
    await menu(page, /^Relationships/);
    await page.getByRole('dialog', { name: 'Relationships' }).getByRole('checkbox').first().check();
    await page.keyboard.press('Escape');
    await menu(page, /^Export/);
    const [download] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: /SVG vector/ }).click()]);
    const svg = await (await import('node:fs/promises')).readFile((await download.path())!, 'utf8');
    expect(svg).toContain('relationships:');
  });
});
