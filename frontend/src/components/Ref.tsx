import { useNavigate } from 'react-router-dom';
import { useUI } from '@/store/ui';
import { cn } from '@/lib/cn';

const ASSET_TYPES = new Set(['application', 'api', 'database', 'cloud', 'asset', 'capability', 'owner', 'integration']);

export interface RefTarget {
  type: string;
  id: string;
}

/** Opens the right inspector (or navigates) for any entity reference returned by the API. */
export function useOpenRef() {
  const open = useUI((s) => s.openInspector);
  const nav = useNavigate();
  return (r: RefTarget) => {
    if (ASSET_TYPES.has(r.type)) return open({ kind: 'asset', id: r.id });
    if (r.type === 'finding') return open({ kind: 'finding', id: r.id });
    if (r.type === 'drift') return open({ kind: 'drift', id: r.id });
    if (r.type === 'document') return open({ kind: 'document', id: r.id });
    if (r.type === 'review') return nav(`/reviews/${r.id}`);
    if (r.type === 'standard') return nav(`/standards?id=${r.id}`);
    if (r.type === 'workflow') return;
  };
}

export function RefLink({ type, id, name, className, mono }: RefTarget & { name?: string; className?: string; mono?: boolean }) {
  const open = useOpenRef();
  return (
    <button
      type="button"
      onClick={(e) => {
        e.stopPropagation();
        open({ type, id });
      }}
      className={cn('max-w-full truncate text-left text-accent hover:underline focus-visible:underline', mono && 'font-mono text-xs', className)}
      title={name ?? id}
    >
      {name ?? id}
    </button>
  );
}
