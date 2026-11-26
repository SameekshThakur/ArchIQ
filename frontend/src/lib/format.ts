export const fmtNum = (n: number) => new Intl.NumberFormat('en-US').format(n);
export const fmtMoneyK = (k: number) => (k >= 1000 ? `$${(k / 1000).toFixed(1)}M` : `$${Math.round(k)}k`);
export const titleCase = (s: string) => s.replace(/[_-]/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
export const fmtDate = (iso: string) => new Date(iso).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
export const sevRank: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3, info: 4 };

export function download(filename: string, content: string | Blob, type = 'text/plain') {
  const blob = content instanceof Blob ? content : new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
