import { useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useUI } from '@/store/ui';
import { ALL_NAV } from './nav';

function isTyping(el: EventTarget | null): boolean {
  const e = el as HTMLElement | null;
  if (!e) return false;
  return e.tagName === 'INPUT' || e.tagName === 'TEXTAREA' || e.tagName === 'SELECT' || e.isContentEditable;
}

/** Global keyboard shortcuts: ⌘K palette, ⌘J copilot, `/` search, `?` cheat-sheet, `g <key>` navigation. */
export function useShortcuts() {
  const navigate = useNavigate();
  const pendingG = useRef<number | null>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;
      const ui = useUI.getState();
      if (mod && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        ui.setCommandOpen(!ui.commandOpen);
        return;
      }
      if (mod && e.key.toLowerCase() === 'j') {
        e.preventDefault();
        ui.setCopilotOpen(!ui.copilotOpen);
        return;
      }
      if (e.key === 'Escape') {
        if (ui.inspector && !ui.commandOpen && !ui.shortcutsOpen) ui.closeInspector();
        return;
      }
      if (isTyping(e.target) || mod || e.altKey) return;

      if (e.key === '/') {
        const input = document.querySelector<HTMLInputElement>('[data-search-input]');
        if (input) {
          e.preventDefault();
          input.focus();
        } else {
          e.preventDefault();
          ui.setCommandOpen(true);
        }
        return;
      }
      if (e.key === '?') {
        e.preventDefault();
        ui.setShortcutsOpen(true);
        return;
      }
      if (pendingG.current !== null) {
        window.clearTimeout(pendingG.current);
        pendingG.current = null;
        const target = ALL_NAV.find((n) => n.key === e.key.toLowerCase());
        if (target) {
          e.preventDefault();
          navigate(target.to);
        }
        return;
      }
      if (e.key === 'g') {
        pendingG.current = window.setTimeout(() => (pendingG.current = null), 900);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [navigate]);
}
