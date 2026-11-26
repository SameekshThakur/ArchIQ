import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';
import { resetServerState, setTheme } from './helpers';

const SHOTS = process.env.STUDIO_SHOTS;
const shot = async (page: Page, name: string) => { if (SHOTS) await page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: true }); };
const serious = async (page: Page) => {
  const r = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']).analyze();
  return r.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical').map((v) => `${v.id}: ${v.nodes.slice(0, 3).map((n) => n.target.join(' ')).join(' | ')}`);
};

const REQ = 'Modernise claims intake for motor and home. Customers and brokers submit claims through a web portal and the mobile app. Availability must be 99.9% with an RTO of 4 hours and an RPO of 15 minutes. It handles personal data and customer financial records, and data must stay in the UK. About 300 requests per second at peak with p95 latency under 500 ms. It publishes events when a claim changes status.';

test.describe('Blueprint Intelligence Studio', () => {
  test.beforeEach(async ({ page, request }) => { await resetServerState(request); await setTheme(page, 'dark'); });

  test('from requirements to a submitted review', async ({ page }) => {
    await page.goto('/studio');
    await expect(page.getByRole('heading', { name: 'Blueprint Intelligence Studio' })).toBeVisible();

    // 1. requirements: too short is refused in the form, before any request
    const box = page.getByLabel('Business or technical requirements');
    await box.fill('too short');
    await page.getByRole('button', { name: 'Analyse and recommend' }).click();
    await expect(page.getByRole('alert')).toContainText('at least a sentence');
    await box.fill(REQ);
    await shot(page, '01-start');
    await page.getByRole('button', { name: 'Analyse and recommend' }).click();

    // 2. recommendation, with evidence and alternatives
    await expect(page.getByTestId('step-recommendation')).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText(/^Recommended:/)).toBeVisible();
    await expect(page.getByText(/Confidence \d+%/)).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Alternatives' })).toBeVisible();
    await shot(page, '02-recommendation');
    await page.getByRole('button', { name: /^Customise / }).click();

    // 3. customise: a choice changes the live diagram and the readiness figure
    await expect(page.getByTestId('step-customise')).toBeVisible();
    const chip = page.getByTestId('readiness-chip');
    await expect(chip).toBeVisible();
    const before = await chip.innerText();
    await page.getByRole('button', { name: 'Clear all' }).click();
    await expect.poll(async () => chip.innerText(), { timeout: 15_000 }).not.toBe(before);
    await page.getByRole('button', { name: 'Select all' }).click();
    await shot(page, '03-customise');

    // 4. diagram: add a component, rename it, undo
    await page.getByRole('button', { name: 'Edit the diagram' }).click();
    const canvas = page.getByTestId('architecture-canvas');
    await expect(canvas).toBeVisible();
    const nodes = canvas.locator('[data-testid^="node-"]');
    await expect(nodes.first()).toBeVisible();
    const count = await nodes.count();
    await page.getByRole('button', { name: /^Add / }).first().waitFor();
    const addBtns = page.getByRole('button', { name: /^Add / });
    await addBtns.first().click();
    await expect(nodes).toHaveCount(count + 1, { timeout: 15_000 });
    await expect(page.getByTestId('node-inspector')).toBeVisible();
    await page.getByLabel('Component name').fill('Studio test component');
    await page.getByLabel('Component name').blur();
    await expect(canvas.getByText('Studio test component')).toBeVisible({ timeout: 15_000 });
    await shot(page, '04-diagram');
    await page.getByRole('button', { name: 'Undo' }).click(); // the rename
    await expect(page.getByTestId('architecture-canvas').getByText('Studio test component')).toHaveCount(0, { timeout: 15_000 });
    await page.getByRole('button', { name: 'Undo' }).click(); // the added component
    await expect(nodes).toHaveCount(count, { timeout: 15_000 });
    await page.getByRole('button', { name: 'Redo' }).click();
    await expect(nodes).toHaveCount(count + 1, { timeout: 15_000 });
    await page.getByRole('button', { name: 'Undo' }).click();
    await expect(nodes).toHaveCount(count, { timeout: 15_000 });

    // 5. validation
    await page.getByRole('button', { name: 'See the validation' }).click();
    await expect(page.getByTestId('step-validation')).toBeVisible();
    await page.getByRole('button', { name: /Record this validation/ }).click();
    await expect(page.getByText(/^Recorded /)).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText(/not been checked against a deployed environment|Validated as declared/)).toBeVisible();
    await shot(page, '05-validation');

    // 6. gaps: accept an automatic fix and watch the open count drop
    await page.getByRole('navigation', { name: 'Studio steps' }).getByRole('button', { name: /Gaps/ }).click();
    await expect(page.getByTestId('step-gaps')).toBeVisible();
    await shot(page, '06-gaps');
    const accept = page.getByRole('button', { name: /^Accept: / }).first();
    if (await accept.isVisible().catch(() => false)) {
      const open = async () => Number(/(\d+) open gap/.exec(await page.getByText(/\d+ open gaps?/).first().innerText())?.[1] ?? 0);
      const n0 = await open();
      await accept.click();
      await expect.poll(open, { timeout: 20_000 }).toBeLessThan(n0);
    }

    // 7. export
    await page.getByRole('button', { name: 'Continue to export' }).click();
    await expect(page.getByTestId('step-export')).toBeVisible();
    await expect(page.getByText(/Target architecture/i).first()).toBeVisible({ timeout: 20_000 });
    await shot(page, '07-export-document');
    await page.getByRole('tab', { name: /Starter ZIP/ }).click();
    await expect(page.getByText(/not deployable infrastructure/)).toBeVisible();
    await shot(page, '07-export-starter');
    const [dl] = await Promise.all([page.waitForEvent('download'), page.getByRole('link', { name: /Starter \(\.zip\)/ }).click()]);
    expect(dl.suggestedFilename()).toMatch(/\.zip$/);
    await page.getByLabel('Version label (optional)').fill('after review');
    await page.getByRole('button', { name: 'Save version' }).click();
    await expect(page.getByRole('listitem').filter({ hasText: 'after review' }).first()).toBeVisible();

    // 8. governance: submit, then follow the link into the existing review page
    await page.getByRole('button', { name: 'Continue to governance' }).click();
    await expect(page.getByTestId('step-governance')).toBeVisible();
    await shot(page, '08-governance');
    const submit = page.getByRole('button', { name: 'Submit for review' });
    if (await submit.isDisabled()) test.info().annotations.push({ type: 'note', description: 'submission blocked by an open critical gap in this run' });
    else {
      await submit.click();
      const arb = page.getByRole('heading', { name: /Submitted as/ });
      await expect(arb).toBeVisible({ timeout: 20_000 });
      await shot(page, '08-submitted');
      await page.getByRole('link', { name: 'Open the review' }).click();
      await expect(page).toHaveURL(/\/reviews\/ARB-/);
      await expect(page.getByText(/ARB-\d{4}-\d{3}/).first()).toBeVisible();
    }
  });


  test('accepting a recommended fix changes the design and clears the gap', async ({ page, request }) => {
    const d = await (await request.post('/api/v1/studio/designs', { data: { text: REQ } })).json();
    // turn every control off so the standards have real, fixable findings
    const r = await request.patch(`/api/v1/studio/designs/${d.n}`, { data: { selections: { posture: [] } } });
    expect(r.ok()).toBeTruthy();
    await page.goto(`/studio?design=${d.n}&step=gaps`);
    const open = async () => Number(/(\d+) open gap/.exec(await page.getByText(/\d+ open gaps?/).first().innerText())?.[1] ?? 0);
    await expect.poll(open, { timeout: 15_000 }).toBeGreaterThan(0);
    const n0 = await open();
    const accept = page.getByRole('button', { name: /^Accept: / }).first();
    await expect(accept).toBeVisible();
    await accept.click();
    await expect.poll(open, { timeout: 20_000 }).toBeLessThan(n0);
    await expect(page.getByRole('heading', { name: 'Resolved by your decisions' })).toBeVisible();
    await shot(page, '09-gaps-after-accept');
    // accepting a risk needs a justification
    const risk = page.getByRole('button', { name: 'Accept the risk' }).first();
    await risk.click();
    const record = page.getByRole('button', { name: 'Record risk acceptance' });
    await expect(record).toBeDisabled();
    await page.getByLabel('Justification').first().fill('Accepted until the platform team delivers private networking in Q2.');
    await expect(record).toBeEnabled();
  });

  for (const theme of ['dark', 'light'] as const) {
    test(`the studio steps have no serious accessibility violations (${theme})`, async ({ page, request }) => {
      await setTheme(page, theme);
      await page.goto('/studio');
      await page.waitForLoadState('networkidle');
      expect(await serious(page)).toEqual([]);
      const r = await request.post('/api/v1/studio/designs', { data: { text: REQ } });
      const d = await r.json();
      for (const step of ['recommendation', 'customise', 'diagram', 'validation', 'gaps', 'export', 'governance']) {
        await page.goto(`/studio?design=${d.n}&step=${step}`);
        await page.waitForLoadState('networkidle');
        await page.waitForTimeout(500);
        expect(await serious(page), step).toEqual([]);
      }
    });
  }

  test('a narrow screen keeps every step usable', async ({ page, request }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    const d = await (await request.post('/api/v1/studio/designs', { data: { text: REQ } })).json();
    for (const step of ['customise', 'diagram', 'gaps']) {
      await page.goto(`/studio?design=${d.n}&step=${step}`);
      await page.waitForLoadState('networkidle');
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      expect(overflow, step).toBeLessThanOrEqual(1);
      await shot(page, `m-${step}`);
    }
  });
});
