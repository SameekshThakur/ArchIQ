import { ExternalLink } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { IconButton } from '@/components/ui/Button';
import { Drawer } from '@/components/ui/Overlay';
import { useUI } from '@/store/ui';
import { Conversation } from './Conversation';

/** ⌘J slide-over: same conversation as the Copilot page, available from anywhere. */
export default function CopilotDrawer() {
  const open = useUI((s) => s.copilotOpen);
  const set = useUI((s) => s.setCopilotOpen);
  const nav = useNavigate();
  return (
    <Drawer
      open={open}
      onOpenChange={set}
      title="Copilot"
      subtitle="Ask about the estate · ⌘J to toggle"
      width={560}
      actions={<IconButton label="Open full page" size="sm" onClick={() => { set(false); nav('/copilot'); }}><ExternalLink className="h-4 w-4" /></IconButton>}
    >
      <div className="-mx-5 -my-4 h-[calc(100vh-86px)]"><Conversation compact /></div>
    </Drawer>
  );
}
