import AxeBuilder from '@axe-core/playwright';
import { expect, test, type APIRequestContext, type Page } from '@playwright/test';
import { resetServerState, setTheme } from './helpers';

const API = 'http://127.0.0.1:8100/api/v1';
async function clearConnections(request: APIRequestContext) {
  const r = await request.get(`${API}/connections`);
  for (const c of (await r.json()).items) if (c.configured) await request.delete(`${API}/connections/${c.id}`);
}

test.beforeEach(async ({ request }) => resetServerState(request, 'empty'));
test.afterEach(async ({ request }) => resetServerState(request));

const pickDomain = async (page: Page, name: RegExp) => {
  await page.getByRole('combobox', { name: 'Business domain' }).click();
  await page.getByRole('option', { name }).click();
};
const intent = (page: Page, name: RegExp) => page.getByRole('radio', { name });
/** People click the card, not the visually hidden radio inside it. */
const choose = async (page: Page, name: RegExp) => { await page.locator('label').filter({ has: intent(page, name) }).click(); await expect(intent(page, name)).toBeChecked(); };
const steps = (page: Page) => page.getByRole('list', { name: 'Analysis steps' }).getByRole('listitem');

async function runWithSamples(page: Page) {
  await page.goto('/start');
  await choose(page, /Get a design ready for architecture review/);
  await page.getByRole('button', { name: 'Use the sample files' }).click();
  await expect(page.getByRole('list', { name: 'Files to analyse' }).getByRole('listitem')).toHaveCount(6);
  await pickDomain(page, /^Claims/);
  await page.getByRole('button', { name: 'Start the analysis' }).click();
  await expect(page.getByTestId('result-headline')).toBeVisible({ timeout: 60_000 });
}

test.describe('first visit and empty pages', () => {
  test('the app opens on the start page, not on a dashboard of data nobody asked for', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveURL(/\/start$/);
    await expect(page.getByRole('heading', { name: 'New analysis', level: 1 })).toBeVisible();
    await expect(page.getByRole('radiogroup', { name: 'What you are looking for' })).toBeVisible();
    await expect(page.getByText('Add your supporting documents')).toBeVisible();
    await expect(page.getByText('Which business domain?')).toBeVisible();
  });

  test('every other page says where to begin instead of showing the estate', async ({ page }) => {
    for (const path of ['/graph', '/standards', '/reviews', '/discovery', '/documents', '/assessment', '/copilot']) {
      await page.goto(path);
      await expect(page.getByTestId('workspace-empty'), path).toBeVisible();
      await expect(page.getByRole('link', { name: 'Start an analysis' })).toBeVisible();
    }
    await expect(page.getByTestId('force-graph')).toHaveCount(0);
    // and no sidebar counts about an estate that is not there
    await expect(page.getByRole('navigation', { name: 'Modules' }).locator('.num')).toHaveCount(0);
  });

  test('the Start button explains what is still missing', async ({ page }) => {
    await page.goto('/start');
    const start = page.getByRole('button', { name: 'Start the analysis' });
    await expect(start).toBeDisabled();
    await expect(page.getByText('Say what you are looking for')).toBeVisible();
    await choose(page, /Find risks and technical debt/);
    await expect(page.getByText('Choose a business domain')).toBeVisible();
    await expect(start).toBeDisabled();
    await pickDomain(page, /^Billing/);
    await expect(start).toBeEnabled();
  });

  test('the intent choices work from the keyboard', async ({ page }) => {
    await page.goto('/start');
    const first = page.getByRole('radio').first();
    await first.focus();
    await page.keyboard.press('Space');
    await expect(first).toBeChecked();
    await page.keyboard.press('ArrowDown');
    await expect(page.getByRole('radio').nth(1)).toBeChecked();
  });

  test('typing a goal is enough on its own', async ({ page }) => {
    await page.goto('/start');
    await page.getByRole('textbox', { name: /In your own words/ }).fill('which systems are single points of failure?');
    await pickDomain(page, /^Claims/);
    await page.getByRole('button', { name: 'Start the analysis' }).click();
    await expect(page.getByTestId('result-headline')).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText(/Find risks and technical debt/).first()).toBeVisible();
  });
});

test.describe('the whole flow', () => {
  test('sample files in, every step runs, and the other pages now hold the results', async ({ page }) => {
    await runWithSamples(page);
    await expect(steps(page)).toHaveCount(8);
    await expect(steps(page).first()).toHaveAttribute('data-status', 'skipped'); // no tools were chosen
    for (const li of (await steps(page).all()).slice(1)) await expect(li).toHaveAttribute('data-status', 'done');
    await expect(page.getByTestId('result-headline')).toContainText(/designs? reviewed/);
    for (const id of ['documents', 'inventory', 'standards', 'reviews', 'estate']) await expect(page.getByTestId(`result-${id}`)).toBeVisible();
    await expect(page.getByTestId('result-estate')).toContainText('12'); // Claims applications

    // the documents really are in Document intelligence
    await page.getByTestId('result-documents').getByRole('link', { name: /Open/ }).click();
    await expect(page).toHaveURL(/\/documents$/);
    await page.getByPlaceholder(/search/i).first().fill('Modernization');
    await expect(page.getByRole('button', { name: /^Remove Claims Intake Modernization HLD/ })).toBeVisible();
    // and the reviews are saved in the Review agent
    await page.goto('/reviews');
    await expect(page.getByText(/claims-copilot-main/).first()).toBeVisible();
    // the overview works now too
    await page.goto('/');
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByTestId('workspace-empty')).toHaveCount(0);
  });

  test('the results can be downloaded as a printable report and as Markdown', async ({ page }) => {
    await runWithSamples(page);
    const { readFile } = await import('node:fs/promises');
    const [html] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: 'Download report' }).click()]);
    expect(html.suggestedFilename()).toMatch(/^archiq-claims-analysis-\d{4}-\d{2}-\d{2}\.html$/);
    const h = await readFile((await html.path())!, 'utf8');
    expect(h).toContain('ArchIQ analysis: Claims');
    expect(h).toMatch(/Not ready|Conditional|Ready/);
    expect(h).toContain('claims-copilot-main.tf');
    const [md] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: 'Markdown' }).click()]);
    const m = await readFile((await md.path())!, 'utf8');
    expect(m).toMatch(/^# ArchIQ analysis: Claims/);
    expect(m).toContain('## Standards');
  });

  test('a design that passes review ends in the Ready state', async ({ page }) => {
    await page.goto('/start');
    await page.getByRole('button', { name: 'Try a design that passes review' }).click();
    await expect(page.getByRole('list', { name: 'Files to analyse' }).getByText('agent-portal-sso-design.json')).toBeVisible();
    await expect(page.getByText('Customer & Distribution').first()).toBeVisible();
    await page.getByRole('button', { name: 'Start the analysis' }).click();
    await expect(page.getByTestId('result-headline')).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText('Ready', { exact: true })).toBeVisible();
    await expect(page.getByText('Not ready', { exact: true })).toHaveCount(0);
  });

  test('the progress is visible while it runs and survives a reload', async ({ page }) => {
    await page.goto('/start');
    await choose(page, /Understand what we have/);
    await pickDomain(page, /^Claims/);
    await page.getByRole('button', { name: 'Start the analysis' }).click();
    await expect(page.getByRole('heading', { name: /Running your analysis|Your analysis is ready/ })).toBeVisible();
    await page.reload();
    await expect(page.getByRole('heading', { name: /Running your analysis|Your analysis is ready/ })).toBeVisible();
    await expect(page.getByTestId('result-headline')).toBeVisible({ timeout: 30_000 });
  });

  test('the estate section opens the graph already narrowed to the domain', async ({ page }) => {
    await runWithSamples(page);
    await page.getByTestId('result-estate').getByRole('link', { name: /Open/ }).click();
    await expect(page).toHaveURL(/\/graph\?domain=Claims/);
    await expect(page.getByTestId('force-graph')).toHaveAttribute('data-settled', 'true', { timeout: 30_000 });
    await expect(page.getByRole('button', { name: /^Domains/ })).toContainText('1');
    expect(Number(await page.getByTestId('force-graph').getAttribute('data-nodes'))).toBeLessThan(60);
  });

  test('a new domain is accepted, and the results say it has no estate behind it', async ({ page }) => {
    await page.goto('/start');
    await choose(page, /Understand what we have/);
    await pickDomain(page, /Add a new domain/);
    await page.getByRole('textbox', { name: /New domain name/ }).fill('Treasury');
    await page.getByRole('button', { name: 'Start the analysis' }).click();
    await expect(page.getByTestId('result-headline')).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText(/is a new domain/)).toBeVisible();
    await expect(page.getByText(/No files or connected tools were added/)).toBeVisible();
  });

  test('Start over empties the app again and removes what the run added', async ({ page, request }) => {
    await runWithSamples(page);
    expect((await (await request.get('/api/v1/reviews/adhoc')).json()).total).toBeGreaterThan(0);
    await page.getByRole('button', { name: 'Start over' }).click();
    await expect(page.getByRole('heading', { name: 'New analysis', level: 1 })).toBeVisible();
    expect((await (await request.get('/api/v1/reviews/adhoc')).json()).total).toBe(0);
    await page.goto('/standards');
    await expect(page.getByTestId('workspace-empty')).toBeVisible();
  });

  test('files can be removed before starting', async ({ page }) => {
    await page.goto('/start');
    await page.getByRole('button', { name: 'Use the sample files' }).click();
    const list = page.getByRole('list', { name: 'Files to analyse' });
    await expect(list.getByRole('listitem')).toHaveCount(6);
    await page.getByRole('button', { name: 'Remove claims-copilot-main.tf' }).click();
    await expect(list.getByRole('listitem')).toHaveCount(5);
  });

  test('uploading a file from disk works', async ({ page }) => {
    await page.goto('/start');
    await page.locator('input[type=file]').setInputFiles(`${process.cwd()}/../sample-files/claims-notifications-design.md`);
    await expect(page.getByRole('list', { name: 'Files to analyse' }).getByText('claims-notifications-design.md')).toBeVisible();
  });
});

test.describe('the demo shortcut', () => {
  test('loads the sample estate in one click', async ({ page }) => {
    await page.goto('/start');
    await page.getByRole('button', { name: 'Explore the sample estate instead' }).click();
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByTestId('demo-badge')).toHaveText('Demo data');
    await expect(page.locator('body')).not.toContainText(/northwind/i); // the interface names no company
    await page.goto('/graph');
    await expect(page.getByTestId('force-graph')).toHaveAttribute('data-settled', 'true', { timeout: 30_000 });
    expect(Number(await page.getByTestId('force-graph').getAttribute('data-nodes'))).toBeGreaterThan(50);
    await page.goto('/start');
    await expect(page.getByRole('heading', { name: 'Sample estate is loaded' })).toBeVisible();
    await page.getByRole('button', { name: 'Start a new analysis' }).click();
    await expect(page.getByRole('radiogroup', { name: 'What you are looking for' })).toBeVisible();
    await expect(page.getByTestId('demo-badge')).toHaveCount(0); // not shown once the sample data is gone
  });
});

for (const theme of ['dark', 'light'] as const) {
  test.describe(`accessibility of the guided start, ${theme} theme`, () => {
    test.beforeEach(async ({ page }) => setTheme(page, theme));
    const violations = async (page: Page) => (await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']).analyze()).violations
      .filter((v) => v.impact === 'serious' || v.impact === 'critical').map((v) => `${v.id}: ${v.nodes.slice(0, 3).map((n) => n.target.join(' ')).join(' | ')}`);

    test('the wizard, the new-domain field and the empty-state page', async ({ page }) => {
      await page.goto('/start');
      await page.getByRole('button', { name: 'Use the sample files' }).click();
      await expect(page.getByRole('list', { name: 'Files to analyse' })).toBeVisible();
      await pickDomain(page, /Add a new domain/);
      await page.waitForTimeout(300);
      expect(await violations(page)).toEqual([]);
      await page.goto('/graph');
      await expect(page.getByTestId('workspace-empty')).toBeVisible();
      expect(await violations(page)).toEqual([]);
    });

    test('the results page', async ({ page }) => {
      await runWithSamples(page);
      await page.waitForTimeout(300);
      expect(await violations(page)).toEqual([]);
    });
  });
}


test.describe('connected tools in a new analysis', () => {
  test.beforeEach(async ({ request }) => { await clearConnections(request); });
  test.afterEach(async ({ request }) => { await clearConnections(request); });

  test('tools are set up and ticked on the start page, and the run reads them with no files', async ({ page }) => {
    await page.goto('/start');
    await choose(page, /Understand what we have/);
    const tools = page.getByRole('list', { name: 'Tools to read' });
    await expect(tools.getByRole('listitem')).toHaveCount(6);
    await expect(tools.getByRole('checkbox')).toHaveCount(0); // nothing is set up yet
    await page.getByRole('button', { name: 'Set up the rest as demo data' }).click();
    await expect(tools.getByRole('checkbox')).toHaveCount(6);
    for (const cb of await tools.getByRole('checkbox').all()) await expect(cb).toBeChecked();
    await expect(page.getByText('6 of 6 set-up tools will be read')).toBeVisible();
    await pickDomain(page, /^Claims/);
    await expect(page.getByText('No files · 6 tools · Claims')).toBeVisible();
    await page.getByRole('button', { name: 'Start the analysis' }).click();
    await expect(page.getByTestId('result-headline')).toBeVisible({ timeout: 60_000 });
    await expect(steps(page)).toHaveCount(8);
    await expect(steps(page).first()).toHaveAttribute('data-status', 'done');
    await expect(steps(page).first()).toContainText('ServiceNow CMDB');
    for (const id of ['sources', 'work', 'inventory', 'documents', 'standards', 'estate']) await expect(page.getByTestId(`result-${id}`)).toBeVisible();
    // the pages that were empty now show what the tools brought
    await page.goto('/discovery');
    await expect(page.getByTestId('workspace-empty')).toHaveCount(0);
    await expect(page.getByRole('region', { name: /Last inventory import: ServiceNow/ })).toBeVisible();
  });

  test('one tool can be connected from the drawer without losing what was typed', async ({ page }) => {
    await page.goto('/start');
    await choose(page, /Find risks and technical debt/);
    await page.getByRole('button', { name: 'Connect Jira' }).click();
    const drawer = page.getByRole('dialog');
    await drawer.getByRole('radio', { name: 'Demo data' }).click();
    await expect(drawer.getByRole('button', { name: 'Save and sync' })).toHaveCount(0); // the analysis reads it itself
    await drawer.getByRole('button', { name: 'Save and use in this analysis' }).click();
    await expect(page.getByRole('list', { name: 'Tools to read' }).getByRole('checkbox', { name: 'Jira' })).toBeChecked();
    await expect(intent(page, /Find risks and technical debt/)).toBeChecked();
    await pickDomain(page, /^Claims/);
    await page.getByRole('button', { name: 'Start the analysis' }).click();
    await expect(page.getByTestId('result-headline')).toBeVisible({ timeout: 60_000 });
    await expect(page.getByTestId('result-work')).toContainText('Open items');
  });

  test('the Connections page points people to a new analysis', async ({ page }) => {
    await page.goto('/connections');
    await page.getByTestId('connections-hint').getByRole('link', { name: 'a new analysis' }).click();
    await expect(page).toHaveURL(/\/start$/);
  });

  for (const theme of ['dark', 'light'] as const) {
    test(`the start page with tools has no accessibility violations (${theme})`, async ({ page, request }) => {
      await setTheme(page, theme);
      await request.put(`${API}/connections/jira`, { data: { mode: 'demo' } });
      await page.goto('/start');
      await expect(page.getByRole('list', { name: 'Tools to read' })).toBeVisible();
      const r = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa']).analyze();
      expect(r.violations.map((v) => `${v.id}: ${v.nodes[0]?.html}`)).toEqual([]);
    });
  }
});
