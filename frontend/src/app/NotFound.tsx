import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/Button';

export default function NotFound() {
  return (
    <div className="mx-auto mt-28 max-w-md px-6">
      <p className="micro">Error 404</p>
      <h1 className="mt-2 text-2xl font-semibold">That page isn&apos;t in the estate map</h1>
      <p className="mt-2 text-sm text-fg-2">The route you followed doesn&apos;t exist. Use the sidebar or press ⌘K to jump to a module.</p>
      <Link to="/" className="mt-5 inline-block">
        <Button variant="primary">Back to overview</Button>
      </Link>
    </div>
  );
}
