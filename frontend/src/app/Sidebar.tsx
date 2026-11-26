import * as DropdownMenu from '@radix-ui/react-dropdown-menu';
import { Check, ChevronsLeft, ChevronsRight, ChevronsUpDown } from 'lucide-react';
import { NavLink } from 'react-router-dom';
import { Avatar } from '@/components/ui/Badge';
import { IconButton } from '@/components/ui/Button';
import { Tooltip } from '@/components/ui/Overlay';
import { cn } from '@/lib/cn';
import { ARCHITECT_ROLE, ARCHITECT_USERS, useUI } from '@/store/ui';
import { useNavBadges } from '@/hooks/useNavBadges';
import { NAV } from './nav';

export function LogoMark({ size = 24 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden>
      <defs>
        <linearGradient id="aq-logo" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#6E7BFF" />
          <stop offset="1" stopColor="#8B5CF6" />
        </linearGradient>
      </defs>
      <path d="M16 4l10.5 6v12L16 28 5.5 22V10z" fill="none" stroke="url(#aq-logo)" strokeWidth="2" strokeLinejoin="round" />
      <path d="M5.5 10L16 16l10.5-6M16 16v12" fill="none" stroke="url(#aq-logo)" strokeWidth="1.4" strokeLinejoin="round" opacity="0.7" />
      <circle cx="16" cy="16" r="2.6" fill="url(#aq-logo)" />
    </svg>
  );
}

export function Sidebar() {
  const collapsed = useUI((s) => s.sidebarCollapsed);
  const toggle = useUI((s) => s.toggleSidebar);
  const userName = useUI((s) => s.userName);
  const setUserName = useUI((s) => s.setUserName);
  const badges = useNavBadges();

  return (
    <aside
      aria-label="Primary"
      style={{ width: collapsed ? 'var(--sidebar-w-collapsed)' : 'var(--sidebar-w)' }}
      className="flex h-full shrink-0 flex-col border-r border-line bg-surface transition-[width] duration-220 ease-[var(--ease)]"
    >
      <div className={cn('flex h-[var(--topbar-h)] shrink-0 items-center border-b border-line-subtle', collapsed ? 'justify-center' : 'gap-2.5 px-4')}>
        <LogoMark size={22} />
        {!collapsed && (
          <div className="flex items-baseline gap-1.5">
            <span className="text-[15px] font-semibold tracking-tight">ArchIQ</span>
            <span className="micro !text-[9px]">EA Intelligence</span>
          </div>
        )}
      </div>

      <nav className="min-h-0 flex-1 overflow-y-auto px-2 py-3" aria-label="Modules">
        {NAV.map((group) => (
          <div key={group.label} className="mb-4">
            {!collapsed ? (
              <div className="micro px-2.5 pb-1.5">{group.label}</div>
            ) : (
              <div className="mx-3 mb-1.5 h-px bg-line-subtle" aria-hidden />
            )}
            <ul className="space-y-0.5">
              {group.items.map((item) => {
                const badge = item.badgeKey ? badges[item.badgeKey] : undefined;
                const link = (
                  <NavLink
                    to={item.to}
                    end={item.to === '/'}
                    aria-label={collapsed ? item.label : undefined}
                    className={({ isActive }) =>
                      cn(
                        'group relative flex h-8 items-center rounded-md text-sm transition-colors duration-150',
                        collapsed ? 'justify-center' : 'gap-2.5 px-2.5',
                        isActive ? 'bg-accent/10 text-fg' : 'text-fg-2 hover:bg-raised hover:text-fg',
                      )
                    }
                  >
                    {({ isActive }) => (
                      <>
                        {isActive && <span className="absolute -left-2 top-1.5 h-5 w-[2px] rounded-full bg-accent" aria-hidden />}
                        <item.icon className={cn('h-4 w-4 shrink-0', isActive ? 'text-accent' : 'text-fg-3 group-hover:text-fg-2')} strokeWidth={1.75} />
                        {!collapsed && <span className="truncate">{item.label}</span>}
                        {!collapsed && badge !== undefined && (
                          <span className="num ml-auto rounded bg-raised px-1.5 font-mono text-[10px] leading-4 text-fg-2">{badge}</span>
                        )}
                        {collapsed && badge !== undefined && <span className="absolute right-1.5 top-1.5 h-1.5 w-1.5 rounded-full bg-accent" />}
                      </>
                    )}
                  </NavLink>
                );
                return (
                  <li key={item.to}>
                    {collapsed ? (
                      <Tooltip content={item.label} side="right" delay={100}>
                        {link}
                      </Tooltip>
                    ) : (
                      link
                    )}
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      <div className="shrink-0 border-t border-line-subtle p-2">
        <div className={cn('flex items-center rounded-md', collapsed ? 'flex-col gap-2' : 'gap-1 px-1 py-1')}>
          <DropdownMenu.Root>
            <DropdownMenu.Trigger asChild>
              <button
                type="button"
                aria-label={`Switch active architect (${userName})`}
                className={cn(
                  'flex min-w-0 flex-1 items-center rounded-md text-left transition-colors hover:bg-raised focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent',
                  collapsed ? 'justify-center p-1' : 'gap-2 px-1.5 py-1',
                )}
              >
                <Avatar name={userName} size={28} />
                {!collapsed && (
                  <>
                    <div className="min-w-0 flex-1 leading-tight">
                      <div className="truncate text-sm font-medium text-fg">{userName}</div>
                      <div className="truncate text-[11px] text-fg-3">{ARCHITECT_ROLE}</div>
                    </div>
                    <ChevronsUpDown className="h-3.5 w-3.5 shrink-0 text-fg-3" aria-hidden />
                  </>
                )}
              </button>
            </DropdownMenu.Trigger>
            <DropdownMenu.Portal>
              <DropdownMenu.Content side="top" align="start" sideOffset={6} className="glass z-[75] min-w-[230px] animate-fadeIn rounded-lg border border-line p-1 shadow-pop">
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
          <IconButton label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'} size="sm" onClick={toggle}>
            {collapsed ? <ChevronsRight className="h-4 w-4" /> : <ChevronsLeft className="h-4 w-4" />}
          </IconButton>
        </div>
      </div>
    </aside>
  );
}
