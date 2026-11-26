import * as DropdownMenu from '@radix-ui/react-dropdown-menu';
import * as Popover from '@radix-ui/react-popover';
import { Bell, Check, ChevronDown, ChevronRight, Moon, Search, Sparkles, Sun } from 'lucide-react';
import { Link, useLocation } from 'react-router-dom';
import { Avatar, Badge } from '@/components/ui/Badge';
import { useWorkspace } from '@/features/start/useWorkspace';
import { Kbd, IconButton } from '@/components/ui/Button';
import { StatusDot } from '@/components/ui/Badge';
import { Tooltip } from '@/components/ui/Overlay';
import { ARCHITECT_ROLE, ARCHITECT_USERS, useUI } from '@/store/ui';
import { findNav, SCOPES } from './nav';

const NOTIFICATIONS = [
  { id: 'n1', tone: 'critical' as const, title: 'Drift detected on stkestrelclaimsprd01', body: 'Public network access enabled; approved Terraform specifies a private endpoint.', when: '9 min ago' },
  { id: 'n2', tone: 'high' as const, title: 'WebSphere 8.5 out of vendor support', body: 'Claims Core and Claims Batch Processor still depend on this runtime.', when: '1 h ago' },
  { id: 'n3', tone: 'accent' as const, title: 'ARB review ready: Claims Notification Service on Azure', body: 'Automated pre-ARB review completed for Tier 1 submission.', when: '3 h ago' },
];

function Breadcrumbs() {
  const { pathname } = useLocation();
  const { group, item } = findNav(pathname);
  const design = pathname.startsWith('/_design');
  return (
    <nav aria-label="Breadcrumb" className="flex min-w-0 items-center gap-1.5 text-sm">
      <Link to="/" className="hidden min-h-6 shrink-0 items-center text-fg-3 hover:text-fg sm:inline-flex">
        Home
      </Link>
      <ChevronRight className="hidden h-3.5 w-3.5 shrink-0 text-fg-3 sm:block" aria-hidden />
      {design ? (
        <span className="font-medium">Design system</span>
      ) : (
        <>
          {group && item && item.to !== '/' && (
            <>
              <span className="hidden text-fg-3 md:inline">{group.label}</span>
              <ChevronRight className="hidden h-3.5 w-3.5 text-fg-3 md:block" aria-hidden />
            </>
          )}
          <span className="truncate font-medium" aria-current="page">
            {item?.label ?? 'Not found'}
          </span>
        </>
      )}
    </nav>
  );
}

export function Topbar() {
  const { theme, toggleTheme, userName, setUserName, scope, setScope, setCommandOpen, setCopilotOpen } = useUI();
  const ws = useWorkspace();
  const demo = ws.data?.status === 'ready' && ws.data.mode === 'demo';
  return (
    <header className="flex h-[var(--topbar-h)] shrink-0 items-center gap-3 border-b border-line bg-surface/80 px-4 backdrop-blur">
      <Breadcrumbs />
      {demo && (
        <Link to="/start" title="Showing baseline estate snapshot. Start a new analysis to refresh." className="shrink-0 rounded focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent" data-testid="demo-badge"><Badge tone="medium">Not live</Badge></Link>
      )}

      <div className="ml-auto flex items-center gap-2">
        <button
          type="button"
          onClick={() => setCommandOpen(true)}
          className="group hidden h-8 w-72 items-center gap-2 rounded-md border border-line bg-bg px-2.5 text-sm text-fg-3 transition-colors duration-150 hover:border-fg-3/40 md:flex"
        >
          <Search className="h-3.5 w-3.5" aria-hidden />
          {/* no aria-label: a name that does not start with the visible text fails WCAG 2.5.3 for voice-control users */}
          <span className="flex-1 text-left">Search or ask…<span className="sr-only"> (open command palette)</span></span>
          <Kbd>⌘</Kbd>
          <Kbd>K</Kbd>
        </button>

        <DropdownMenu.Root>
          <DropdownMenu.Trigger asChild>
            <button
              type="button"
              className="hidden h-8 items-center gap-2 rounded-md border border-line bg-bg px-2.5 text-xs text-fg-2 transition-colors duration-150 hover:border-fg-3/40 hover:text-fg lg:flex"
            >
              <StatusDot tone="healthy" />
              <span className="max-w-[210px] truncate"><span className="sr-only">Scope: </span>{scope}</span>
              <ChevronDown className="h-3 w-3 text-fg-3" />
            </button>
          </DropdownMenu.Trigger>
          <DropdownMenu.Portal>
            <DropdownMenu.Content align="end" sideOffset={6} className="glass z-[75] min-w-[260px] animate-fadeIn rounded-lg border border-line p-1 shadow-pop">
              <div className="micro px-2.5 py-1.5">Scope</div>
              {SCOPES.map((s) => (
                <DropdownMenu.Item
                  key={s}
                  onSelect={() => setScope(s)}
                  className="flex h-8 cursor-default items-center justify-between rounded px-2.5 text-sm outline-none data-[highlighted]:bg-raised"
                >
                  {s}
                  {s === scope && <Check className="h-3.5 w-3.5 text-accent" />}
                </DropdownMenu.Item>
              ))}
            </DropdownMenu.Content>
          </DropdownMenu.Portal>
        </DropdownMenu.Root>

        <Tooltip content="Copilot (⌘J)">
          <IconButton label="Open Copilot" onClick={() => setCopilotOpen(true)}>
            <Sparkles className="h-4 w-4 text-accent" />
          </IconButton>
        </Tooltip>

        <Popover.Root>
          <Popover.Trigger asChild>
            <IconButton label="Notifications" className="relative">
              <Bell className="h-4 w-4" />
              <span className="absolute right-1.5 top-1.5 h-1.5 w-1.5 rounded-full bg-critical" aria-hidden />
            </IconButton>
          </Popover.Trigger>
          <Popover.Portal>
            <Popover.Content align="end" sideOffset={6} className="glass z-[75] w-[360px] animate-fadeIn rounded-lg border border-line shadow-pop">
              <div className="border-b border-line px-4 py-3 text-sm font-semibold">Notifications</div>
              <ul className="max-h-80 divide-y divide-line-subtle overflow-y-auto">
                {NOTIFICATIONS.map((n) => (
                  <li key={n.id} className="flex gap-3 px-4 py-3">
                    <span className="mt-1.5"><StatusDot tone={n.tone} /></span>
                    <div className="min-w-0">
                      <p className="text-sm font-medium">{n.title}</p>
                      <p className="mt-0.5 text-xs text-fg-2">{n.body}</p>
                      <p className="mt-1 text-[11px] text-fg-3">{n.when}</p>
                    </div>
                  </li>
                ))}
              </ul>
            </Popover.Content>
          </Popover.Portal>
        </Popover.Root>

        <Tooltip content={theme === 'dark' ? 'Light theme' : 'Dark theme'}>
          <IconButton label="Toggle theme" onClick={toggleTheme}>
            {theme === 'dark' ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </IconButton>
        </Tooltip>
        <DropdownMenu.Root>
          <DropdownMenu.Trigger asChild>
            <button
              type="button"
              aria-label={`Profile: ${userName} (${ARCHITECT_ROLE})`}
              className="rounded-full focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
            >
              <Avatar name={userName} size={28} />
            </button>
          </DropdownMenu.Trigger>
          <DropdownMenu.Portal>
            <DropdownMenu.Content align="end" sideOffset={6} className="glass z-[75] min-w-[230px] animate-fadeIn rounded-lg border border-line p-1 shadow-pop">
              <div className="micro px-2.5 py-1.5">Active profile</div>
              {ARCHITECT_USERS.map((u) => (
                <DropdownMenu.Item
                  key={u}
                  onSelect={() => setUserName(u)}
                  className="flex cursor-pointer items-center gap-2.5 rounded px-2.5 py-1.5 text-sm outline-none data-[highlighted]:bg-raised"
                >
                  <Avatar name={u} size={24} />
                  <div className="min-w-0 flex-1 leading-tight">
                    <div className="truncate text-sm font-medium text-fg">{u}</div>
                    <div className="truncate text-[10px] text-fg-3">{ARCHITECT_ROLE}</div>
                  </div>
                  {u === userName && <Check className="h-3.5 w-3.5 shrink-0 text-accent" />}
                </DropdownMenu.Item>
              ))}
            </DropdownMenu.Content>
          </DropdownMenu.Portal>
        </DropdownMenu.Root>
      </div>
    </header>
  );
}
