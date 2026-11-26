import AxeBuilder from '@axe-core/playwright';
import { expect, test, type APIRequestContext, type Page } from '@playwright/test';
import { setTheme } from './helpers';

const API = 'http://127.0.0.1:8100/api/v1';

async function clearConnections(request: APIRequestContext) {
  const r = await request.get(`${API}/connections`);
  for (const c of (await r.json()).items) if (c.configured) await request.delete(`${API}/connections/${c.id}`);
}

async function connectDemo(page: Page, name: string) {
  await page.getByRole('listitem', { name }).getByRole('button', { name: /Connect|Settings/ }).click();
  const drawer = page.getByRole('dialog');
  await drawer.getByRole('radio', { name: 'Demo data' }).click();
  await drawer.getByRole('button', { name: 'Save and sync' }).click();
  await expect(drawer.getByRole('heading', { name: 'Last sync' })).toBeVisible({ timeout: 20_000 });
  return drawer;
}

test.describe('connections', () => {
  test.beforeEach(async ({ request }) => { await clearConnections(request); });

  test('is reachable before any analysis exists and lists six platforms', async ({ page, request }) => {
    await request.delete(`${API}/workspace`);
    await page.goto('/connections');
    await expect(page.getByRole('heading', { name: 'Connections', level: 1 })).toBeVisible();
    await expect(page.getByRole('list', { name: 'Platforms' }).locator(':scope > [role=listitem]')).toHaveCount(6);
    await expect(page.getByRole('listitem', { name: 'ServiceNow CMDB' }).getByText('Not connected')).toBeVisible();
  });

  test('a demo ServiceNow sync reconciles the CMDB and links to Discovery', async ({ page }) => {
    await page.goto('/connections');
    const drawer = await connectDemo(page, 'ServiceNow CMDB');
    await expect(drawer.getByText('Reconciled against the estate')).toBeVisible();
    await expect(drawer.getByText('Not in estate')).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.getByRole('listitem', { name: 'ServiceNow CMDB' }).getByText('Demo mode')).toBeVisible();
  });

  test('Azure and GitHub together show live drift', async ({ page }) => {
    await page.goto('/connections');
    await connectDemo(page, 'Azure Resource Graph');
    await page.keyboard.press('Escape');
    await connectDemo(page, 'GitHub');
    await page.keyboard.press('Escape');
    const table = page.getByRole('table', { name: /differ from the approved code/ });
    await expect(table).toBeVisible();
    await expect(table.getByText('public network access').first()).toBeVisible();
  });

  test('live mode asks for the required fields and never shows a saved secret', async ({ page }) => {
    await page.goto('/connections');
    await page.getByRole('listitem', { name: 'Jira' }).getByRole('button', { name: 'Connect' }).click();
    const drawer = page.getByRole('dialog');
    await expect(drawer.getByText(/Still needed: Site URL, API token, Project keys/)).toBeVisible();
    await expect(drawer.getByRole('button', { name: 'Test connection' })).toBeDisabled();
    await drawer.getByLabel('Site URL').fill('https://example.atlassian.net');
    await drawer.getByLabel('API token').fill('super-secret-token');
    await drawer.getByLabel('Project keys').fill('ARCH');
    await drawer.getByRole('button', { name: 'Save', exact: true }).click();
    await expect(drawer.getByLabel('API token')).toHaveValue('');
    await expect(drawer.getByLabel('API token')).toHaveAttribute('placeholder', /Saved/);
    expect(await page.content()).not.toContain('super-secret-token');
  });

  for (const theme of ['dark', 'light'] as const) {
    test(`has no serious accessibility violations, ${theme} theme`, async ({ page }) => {
      await setTheme(page, theme);
      await page.goto('/connections');
      await connectDemo(page, 'Confluence');
      const r = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
      expect(r.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical').map((v) => `${v.id}: ${v.nodes.slice(0, 3).map((n) => n.target.join(' ') + ' ' + (n.any[0]?.message ?? '')).join(' | ')}`)).toEqual([]);
    });
  }
});
