import { Suspense } from 'react';
import { Drawer } from '@/components/ui/Overlay';
import { Skeleton } from '@/components/ui/Panel';
import { getInspector } from '@/features/inspector/registry';
import { useUI } from '@/store/ui';

export function InspectorHost() {
  const target = useUI((s) => s.inspector);
  const close = useUI((s) => s.closeInspector);
  const entry = target ? getInspector(target.kind) : undefined;
  return (
    <Drawer
      open={!!target && !!entry}
      onOpenChange={(o) => !o && close()}
      title={entry?.label ?? 'Inspector'}
      subtitle={target ? <span className="font-mono">{target.id}</span> : undefined}
      width={entry?.width ?? 480}
    >
      {target && entry && (
        <Suspense
          fallback={
            <div className="space-y-3" role="status" aria-label="Loading">
              <Skeleton className="h-6 w-2/3" />
              <Skeleton className="h-3 w-full" />
              <Skeleton className="h-3 w-5/6" />
              <Skeleton className="mt-6 h-32 w-full" />
            </div>
          }
        >
          <entry.Component key={`${target.kind}:${target.id}`} id={target.id} />
        </Suspense>
      )}
    </Drawer>
  );
}
