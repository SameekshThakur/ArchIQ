import { ArrowLeft } from 'lucide-react';
import { Link, useParams } from 'react-router-dom';
import { useGet } from '@/api/hooks';
import { Badge } from '@/components/ui/Badge';
import { Page } from '@/components/ui/PageHeader';
import { fmtDate, titleCase } from '@/lib/format';
import { ReviewDetail, type ReviewData } from './ReviewDetail';

export default function ReviewPage() {
  const { id } = useParams();
  const { data, isLoading, isError, error } = useGet<ReviewData>(`/reviews/${id}`);
  const s = data?.submission;
  return (
    <Page>
      <Link to="/reviews" className="mb-3 inline-flex items-center gap-1.5 text-xs text-fg-3 hover:text-fg"><ArrowLeft className="h-3.5 w-3.5" aria-hidden />All reviews</Link>
      <header className="mb-5">
        <div className="flex flex-wrap items-center gap-2"><h1 className="text-xl font-semibold text-fg">{s?.title ?? id}</h1>{s && <Badge>{titleCase(s.stage)}</Badge>}</div>
        <p className="mt-1 max-w-3xl text-sm text-fg-2">{s?.summary}</p>
        {s && <p className="mt-1 text-xs text-fg-3">{s.id} · submitted by {s.submitter} on {s.submitted_at && fmtDate(s.submitted_at)} · ARB {s.arb_date && fmtDate(s.arb_date)}</p>}
      </header>
      {isError ? <p role="alert" className="rounded border border-critical/30 bg-critical/10 px-4 py-3 text-sm text-critical">{error.message}</p> : <ReviewDetail data={data} loading={isLoading} />}
    </Page>
  );
}
