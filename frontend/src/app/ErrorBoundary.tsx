import { Component, type ErrorInfo, type ReactNode } from 'react';
import { AlertTriangle } from 'lucide-react';
import { Button } from '@/components/ui/Button';

interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<{ children: ReactNode; resetKey?: string }, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('[ArchIQ] render error', error, info.componentStack);
  }

  componentDidUpdate(prev: { resetKey?: string }) {
    if (prev.resetKey !== this.props.resetKey && this.state.error) this.setState({ error: null });
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="mx-auto mt-24 max-w-md px-6">
        <div className="rounded-lg border border-critical/30 bg-critical/5 p-5">
          <AlertTriangle className="h-5 w-5 text-critical" aria-hidden />
          <h2 className="mt-3 text-base font-semibold">This view failed to render</h2>
          <p className="mt-1 text-sm text-fg-2">{this.state.error.message}</p>
          <Button className="mt-4" onClick={() => this.setState({ error: null })}>
            Try again
          </Button>
        </div>
      </div>
    );
  }
}

export function RouteError() {
  return (
    <div className="mx-auto mt-24 max-w-md px-6">
      <h2 className="text-base font-semibold">Something went wrong loading this page</h2>
      <p className="mt-1 text-sm text-fg-2">Reload the page. If it persists, check that the backend is running on port 8000.</p>
      <Button className="mt-4" onClick={() => window.location.reload()}>
        Reload
      </Button>
    </div>
  );
}
