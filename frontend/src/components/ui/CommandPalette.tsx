import { Command } from 'cmdk';
import * as Dialog from '@radix-ui/react-dialog';
import { CornerDownLeft, Search } from 'lucide-react';
import type { ReactNode } from 'react';
import { Kbd } from './Button';

export interface PaletteItem {
  id: string;
  label: string;
  hint?: string;
  icon?: ReactNode;
  shortcut?: string[];
  onSelect: () => void;
}

export interface PaletteGroup {
  heading: string;
  items: PaletteItem[];
}

export function CommandPalette({
  open,
  onOpenChange,
  groups,
  query,
  onQueryChange,
  loading,
  placeholder = 'Search assets, jump to a page, or ask the Copilot…',
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  groups: PaletteGroup[];
  query: string;
  onQueryChange: (q: string) => void;
  loading?: boolean;
  placeholder?: string;
}) {
  const visible = groups.filter((g) => g.items.length > 0);
  return (
    <Command.Dialog
      open={open}
      onOpenChange={onOpenChange}
      shouldFilter={false}
      label="Command palette"
      overlayClassName="fixed inset-0 z-[65] bg-[rgb(var(--scrim)/0.6)] backdrop-blur-[2px] animate-fadeIn"
      contentClassName="glass fixed left-1/2 top-[16vh] z-[66] w-[620px] max-w-[94vw] -translate-x-1/2 animate-rise overflow-hidden rounded-xl border border-line shadow-pop"
    >
      <Dialog.Title className="sr-only">Command palette</Dialog.Title>
      <div className="flex items-center gap-2.5 border-b border-line px-4">
        <Search className="h-4 w-4 shrink-0 text-fg-3" aria-hidden />
        <Command.Input
          value={query}
          onValueChange={onQueryChange}
          placeholder={placeholder}
          className="h-12 w-full bg-transparent text-sm text-fg outline-none placeholder:text-fg-3"
        />
        <Kbd>Esc</Kbd>
      </div>
      <Command.List className="max-h-[52vh] overflow-y-auto p-2">
        {visible.length === 0 && (
          <Command.Empty className="px-3 py-8 text-center text-sm text-fg-3">
            {loading ? 'Searching the estate…' : 'No matches. Try an application, API or database name.'}
          </Command.Empty>
        )}
        {visible.map((g) => (
          <Command.Group
            key={g.heading}
            heading={g.heading}
            className="mb-1 [&_[cmdk-group-heading]]:micro [&_[cmdk-group-heading]]:px-2.5 [&_[cmdk-group-heading]]:py-1.5"
          >
            {g.items.map((it) => (
              <Command.Item
                key={it.id}
                value={`${g.heading}-${it.id}`}
                onSelect={it.onSelect}
                className="flex h-9 cursor-pointer items-center gap-2.5 rounded-md px-2.5 text-sm text-fg-2 data-[selected=true]:bg-accent/10 data-[selected=true]:text-fg"
              >
                {it.icon && <span className="flex h-4 w-4 shrink-0 items-center justify-center text-fg-3">{it.icon}</span>}
                <span className="truncate">{it.label}</span>
                {it.hint && <span className="ml-1 truncate text-xs text-fg-3">{it.hint}</span>}
                <span className="ml-auto flex items-center gap-1">
                  {it.shortcut?.map((k, ki) => (
                    <Kbd key={`${k}-${ki}`}>{k}</Kbd>
                  ))}
                  <CornerDownLeft className="h-3 w-3 text-fg-3 opacity-0 [[data-selected=true]_&]:opacity-100" aria-hidden />
                </span>
              </Command.Item>
            ))}
          </Command.Group>
        ))}
      </Command.List>
    </Command.Dialog>
  );
}
