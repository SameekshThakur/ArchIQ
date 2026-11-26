import {
  Blocks,
  Wand2,
  ClipboardCheck,
  Flame,
  FileCode2,
  FileSearch,
  GitCompareArrows,
  LayoutDashboard,
  Network,
  Plug,
  Radar,
  Rocket,
  Route,
  Scale,
  ScanSearch,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Crosshair,
  Waypoints,
  type LucideIcon,
} from 'lucide-react';

export interface NavItem {
  to: string;
  label: string;
  description: string;
  icon: LucideIcon;
  /** second key of a `g <key>` sequence */
  key: string;
  badgeKey?: string;
}

export interface NavGroup {
  label: string;
  items: NavItem[];
}

export const NAV: NavGroup[] = [
  {
    label: 'Start',
    items: [
      { to: '/start', label: 'New analysis', description: 'Say what you are looking for, add documents and a domain, and run it end to end', icon: Rocket, key: 'n' },
      { to: '/connections', label: 'Connections', description: 'Connect ServiceNow, Jira, Azure, GitHub, Confluence and SharePoint', icon: Plug, key: 'k' },
    ],
  },
  {
    label: 'Overview',
    items: [
      { to: '/', label: 'Executive overview', description: 'Estate health, risks and AI activity', icon: LayoutDashboard, key: 'h' },
    ],
  },
  {
    label: 'Discover',
    items: [
      { to: '/discovery', label: 'Discovery', description: 'Scan and inventory the estate', icon: ScanSearch, key: 'd' },
      { to: '/graph', label: 'Knowledge graph', description: 'Living architecture graph', icon: Network, key: 'g' },
    ],
  },
  {
    label: 'Understand',
    items: [
      { to: '/documents', label: 'Document intelligence', description: 'Reconstruct architecture from documents', icon: FileSearch, key: 'o' },
      { to: '/copilot', label: 'Copilot', description: 'Ask questions about the estate', icon: Sparkles, key: 'p' },
    ],
  },
  {
    label: 'Assess',
    items: [
      { to: '/assessment', label: 'Assessment', description: 'Smells, SPOFs and obsolete tech', icon: ShieldAlert, key: 'a', badgeKey: 'findings' },
      { to: '/debt-radar', label: 'Debt radar', description: 'Technical-debt heatmap', icon: Flame, key: 'r' },
      { to: '/impact', label: 'Change impact', description: 'Blast radius of a change', icon: Crosshair, key: 'i' },
    ],
  },
  {
    label: 'Design',
    items: [
      { to: '/target-architecture', label: 'Target architecture', description: 'Generate future-state options', icon: Radar, key: 't' },
      { to: '/decisions', label: 'Decision agent', description: 'Weighted option comparison and ADRs', icon: Scale, key: 'e' },
      { to: '/studio', label: 'Blueprint Studio', description: 'From requirements to a validated, submittable architecture', icon: Wand2, key: 'u' },
      { to: '/blueprints', label: 'Blueprints', description: 'Reference architectures and patterns', icon: Blocks, key: 'b' },
    ],
  },
  {
    label: 'Govern',
    items: [
      { to: '/standards', label: 'Standards', description: 'Check designs against policy', icon: ShieldCheck, key: 's' },
      { to: '/reviews', label: 'Review agent', description: 'Automated ARB readiness reviews', icon: ClipboardCheck, key: 'v', badgeKey: 'reviews' },
    ],
  },
  {
    label: 'Modernize',
    items: [
      { to: '/modernization', label: 'Modernization', description: 'Transformation waves and roadmap', icon: Route, key: 'm' },
      { to: '/codegen', label: 'Architecture to code', description: 'IaC, contracts and skeletons', icon: FileCode2, key: 'c' },
    ],
  },
  {
    label: 'Operate',
    items: [
      { to: '/drift', label: 'Drift detection', description: 'Approved vs deployed', icon: GitCompareArrows, key: 'f', badgeKey: 'drift' },
    ],
  },
];

export const ALL_NAV: NavItem[] = NAV.flatMap((g) => g.items);

export function findNav(pathname: string): { group?: NavGroup; item?: NavItem } {
  for (const group of NAV) {
    const item = group.items.find((i) => (i.to === '/' ? pathname === '/' : pathname.startsWith(i.to)));
    if (item) return { group, item };
  }
  return {};
}

export const SCOPES = [
  'Enterprise · All domains',
  'Enterprise · Claims & Policy domain',
  'Enterprise · Customer & Distribution',
  'Enterprise · Finance & Billing',
  'Enterprise · Data & Analytics',
];

export { Waypoints };
