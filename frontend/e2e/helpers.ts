import { expect, type APIRequestContext, type Locator, type Page } from '@playwright/test';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

export const SAMPLES = join(fileURLToPath(new URL('.', import.meta.url)), '..', '..', 'sample-files');
export const sample = (name: string) => join(SAMPLES, name);

export async function setTheme(page: Page, theme: 'dark' | 'light') {
  await page.addInitScript((t) => localStorage.setItem('archiq-theme', t), theme);
}

/** Opens the graph and waits until the layout has finished moving, so pictures taken afterwards are still. */
export async function openGraph(page: Page): Promise<Locator> {
  await page.goto('/graph');
  const graph = page.getByTestId('force-graph');
  await expect(graph).toHaveAttribute('data-settled', 'true', { timeout: 30_000 });
  return graph;
}

export const canvas = (page: Page) => page.getByTestId('force-graph').locator('canvas').first();
export const zoomOf = async (page: Page) => Number((await page.getByTestId('force-graph').getAttribute('data-zoom')) ?? '1');
export const nodeCount = async (page: Page) => Number(await page.getByTestId('force-graph').getAttribute('data-nodes'));

/** Jumps to a node with Find in view. The node ends up at the middle of the canvas, which is where tests then point the mouse. */
export async function zoomToNode(page: Page, name: string) {
  const box = page.getByRole('combobox', { name: 'Find a node in this view' });
  await box.fill(name);
  await page.getByRole('option').first().click();
  await expect.poll(() => zoomOf(page), { timeout: 5000 }).toBeGreaterThan(3);
  await page.waitForTimeout(800); // let the camera tween finish
}

export async function canvasCentre(page: Page) {
  const b = await canvas(page).boundingBox();
  if (!b) throw new Error('graph canvas is not visible');
  return { x: b.x + b.width / 2, y: b.y + b.height / 2 };
}

/** The canvas as a PNG, for "did anything move" comparisons. */
export const picture = (page: Page) => canvas(page).screenshot({ animations: 'disabled' });

/**
 * Removes whatever a test saved, so specs stay independent of each other and of the developer's own data.
 * The workspace is left with the Sample estate loaded (every page has data to show); pass 'empty' for the first-visit state.
 */
export async function resetServerState(request: APIRequestContext, workspace: 'demo' | 'empty' = 'demo') {
  const views = await (await request.get('/api/v1/graph/views')).json();
  for (const v of views.items) await request.delete(`/api/v1/graph/views/${v.id}`);
  const reviews = await (await request.get('/api/v1/reviews/adhoc')).json();
  for (const r of reviews.items ?? []) await request.delete(`/api/v1/reviews/adhoc/${r.id}`);
  const studio = await (await request.get('/api/v1/studio/designs')).json();
  for (const d of studio.items ?? []) await request.delete(`/api/v1/studio/designs/${d.n}`); // a submitted design is part of the review record and stays
  const imports = await (await request.get('/api/v1/discovery/imports')).json();
  for (const i of imports.items ?? []) await request.delete(`/api/v1/discovery/imports/${i.id}`);
  const docs = await (await request.get('/api/v1/documents?page_size=200')).json();
  for (const d of docs.items) if (d.uploaded) await request.delete(`/api/v1/documents/${d.id}`);
  if (workspace === 'demo') await request.post('/api/v1/workspace/demo');
  else await request.delete('/api/v1/workspace');
}
