import { createBrowserRouter } from 'react-router-dom';
import { RouteError } from './ErrorBoundary';
import { Shell } from './Shell';

/**
 * Data router with lazily loaded routes. Each module is its own chunk so ECharts,
 * Mermaid and the graph libraries only load when a page that needs them is opened.
 */
export const router = createBrowserRouter([
  {
    path: '/',
    element: <Shell />,
    errorElement: <RouteError />,
    children: [
      { path: 'connections', lazy: () => import('@/features/connections/ConnectionsPage').then((m) => ({ Component: m.default })) },
      { path: 'start', lazy: () => import('@/features/start/StartPage').then((m) => ({ Component: m.default })) },
      { index: true, lazy: () => import('@/features/overview/OverviewPage').then((m) => ({ Component: m.default })) },
      { path: 'discovery', lazy: () => import('@/features/discovery/DiscoveryPage').then((m) => ({ Component: m.default })) },
      { path: 'graph', lazy: () => import('@/features/graph/GraphPage').then((m) => ({ Component: m.default })) },
      { path: 'documents', lazy: () => import('@/features/documents/DocumentsPage').then((m) => ({ Component: m.default })) },
      { path: 'assessment', lazy: () => import('@/features/assessment/AssessmentPage').then((m) => ({ Component: m.default })) },
      { path: 'debt-radar', lazy: () => import('@/features/debt/DebtPage').then((m) => ({ Component: m.default })) },
      { path: 'impact', lazy: () => import('@/features/impact/ImpactPage').then((m) => ({ Component: m.default })) },
      { path: 'drift', lazy: () => import('@/features/drift/DriftPage').then((m) => ({ Component: m.default })) },
      { path: 'copilot', lazy: () => import('@/features/copilot/CopilotPage').then((m) => ({ Component: m.default })) },
      { path: 'target-architecture', lazy: () => import('@/features/target/TargetPage').then((m) => ({ Component: m.default })) },
      { path: 'decisions', lazy: () => import('@/features/decisions/DecisionsPage').then((m) => ({ Component: m.default })) },
      { path: 'standards', lazy: () => import('@/features/standards/StandardsPage').then((m) => ({ Component: m.default })) },
      { path: 'reviews', lazy: () => import('@/features/reviews/ReviewsPage').then((m) => ({ Component: m.default })) },
      { path: 'reviews/:id', lazy: () => import('@/features/reviews/ReviewPage').then((m) => ({ Component: m.default })) },
      { path: 'studio', lazy: () => import('@/features/studio/StudioPage').then((m) => ({ Component: m.default })) },
      { path: 'blueprints', lazy: () => import('@/features/blueprints/BlueprintsPage').then((m) => ({ Component: m.default })) },
      { path: 'modernization', lazy: () => import('@/features/modernization/ModernizationPage').then((m) => ({ Component: m.default })) },
      { path: 'codegen', lazy: () => import('@/features/codegen/CodegenPage').then((m) => ({ Component: m.default })) },
      { path: '_design', lazy: () => import('@/features/design/DesignPage').then((m) => ({ Component: m.default })) },
      { path: '*', lazy: () => import('./NotFound').then((m) => ({ Component: m.default })) },
    ],
  },
]);
