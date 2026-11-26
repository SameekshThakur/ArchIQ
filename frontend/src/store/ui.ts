import { create } from 'zustand';

export type Theme = 'dark' | 'light';

export const ARCHITECT_USERS = [
  'Saurabh Dubey',
  'Sameeksh Thakur',
  'Avadhi Jain',
  'Harshita Patidar',
] as const;

export type ArchitectUser = (typeof ARCHITECT_USERS)[number];
export const ARCHITECT_ROLE = 'Enterprise Architect';

export interface InspectorTarget {
  kind: string;
  id: string;
}

export interface ToastItem {
  id: number;
  title: string;
  description?: string;
  tone: 'neutral' | 'success' | 'error' | 'info';
}

interface UIState {
  theme: Theme;
  userName: ArchitectUser;
  sidebarCollapsed: boolean;
  inspector: InspectorTarget | null;
  commandOpen: boolean;
  copilotOpen: boolean;
  shortcutsOpen: boolean;
  scope: string;
  toasts: ToastItem[];
  apiDown: boolean;
  setTheme: (t: Theme) => void;
  toggleTheme: () => void;
  setUserName: (u: ArchitectUser) => void;
  toggleSidebar: () => void;
  openInspector: (t: InspectorTarget) => void;
  closeInspector: () => void;
  setCommandOpen: (o: boolean) => void;
  setCopilotOpen: (o: boolean) => void;
  setShortcutsOpen: (o: boolean) => void;
  setScope: (s: string) => void;
  setApiDown: (d: boolean) => void;
  toast: (t: Omit<ToastItem, 'id' | 'tone'> & { tone?: ToastItem['tone'] }) => void;
  dismissToast: (id: number) => void;
}

function readTheme(): Theme {
  try {
    const t = localStorage.getItem('archiq-theme');
    if (t === 'light' || t === 'dark') return t;
  } catch {
    /* storage unavailable */
  }
  return 'dark';
}

function applyTheme(t: Theme) {
  document.documentElement.dataset.theme = t;
  try {
    localStorage.setItem('archiq-theme', t);
  } catch {
    /* storage unavailable */
  }
}

let toastId = 1;

export const useUI = create<UIState>((set, get) => ({
  theme: readTheme(),
  userName: 'Saurabh Dubey',
  // phone-width screens start collapsed so the page does not shift after first paint
  sidebarCollapsed: typeof window !== 'undefined' && typeof window.matchMedia === 'function' && window.matchMedia('(max-width: 767px)').matches,
  inspector: null,
  commandOpen: false,
  copilotOpen: false,
  shortcutsOpen: false,
  scope: 'Enterprise · All domains',
  toasts: [],
  apiDown: false,
  setTheme: (t) => {
    applyTheme(t);
    set({ theme: t });
  },
  toggleTheme: () => get().setTheme(get().theme === 'dark' ? 'light' : 'dark'),
  setUserName: (u) => set({ userName: u }),
  toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
  openInspector: (t) => set({ inspector: t }),
  closeInspector: () => set({ inspector: null }),
  setCommandOpen: (o) => set({ commandOpen: o }),
  setCopilotOpen: (o) => set({ copilotOpen: o }),
  setShortcutsOpen: (o) => set({ shortcutsOpen: o }),
  setScope: (s) => set({ scope: s }),
  setApiDown: (d) => set({ apiDown: d }),
  toast: (t) => {
    const id = toastId++;
    set((s) => ({ toasts: [...s.toasts, { id, tone: 'neutral', ...t }] }));
    setTimeout(() => get().dismissToast(id), 4500);
  },
  dismissToast: (id) => set((s) => ({ toasts: s.toasts.filter((x) => x.id !== id) })),
}));
