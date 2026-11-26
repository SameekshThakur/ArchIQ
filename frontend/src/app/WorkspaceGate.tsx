import { Rocket } from 'lucide-react';
import type { ReactNode } from 'react';
import { Link, Navigate, useLocation } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/Panel';
import { useWorkspace, useWorkspaceActions } from '@/features/start/useWorkspace';
import { useNavigate } from 'react-router-dom';

/** Pages that work without an analysis: the start page, platform connections, the Blueprint Studio (it designs new systems and needs no estate) and the design-system reference. */
const OPEN = ['/start', '/connections', '/studio', '/_design'];

/**
 * Until the person has started an analysis (or loaded the demo) every module would be showing numbers about an estate they never asked about.
 * So they see where to begin instead, and the first visit lands on the start page.
 */
export function WorkspaceGate({ children, fallback }: { children: ReactNode; fallback: ReactNode }) {
  const { pathname } = useLocation();
  const ws = useWorkspace();
  if (OPEN.some((p) => pathname === p || pathname.startsWith(`${p}/`))) return <>{children}</>;
  if (ws.isError) return <>{children}</>; // API unreachable: the banner explains it, and the page's own error state takes over
  if (!ws.data) return <>{fallback}</>;
  if (ws.data.status === 'ready') return <>{children}</>;
  if (pathname === '/' && ws.data.status === 'empty') return <Navigate to="/start" replace />;
  return <NothingYet status={ws.data.status} />;
}

function NothingYet({ status }: { status: 'empty' | 'running' | 'failed' | 'ready' }) {
  const navigate = useNavigate();
  const { loadDemo } = useWorkspaceActions();
  const running = status === 'running';
  return (
    <div className="mx-auto max-w-[1480px] px-6 pt-10" data-testid="workspace-empty">
      <EmptyState
        icon={<Rocket className="h-4 w-4" aria-hidden />}
        title={running ? 'Your analysis is still running' : status === 'failed' ? 'The last analysis did not finish' : 'Nothing to show yet'}
        description={running ? 'This page fills in as soon as the run finishes.' : 'This page shows what ArchIQ finds once you say what you are looking for, add your documents and choose a business domain.'}
        action={
          <div className="flex flex-wrap gap-2">
            <Link to="/start" className="inline-flex h-8 items-center gap-1.5 rounded-md accent-bg px-3 text-sm font-medium text-accent-fg hover:brightness-110 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent">{running ? 'See progress' : 'Start an analysis'}</Link>
            {!running && <Button variant="outline" onClick={() => void loadDemo().then(() => navigate('/'))}>Load baseline estate</Button>}
          </div>
        }
      />
    </div>
  );
}
