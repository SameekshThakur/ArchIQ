import { Kbd } from '@/components/ui/Button';
import { Modal } from '@/components/ui/Overlay';
import { useUI } from '@/store/ui';
import { ALL_NAV } from './nav';

const GENERAL: { keys: string[]; label: string }[] = [
  { keys: ['⌘', 'K'], label: 'Command palette' },
  { keys: ['⌘', 'J'], label: 'Toggle Copilot' },
  { keys: ['/'], label: 'Focus search' },
  { keys: ['?'], label: 'Show this cheat-sheet' },
  { keys: ['Esc'], label: 'Close drawer or dialog' },
];

export function ShortcutsModal() {
  const open = useUI((s) => s.shortcutsOpen);
  const set = useUI((s) => s.setShortcutsOpen);
  return (
    <Modal open={open} onOpenChange={set} title="Keyboard shortcuts" description="Press g, then a letter, to jump between modules." width={640}>
      <div className="grid grid-cols-2 gap-x-8 gap-y-6">
        <section>
          <h3 className="micro mb-2">General</h3>
          <ul className="space-y-2">
            {GENERAL.map((s) => (
              <li key={s.label} className="flex items-center justify-between text-sm">
                <span className="text-fg-2">{s.label}</span>
                <span className="flex gap-1">{s.keys.map((k, i) => <Kbd key={`${k}-${i}`}>{k}</Kbd>)}</span>
              </li>
            ))}
          </ul>
        </section>
        <section>
          <h3 className="micro mb-2">Go to</h3>
          <ul className="space-y-2">
            {ALL_NAV.map((n) => (
              <li key={n.to} className="flex items-center justify-between text-sm">
                <span className="text-fg-2">{n.label}</span>
                <span className="flex gap-1"><Kbd>g</Kbd><Kbd>{n.key}</Kbd></span>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </Modal>
  );
}
