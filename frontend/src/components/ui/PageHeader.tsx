import { RefreshCw } from 'lucide-react';
import type { ReactNode } from 'react';
import { StatusDot } from './Badge';
import { cn } from '@/lib/cn';

export function PageHeader({
  title,
  description,
  actions,
  secondary,
  freshness,
  className,
}: {
  title: string;
  description: string;
  actions?: ReactNode;
  secondary?: ReactNode;
  freshness?: string;
  className?: string;
}) {
  return (
    <header className={cn('relative mb-5 flex flex-wrap items-end justify-between gap-4', className)}>
      <div className="min-w-0">
        <h1 className="text-xl font-semibold text-fg">{title}</h1>
        <p className="mt-1 max-w-2xl text-sm text-fg-2">{description}</p>
        {freshness && (
          <p className="mt-2 flex items-center gap-1.5 text-xs text-fg-3">
            <StatusDot tone="healthy" pulse />
            <RefreshCw className="h-3 w-3" aria-hidden />
            {freshness}
          </p>
        )}
      </div>
      <div className="flex items-center gap-2">
        {secondary}
        {actions}
      </div>
    </header>
  );
}

export function Page({ children, className, wide }: { children: ReactNode; className?: string; wide?: boolean }) {
  return (
    <div className={cn('relative mx-auto w-full px-6 pb-10 pt-6', wide ? 'max-w-none' : 'max-w-[1480px]', className)}>
      <div className="grid-texture pointer-events-none absolute inset-x-0 top-0 -z-0 h-64" aria-hidden />
      <div className="relative">{children}</div>
    </div>
  );
}
