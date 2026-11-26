import { useSearchParams } from 'react-router-dom';
import { Conversation } from './Conversation';

export default function CopilotPage() {
  const [params] = useSearchParams();
  return (
    <div className="mx-auto flex h-full max-w-[1100px] flex-col">
      <header className="px-6 pb-1 pt-6">
        <h1 className="text-xl font-semibold text-fg">Architecture Copilot</h1>
        <p className="mt-1 text-sm text-fg-2">Natural-language questions answered from the graph, with the path or evidence behind every claim.</p>
      </header>
      <div className="min-h-0 flex-1"><Conversation autoQuery={params.get('q')} /></div>
    </div>
  );
}
