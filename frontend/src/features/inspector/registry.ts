import type { ComponentType, LazyExoticComponent } from 'react';

export interface InspectorProps {
  id: string;
}

export interface InspectorEntry {
  label: string;
  width?: number;
  Component: LazyExoticComponent<ComponentType<InspectorProps>> | ComponentType<InspectorProps>;
}

/**
 * Central registry for the reusable right-hand inspector drawer.
 * Any feature can call `openInspector({ kind, id })`; the shell renders the matching entry.
 */
const registry = new Map<string, InspectorEntry>();

export function registerInspector(kind: string, entry: InspectorEntry) {
  registry.set(kind, entry);
}

export function getInspector(kind: string): InspectorEntry | undefined {
  return registry.get(kind);
}

// Feature inspectors register themselves below (added as each module lands).
import { lazy } from 'react';

registerInspector('asset', { label: 'Asset', width: 560, Component: lazy(() => import('./AssetInspector')) });
registerInspector('finding', { label: 'Finding', width: 540, Component: lazy(() => import('./FindingInspector')) });
registerInspector('drift', { label: 'Drift item', width: 640, Component: lazy(() => import('./DriftInspector')) });
registerInspector('document', { label: 'Document', width: 620, Component: lazy(() => import('./DocumentInspector')) });
