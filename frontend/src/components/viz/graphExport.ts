/** Turning the on-screen graph into files: a vector SVG of the whole graph and a PNG of the current view. */

export interface ExportNode {
  id: string;
  name: string;
  type: string;
  domain?: string | null;
  degree: number;
  /** Set on a collapsed domain: the number of nodes it stands for. */
  members?: number;
  x?: number;
  y?: number;
}
export interface ExportLink {
  source: string;
  target: string;
}
export type LegendItem = readonly [label: string, colour: string, square: boolean];

export interface ExportStyle {
  fg: string;
  muted: string;
  bg: string;
  line: string;
  accent: string;
  territory: string;
  territoryLine: string;
  colorOf: (n: ExportNode) => string;
  legend: readonly LegendItem[];
  title: string;
  subtitle: string;
  hubCut: number;
  focusId?: string | null;
  highlight?: Set<string>;
}

export const radiusOf = (degree: number) => 3.2 + Math.sqrt(Math.min(degree, 60)) * 0.95;
export const bubbleRadius = (members: number) => 9 + Math.sqrt(members) * 2.6;
/** One size for a node wherever it is drawn: on screen, in the SVG and in label placement. */
export const nodeRadius = (n: { degree: number; members?: number }) => (n.members ? bubbleRadius(n.members) : radiusOf(n.degree));

const esc = (s: string) => s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&apos;' })[c]!);
const f = (n: number) => (Math.round(n * 10) / 10).toString();

export function exportFileName(ext: 'png' | 'svg' | 'csv', now = new Date()) {
  return `archiq-knowledge-graph-${now.toISOString().slice(0, 10)}.${ext}`;
}

/** A self-contained SVG of every node and link at its current position, fitted to its bounds. Opens in browsers, Figma, Illustrator and Inkscape. */
export function buildSvg(nodes: ExportNode[], links: ExportLink[], s: ExportStyle): string {
  const placed = nodes.filter((n) => n.x !== undefined && n.y !== undefined && Number.isFinite(n.x) && Number.isFinite(n.y));
  const byId = new Map(placed.map((n) => [n.id, n]));
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const n of placed) {
    const r = nodeRadius(n);
    minX = Math.min(minX, n.x! - r - 30); maxX = Math.max(maxX, n.x! + r + 30);
    minY = Math.min(minY, n.y! - r - 18); maxY = Math.max(maxY, n.y! + r + 24);
  }
  if (!placed.length) { minX = minY = 0; maxX = 400; maxY = 200; }
  const pad = 40, head = 64, foot = 44;
  const gw = Math.max(maxX - minX, 360), gh = maxY - minY;
  const W = gw + pad * 2, H = gh + pad * 2 + head + foot;
  const ox = pad - minX + (gw - (maxX - minX)) / 2, oy = pad + head - minY;
  const fs = Math.max(10, Math.min(20, gw / 110));
  const out: string[] = [];
  out.push(`<svg xmlns="http://www.w3.org/2000/svg" width="${f(W)}" height="${f(H)}" viewBox="0 0 ${f(W)} ${f(H)}" font-family="Inter, Segoe UI, Arial, sans-serif">`);
  out.push(`<title>${esc(s.title)}</title>`);
  out.push(`<rect width="100%" height="100%" fill="${s.bg}"/>`);
  out.push(`<text x="${pad}" y="${pad + 8}" font-size="20" font-weight="600" fill="${s.fg}">${esc(s.title)}</text>`);
  out.push(`<text x="${pad}" y="${pad + 30}" font-size="12" fill="${s.muted}">${esc(s.subtitle)}</text>`);
  out.push(`<g transform="translate(${f(ox)} ${f(oy)})">`);

  // domain territories
  const byDomain = new Map<string, ExportNode[]>();
  for (const n of placed) if (n.domain) (byDomain.get(n.domain) ?? byDomain.set(n.domain, []).get(n.domain)!).push(n);
  if (!s.focusId) {
    for (const [d, ns] of byDomain) {
      if (ns.length < 3) continue;
      const cx = ns.reduce((a, n) => a + n.x!, 0) / ns.length, cy = ns.reduce((a, n) => a + n.y!, 0) / ns.length;
      const r = Math.max(...ns.map((n) => Math.hypot(n.x! - cx, n.y! - cy) + nodeRadius(n))) + 14;
      out.push(`<circle cx="${f(cx)}" cy="${f(cy)}" r="${f(r)}" fill="${s.territory}" stroke="${s.territoryLine}"/>`);
      out.push(`<text x="${f(cx)}" y="${f(cy - r - 6)}" text-anchor="middle" font-size="${f(fs * 0.9)}" font-weight="600" letter-spacing="0.06em" fill="${s.muted}">${esc(d.toUpperCase())}</text>`);
    }
  }

  // links, gently curved like the on-screen view
  out.push(`<g fill="none" stroke="${s.line}" stroke-width="0.7">`);
  for (const l of links) {
    const a = byId.get(l.source), b = byId.get(l.target);
    if (!a || !b) continue;
    const mx = (a.x! + b.x!) / 2, my = (a.y! + b.y!) / 2;
    const dx = b.x! - a.x!, dy = b.y! - a.y!;
    out.push(`<path d="M${f(a.x!)} ${f(a.y!)}Q${f(mx + dy * 0.12)} ${f(my - dx * 0.12)} ${f(b.x!)} ${f(b.y!)}"/>`);
  }
  out.push('</g>');

  // nodes, biggest last so hubs sit on top
  const marked = (n: ExportNode) => n.id === s.focusId || (s.highlight?.has(n.id) ?? false);
  for (const n of [...placed].sort((a, b) => a.degree - b.degree)) {
    const r = nodeRadius(n);
    if (marked(n)) out.push(`<circle cx="${f(n.x!)}" cy="${f(n.y!)}" r="${f(r + 4)}" fill="${s.accent}" fill-opacity="0.25"/>`);
    const fill = s.colorOf(n);
    if (n.members) {
      out.push(`<circle cx="${f(n.x!)}" cy="${f(n.y!)}" r="${f(r)}" fill="${fill}" fill-opacity="0.18" stroke="${fill}" stroke-width="1.6"><title>${esc(n.name)} (${n.members} nodes)</title></circle>`);
      out.push(`<text x="${f(n.x!)}" y="${f(n.y! - 1)}" text-anchor="middle" font-size="${f(fs)}" font-weight="600" fill="${s.fg}">${esc(n.name)}</text>`);
      out.push(`<text x="${f(n.x!)}" y="${f(n.y! + fs)}" text-anchor="middle" font-size="${f(fs * 0.85)}" fill="${s.muted}">${n.members} nodes</text>`);
      continue;
    }
    out.push(n.type === 'Data'
      ? `<rect x="${f(n.x! - r * 0.9)}" y="${f(n.y! - r * 0.9)}" width="${f(r * 1.8)}" height="${f(r * 1.8)}" rx="${f(r * 0.3)}" fill="${fill}" stroke="${s.bg}" stroke-width="1.2"><title>${esc(n.name)}</title></rect>`
      : `<circle cx="${f(n.x!)}" cy="${f(n.y!)}" r="${f(r)}" fill="${fill}" stroke="${s.bg}" stroke-width="1.2"><title>${esc(n.name)}</title></circle>`);
  }

  // labels: hubs and marked nodes, skipping any that would sit on a label already placed
  const boxes: { x: number; y: number; w: number; h: number }[] = [];
  const labelled = placed.filter((n) => !n.members && ((n.degree >= s.hubCut && s.hubCut > 0) || marked(n))).sort((a, b) => Number(marked(b)) - Number(marked(a)) || b.degree - a.degree);
  for (const n of labelled) {
    const w = n.name.length * fs * 0.56 + 6, h = fs + 4;
    const box = { x: n.x! - w / 2, y: n.y! + nodeRadius(n) + 2, w, h };
    if (!marked(n) && boxes.some((b) => box.x < b.x + b.w && box.x + box.w > b.x && box.y < b.y + b.h && box.y + box.h > b.y)) continue;
    boxes.push(box);
    out.push(`<rect x="${f(box.x)}" y="${f(box.y)}" width="${f(w)}" height="${f(h)}" rx="2" fill="${s.bg}" fill-opacity="0.85"/>`);
    out.push(`<text x="${f(n.x!)}" y="${f(box.y + fs)}" text-anchor="middle" font-size="${f(fs)}" font-weight="600" fill="${s.fg}">${esc(n.name)}</text>`);
  }
  out.push('</g>');

  // legend
  let lx = pad;
  const ly = H - foot / 2 - 4;
  for (const [label, colour, square] of s.legend) {
    out.push(square
      ? `<rect x="${f(lx)}" y="${f(ly - 5)}" width="10" height="10" rx="2" fill="${colour}"/>`
      : `<circle cx="${f(lx + 5)}" cy="${f(ly)}" r="5" fill="${colour}"/>`);
    out.push(`<text x="${f(lx + 16)}" y="${f(ly + 4)}" font-size="12" fill="${s.muted}">${esc(label)}</text>`);
    lx += 16 + label.length * 6.6 + 18;
  }
  out.push('</svg>');
  return out.join('\n');
}

/** The visible canvas on a solid background with a title strip and legend, so the image stands on its own in a deck or document. */
export function composePng(src: HTMLCanvasElement, s: Pick<ExportStyle, 'bg' | 'fg' | 'muted' | 'title' | 'subtitle' | 'legend'>): Promise<Blob> {
  const dpr = Math.max(1, src.clientWidth ? src.width / src.clientWidth : 1);
  const head = Math.round(58 * dpr), foot = Math.round(36 * dpr), pad = Math.round(20 * dpr);
  const out = document.createElement('canvas');
  out.width = src.width;
  out.height = src.height + head + foot;
  const ctx = out.getContext('2d');
  if (!ctx) return Promise.reject(new Error('Canvas is not available in this browser'));
  ctx.fillStyle = s.bg;
  ctx.fillRect(0, 0, out.width, out.height);
  ctx.drawImage(src, 0, head);
  ctx.textBaseline = 'alphabetic';
  ctx.fillStyle = s.fg;
  ctx.font = `600 ${18 * dpr}px Inter, Segoe UI, Arial, sans-serif`;
  ctx.fillText(s.title, pad, 28 * dpr);
  ctx.fillStyle = s.muted;
  ctx.font = `${11.5 * dpr}px Inter, Segoe UI, Arial, sans-serif`;
  ctx.fillText(s.subtitle, pad, 46 * dpr);
  let x = pad;
  const y = head + src.height + foot / 2 + 4 * dpr;
  ctx.font = `${11.5 * dpr}px Inter, Segoe UI, Arial, sans-serif`;
  for (const [label, colour, square] of s.legend) {
    ctx.fillStyle = colour;
    ctx.beginPath();
    if (square) ctx.roundRect(x, y - 9 * dpr, 9 * dpr, 9 * dpr, 2 * dpr);
    else ctx.arc(x + 4.5 * dpr, y - 4.5 * dpr, 4.5 * dpr, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = s.muted;
    ctx.fillText(label, x + 14 * dpr, y);
    x += 14 * dpr + ctx.measureText(label).width + 16 * dpr;
  }
  return new Promise((resolve, reject) => out.toBlob((b) => (b ? resolve(b) : reject(new Error('Could not encode the image'))), 'image/png'));
}

export function downloadBlob(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}
