import { lazy, Suspense, useEffect } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { WifiOff } from 'lucide-react';
import { Toaster } from '@/components/ui/Overlay';
import { SkeletonBlock, SkeletonTile } from '@/components/ui/Panel';
import { useUI } from '@/store/ui';
import { AppCommandPalette } from './AppCommandPalette';
import { ErrorBoundary } from './ErrorBoundary';
import { InspectorHost } from './InspectorHost';
import { ShortcutsModal } from './ShortcutsModal';
import { Sidebar } from './Sidebar';
import { Topbar } from './Topbar';
import { WorkspaceGate } from './WorkspaceGate';
import { useShortcuts } from './useShortcuts';

const CopilotDrawer = lazy(() => import('@/features/copilot/CopilotDrawer'));

function PageFallback() {
  return (
    <div className="mx-auto max-w-[1480px] px-6 pt-6" role="status" aria-label="Loading page">
      <div className="skeleton mb-2 h-6 w-64" />
      <div className="skeleton mb-12 h-3 w-96" /> {/* the real page header is taller; matching it keeps the content from jumping when the page loads */}
      <div className="grid grid-cols-5 gap-3">
        {Array.from({ length: 5 }).map((_, i) => (
          <SkeletonTile key={i} />
        ))}
      </div>
      <SkeletonBlock className="mt-4 h-72" />
    </div>
  );
}

function ApiBanner() {
  const down = useUI((s) => s.apiDown);
  if (!down) return null;
  return (
    <div role="alert" className="flex items-center gap-2 border-b border-high/30 bg-high/10 px-4 py-1.5 text-xs text-high">
      <WifiOff className="h-3.5 w-3.5" aria-hidden />
      Can&apos;t reach the ArchIQ API on port 8000. Start it with <code className="font-mono">make dev</code> (or <code className="font-mono">dev.bat</code> on Windows); this page will recover automatically.
    </div>
  );
}

/** On a phone-width screen the full sidebar leaves no room for the page, so it starts collapsed to icons (it can still be expanded). */
function useCollapseOnSmallScreens() {
  useEffect(() => {
    const mq = window.matchMedia('(max-width: 767px)');
    const apply = () => { if (mq.matches && !useUI.getState().sidebarCollapsed) useUI.getState().toggleSidebar(); };
    apply();
    mq.addEventListener('change', apply);
    return () => mq.removeEventListener('change', apply);
  }, []);
}

export function Shell() {
  useShortcuts();
  useCollapseOnSmallScreens();
  const { pathname } = useLocation();
  const copilotOpen = useUI((s) => s.copilotOpen);
  return (
    <div className="flex h-full bg-bg">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-[100] focus:rounded focus:bg-accent focus:px-3 focus:py-1.5 focus:text-accent-fg"
      >
        Skip to content
      </a>
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar />
        <ApiBanner />
        <main id="main" className="min-h-0 flex-1 overflow-y-auto">
          <ErrorBoundary resetKey={pathname}>
            <Suspense fallback={<PageFallback />}>
              <WorkspaceGate fallback={<PageFallback />}>
                <Outlet />
              </WorkspaceGate>
            </Suspense>
          </ErrorBoundary>
        </main>
      </div>
      <InspectorHost />
      {copilotOpen && pathname !== '/copilot' && (
        <Suspense fallback={null}>
          <CopilotDrawer />
        </Suspense>
      )}
      <AppCommandPalette />
      <ShortcutsModal />
      <Toaster />
    </div>
  );
}
