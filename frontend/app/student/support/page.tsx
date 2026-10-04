'use client';

import { BookOpen, ExternalLink, Search } from 'lucide-react';
import { FormEvent, useEffect, useState } from 'react';
import { Empty, ErrorNotice, PageHeading } from '@/components/ui';
import { api } from '@/lib/api';

type Resource = { source: string; chunk_index: number; text: string; score: number };
type SearchResult = { matched: boolean; message: string; embedding_provider?: string; sources: Resource[] };

export default function StudentSupportPage() {
  const [query, setQuery] = useState('academic study support mentoring');
  const [result, setResult] = useState<SearchResult | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const search = async (event?: FormEvent) => {
    event?.preventDefault(); setLoading(true); setError('');
    try { setResult(await api<SearchResult>(`/api/v1/support/resources?query=${encodeURIComponent(query)}`)); }
    catch (requestError) { setError((requestError as Error).message); }
    finally { setLoading(false); }
  };
  useEffect(() => {
    api<SearchResult>(`/api/v1/support/resources?query=${encodeURIComponent('academic study support mentoring')}`)
      .then(setResult)
      .catch((requestError: Error) => setError(requestError.message));
  }, []);
  return <div className="fade-up"><PageHeading eyebrow="Academic support" title="Find a resource" description="Search the indexed institutional materials. Results cite their source; policies are never guessed." />
    <form onSubmit={search} className="surface mb-5 flex gap-2 rounded-xl p-3"><label className="relative flex-1"><span className="sr-only">Search support resources</span><Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" /><input value={query} onChange={(event) => setQuery(event.target.value)} className="form-input mt-0 h-11 pl-9" placeholder="Search study support, mentoring, or resources" /></label><button disabled={loading} className="rounded-lg bg-cyan-200 px-4 text-xs font-semibold text-[#07141b] disabled:opacity-50">{loading ? 'Searching…' : 'Search'}</button></form>
    {error && <ErrorNotice message={error} />}
    {result && <><div className={`mb-4 rounded-lg border px-4 py-3 text-xs ${result.matched ? 'border-emerald-200/15 bg-emerald-200/[.035] text-emerald-100' : 'border-amber-100/15 bg-amber-100/[.035] text-amber-100'}`}>{result.message || `${result.sources.length} source excerpts found.`}{result.embedding_provider && <span className="ml-2 text-slate-500">· {result.embedding_provider}</span>}</div><div className="grid gap-3 lg:grid-cols-2">{result.sources.map((item, index) => <article key={`${item.source}-${item.chunk_index}`} className="surface rounded-xl p-5"><div className="flex items-center justify-between"><div className="flex items-center gap-2 text-xs font-medium text-slate-200"><BookOpen size={14} className="text-cyan-200" />{item.source}</div><span className="text-[10px] text-slate-500">Source {index + 1} · {item.score.toFixed(2)}</span></div><p className="mt-3 text-xs leading-6 text-slate-400">{item.text}</p><div className="mt-4 flex items-center gap-1 border-t border-white/7 pt-3 text-[10px] text-slate-600"><ExternalLink size={11} /> Institutional source excerpt</div></article>)}</div>{!result.sources.length && <div className="surface rounded-xl p-5"><Empty title="No matching institutional source" detail="This workspace has no approved support materials yet. Contact your advisor or faculty support team." /></div>}</>}
  </div>;
}