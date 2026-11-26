import '@testing-library/jest-dom/vitest';

class RO {
  observe() {}
  unobserve() {}
  disconnect() {}
}
// jsdom lacks ResizeObserver, which Radix and charts expect
(globalThis as unknown as { ResizeObserver: typeof RO }).ResizeObserver = RO;
if (!window.matchMedia) {
  window.matchMedia = (q: string) =>
    ({ matches: false, media: q, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {}, onchange: null, dispatchEvent: () => false }) as MediaQueryList;
}
