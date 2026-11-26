import { expect, test } from '@playwright/test';
import { resetServerState, sample } from './helpers';

test.beforeEach(async ({ request }) => resetServerState(request));
test.afterEach(async ({ request }) => resetServerState(request));

test.describe('uploads', () => {
  test('a runbook PDF is read, listed, kept after a reload, and can be removed', async ({ page }) => {
    await page.goto('/documents');
    await page.getByRole('button', { name: 'Upload documents' }).click();
    await page.locator('[role=dialog] input[type=file]').setInputFiles(sample('Policy-Admin-Operations-Runbook.pdf'));
    await expect(page.getByRole('button', { name: 'Open analysis' }).first()).toBeVisible({ timeout: 30_000 });
    await page.keyboard.press('Escape');

    await page.reload();
    await page.getByPlaceholder(/search/i).first().fill('Runbook');
    const remove = page.getByRole('button', { name: 'Remove Policy-Admin-Operations-Runbook' });
    await expect(remove).toBeVisible();
    await remove.click();
    await expect(remove).toHaveCount(0);
  });

  test('the sample button loads a file served by the API', async ({ page }) => {
    await page.goto('/documents');
    await page.getByRole('button', { name: 'Upload documents' }).click();
    const row = page.getByRole('listitem').filter({ hasText: 'ADR-0052' });
    await expect(row).toBeVisible();
    await row.getByRole('button', { name: 'Use this sample' }).click();
    await expect(page.getByRole('button', { name: 'Open analysis' }).first()).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText(/\d+ assets · \d+ relations/)).toBeVisible();
  });

  test('an unsupported file type is refused with a clear message', async ({ page }) => {
    await page.goto('/documents');
    await page.getByRole('button', { name: 'Upload documents' }).click();
    await page.locator('[role=dialog] input[type=file]').setInputFiles({ name: 'tool.exe', mimeType: 'application/octet-stream', buffer: Buffer.from('MZ') });
    await expect(page.getByText(/not supported/i)).toBeVisible();
  });

  test('a CMDB export is reconciled with the estate and the report is kept', async ({ page }) => {
    await page.goto('/discovery');
    await page.getByRole('button', { name: 'Import inventory' }).click();
    await page.locator('[role=dialog] input[type=file]').setInputFiles(sample('sample-cmdb-export-2026-11.xlsx'));
    // the full report opens straight away
    const report = page.getByRole('region', { name: /Import report for sample-cmdb-export/ });
    await expect(report).toBeVisible({ timeout: 30_000 });
    await expect(report.getByText('Reconciliation summary')).toBeVisible();
    await page.keyboard.press('Escape');

    // after a reload it is a one-line banner, with the report a click away
    await page.reload();
    const banner = page.getByRole('region', { name: /Last inventory import: sample-cmdb-export/ });
    await expect(banner).toBeVisible();
    await expect(banner).toContainText('matched');
    await banner.getByRole('button', { name: 'View report' }).click();
    await expect(page.getByRole('region', { name: /Import report for sample-cmdb-export/ })).toBeVisible();
    await page.keyboard.press('Escape');
    await banner.getByRole('button', { name: 'Dismiss' }).click();
    await expect(banner).toHaveCount(0);
  });

  test('a design review of the sample is saved between sessions', async ({ page }) => {
    await page.goto('/reviews');
    await page.getByRole('button', { name: 'Review a design' }).click();
    await page.getByRole('button', { name: 'Run review' }).click({ timeout: 20_000 });
    await expect(page.getByText('Your saved reviews')).toBeVisible({ timeout: 30_000 });
    await page.reload();
    await expect(page.getByText('Your saved reviews')).toBeVisible();
  });

  test('Bicep is scored, and the fixed version scores clearly better', async ({ page }) => {
    await page.goto('/standards');
    const score = async () => Number((await page.getByRole('img', { name: /out of 100/ }).first().getAttribute('aria-label'))!.match(/(\d+) out of 100/)![1]);
    const upload = async (file: string) => {
      await page.locator('input[type=file]').first().setInputFiles(sample(file));
      await expect(page.getByText(`Loaded ${file}`)).toBeVisible({ timeout: 30_000 });
      await expect(page.getByText(/\d+ standards applied/)).toBeVisible({ timeout: 30_000 });
    };
    await upload('claims-copilot-main.bicep');
    const bad = await score();
    await upload('claims-copilot-main.fixed.bicep');
    await expect.poll(score).toBeGreaterThan(bad + 20);
    expect(bad).toBeLessThan(60);
  });
});
