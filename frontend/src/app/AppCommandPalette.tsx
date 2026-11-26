import { useQuery } from '@tanstack/react-query';
import { Box, Database, Moon, Network, Plug, Server, Sparkles, Sun, Keyboard, Cloud } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { get } from '@/api/client';
import { CommandPalette, type PaletteGroup } from '@/components/ui/CommandPalette';
import { useUI } from '@/store/ui';
import { ALL_NAV } from './nav';

interface AssetHit {
  id: string;
  name: string;
  type: string;
  domain?: string;
}
interface AssetPage {
  items: AssetHit[];
}

const typeIcon: Record<string, typeof Box> = {
  application: Box,
  api: Network,
  database: Database,
  integration: Plug,
  cloud: Cloud,
};

const SUGGESTED = [
  'Show all applications dependent on Oracle 12c that support Claims.',
  'What is the blast radius of changing Customer API v2?',
  'Which systems are single points of failure?',
];

export function AppCommandPalette() {
  const open = useUI((s) => s.commandOpen);
  const setOpen = useUI((s) => s.setCommandOpen);
  const toggleTheme = useUI((s) => s.toggleTheme);
  const theme = useUI((s) => s.theme);
  const setShortcuts = useUI((s) => s.setShortcutsOpen);
  const setCopilot = useUI((s) => s.setCopilotOpen);
  const openInspector = useUI((s) => s.openInspector);
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [debounced, setDebounced] = useState('');

  useEffect(() => {
    const t = setTimeout(() => setDebounced(query.trim()), 160);
    return () => clearTimeout(t);
  }, [query]);
  useEffect(() => {
    if (!open) setQuery('');
  }, [open]);

  const hits = useQuery({
    queryKey: ['palette-assets', debounced],
    queryFn: () => get<AssetPage>('/assets', { q: debounced, page_size: 6 }),
    enabled: open && debounced.length >= 2,
    staleTime: 15_000,
    retry: false,
  });

  const close = () => setOpen(false);
  const q = query.trim().toLowerCase();

  const groups = useMemo<PaletteGroup[]>(() => {
    const pages = ALL_NAV.filter((n) => !q || n.label.toLowerCase().includes(q) || n.description.toLowerCase().includes(q)).map((n) => ({
      id: n.to,
      label: n.label,
      hint: n.description,
      icon: <n.icon className="h-4 w-4" strokeWidth={1.75} />,
      shortcut: n.to === '/' ? ['g', 'h'] : ['g', n.key],
      onSelect: () => {
        navigate(n.to);
        close();
      },
    }));
    const assets = (hits.data?.items ?? []).map((a) => {
      const Icon = typeIcon[a.type] ?? Server;
      return {
        id: a.id,
        label: a.name,
        hint: `${a.type}${a.domain ? ' · ' + a.domain : ''}`,
        icon: <Icon className="h-4 w-4" strokeWidth={1.75} />,
        onSelect: () => {
          close();
          openInspector({ kind: 'asset', id: a.id });
        },
      };
    });
    const ask = (text: string) => ({
      id: `ask-${text}`,
      label: text,
      icon: <Sparkles className="h-4 w-4 text-accent" />,
      onSelect: () => {
        close();
        navigate(`/copilot?q=${encodeURIComponent(text)}`);
      },
    });
    const copilot = q.length > 3 ? [ask(query.trim())] : SUGGESTED.map(ask);
    const actions = [
      {
        id: 'theme',
        label: theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme',
        icon: theme === 'dark' ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />,
        onSelect: () => {
          toggleTheme();
          close();
        },
      },
      {
        id: 'copilot',
        label: 'Open Copilot panel',
        icon: <Sparkles className="h-4 w-4" />,
        shortcut: ['⌘', 'J'],
        onSelect: () => {
          close();
          setCopilot(true);
        },
      },
      {
        id: 'shortcuts',
        label: 'Keyboard shortcuts',
        icon: <Keyboard className="h-4 w-4" />,
        shortcut: ['?'],
        onSelect: () => {
          close();
          setShortcuts(true);
        },
      },
    ].filter((a) => !q || a.label.toLowerCase().includes(q));
    return [
      { heading: 'Assets', items: assets },
      { heading: q.length > 3 ? 'Ask the Copilot' : 'Suggested questions', items: copilot },
      { heading: 'Pages', items: pages },
      { heading: 'Actions', items: actions },
    ];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, hits.data, theme]);

  return (
    <CommandPalette
      open={open}
      onOpenChange={setOpen}
      groups={groups}
      query={query}
      onQueryChange={setQuery}
      loading={hits.isFetching}
    />
  );
}
