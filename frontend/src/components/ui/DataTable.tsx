import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
} from '@tanstack/react-table';
import { useVirtualizer } from '@tanstack/react-virtual';
import { ArrowDown, ArrowUp, ChevronsUpDown } from 'lucide-react';
import { useRef, useState, type KeyboardEvent, type ReactNode } from 'react';
import { cn } from '@/lib/cn';
import { Skeleton } from './Panel';

export interface DataTableProps<T> {
  data: T[];
  columns: ColumnDef<T, any>[]; // eslint-disable-line @typescript-eslint/no-explicit-any -- TanStack column value types are heterogeneous
  getRowId?: (row: T, index: number) => string;
  onRowClick?: (row: T) => void;
  selectedId?: string | null;
  loading?: boolean;
  empty?: ReactNode;
  /** Max height of the scroll body in px. Rows are virtualised inside it. */
  maxHeight?: number;
  rowHeight?: number;
  className?: string;
  initialSort?: SortingState;
  ariaLabel?: string;
}

export function DataTable<T>({
  data,
  columns,
  getRowId,
  onRowClick,
  selectedId,
  loading,
  empty,
  maxHeight = 520,
  rowHeight = 40,
  className,
  initialSort = [],
  ariaLabel = 'Data table',
}: DataTableProps<T>) {
  const [sorting, setSorting] = useState<SortingState>(initialSort);
  const table = useReactTable({
    data,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getRowId,
  });
  const rows = table.getRowModel().rows;
  const scrollRef = useRef<HTMLDivElement>(null);
  const virt = useVirtualizer({
    count: rows.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => rowHeight,
    overscan: 10,
  });

  const headers = table.getHeaderGroups()[0]?.headers ?? [];
  const cellStyle = (size: number) => ({ flex: `${size} 1 0px`, minWidth: 0 });

  const onKey = (e: KeyboardEvent<HTMLDivElement>, row: T) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onRowClick?.(row);
    } else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      const el = e.currentTarget;
      const next = (e.key === 'ArrowDown' ? el.nextElementSibling : el.previousElementSibling) as HTMLElement | null;
      next?.focus();
    }
  };

  return (
    <div className={cn('overflow-hidden rounded-lg border border-line bg-surface', className)}>
      <div role="table" aria-label={ariaLabel} aria-rowcount={rows.length}>
        <div role="rowgroup" className="border-b border-line bg-raised/40">
          <div role="row" className="flex items-center px-3" style={{ height: 34 }}>
            {headers.map((h) => {
              const sortable = h.column.getCanSort();
              const dir = h.column.getIsSorted();
              const size = h.column.getSize();
              return (
                <div
                  key={h.id}
                  role="columnheader"
                  aria-sort={dir === 'asc' ? 'ascending' : dir === 'desc' ? 'descending' : 'none'}
                  style={cellStyle(size)}
                  className="pr-3"
                >
                  {h.isPlaceholder ? null : sortable ? (
                    <button
                      type="button"
                      onClick={h.column.getToggleSortingHandler()}
                      className="micro group inline-flex items-center gap-1 hover:text-fg"
                    >
                      {flexRender(h.column.columnDef.header, h.getContext())}
                      {dir === 'asc' ? (
                        <ArrowUp className="h-3 w-3 text-accent" />
                      ) : dir === 'desc' ? (
                        <ArrowDown className="h-3 w-3 text-accent" />
                      ) : (
                        <ChevronsUpDown className="h-3 w-3 opacity-0 group-hover:opacity-60" />
                      )}
                    </button>
                  ) : (
                    <span className="micro">{flexRender(h.column.columnDef.header, h.getContext())}</span>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {loading ? (
          <div className="space-y-0" role="status" aria-label="Loading rows">
            {Array.from({ length: 7 }).map((_, i) => (
              <div key={i} className="flex items-center border-b border-line-subtle px-3" style={{ height: rowHeight }}>
                {headers.map((h, j) => (
                  <div key={h.id} style={cellStyle(h.column.getSize())} className="pr-3">
                    <Skeleton className="h-3" style={{ width: `${40 + ((i * 13 + j * 29) % 50)}%` }} />
                  </div>
                ))}
              </div>
            ))}
          </div>
        ) : rows.length === 0 ? (
          <div className="p-6">{empty ?? <p className="text-sm text-fg-3">No results match the current filters.</p>}</div>
        ) : (
          <div ref={scrollRef} role="rowgroup" className="overflow-auto" style={{ maxHeight }}>
            <div style={{ height: virt.getTotalSize(), position: 'relative' }}>
              {virt.getVirtualItems().map((v) => {
                const row = rows[v.index];
                const selected = selectedId != null && row.id === selectedId;
                return (
                  <div
                    key={row.id}
                    role="row"
                    aria-rowindex={v.index + 1}
                    aria-selected={selected || undefined}
                    tabIndex={onRowClick ? 0 : -1}
                    onClick={() => onRowClick?.(row.original)}
                    onKeyDown={(e) => onKey(e, row.original)}
                    style={{ position: 'absolute', top: 0, left: 0, right: 0, height: v.size, transform: `translateY(${v.start}px)` }}
                    className={cn(
                      'flex items-center border-b border-line-subtle px-3 text-sm transition-colors duration-150',
                      onRowClick && 'cursor-pointer hover:bg-raised/70 focus-visible:-outline-offset-2',
                      selected && 'bg-accent/[0.07] shadow-[inset_2px_0_0_rgb(var(--accent))]',
                    )}
                  >
                    {row.getVisibleCells().map((c) => (
                      <div key={c.id} role="cell" style={cellStyle(c.column.getSize())} className="truncate pr-3">
                        {flexRender(c.column.columnDef.cell, c.getContext())}
                      </div>
                    ))}
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
