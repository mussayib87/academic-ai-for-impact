'use client';

import { Check, Pencil, Sparkles, WandSparkles } from 'lucide-react';
import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { Empty, ErrorNotice, PageHeading, RiskBadge } from '@/components/ui';

type Student = { id: number; full_name: string; risk_level: string };
type Draft = { id: number; student_id: number; title: string; body: string; status: string; provider?: string | null; evidence?: Record<string, unknown> };

function formatProviderError(message: string): string {
  const cleaned = message.replace(/<.*?>/g, ' ').replace(/\s+/g, ' ').trim();
  if (!cleaned) return 'Local AI service is unavailable.';
  if (/ollama.*not reachable|service is not reachable|Local AI service is unavailable|no connection could be made/i.test(cleaned)) {
    return 'Local AI service is unavailable.\nOllama is not currently reachable at http://127.0.0.1:11434.\nVerify that Ollama is running and that qwen3:8b is installed.';
  }
  if (/model.*not available|not installed|pull .*qwen3:8b|qwen3:8b.*missing/i.test(cleaned)) {
    return 'Local AI service is available, but the required model is missing.\nVerify that qwen3:8b is installed in Ollama.';
  }
  if (/timed out|timeout/i.test(cleaned)) {
    return 'The local model timed out while generating the draft.\nPlease retry the request or increase the LLM timeout.';
  }
  return cleaned;
}

export default function InterventionsPage() {
  const [students, setStudents] = useState<Student[]>([]);
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [editing, setEditing] = useState<Record<number, { title: string; body: string }>>({});
  const [busy, setBusy] = useState<number | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const reload = async () => {
    const [directory, items] = await Promise.all([api<{ items: Student[] }>('/api/v1/students?limit=100'), api<Draft[]>('/api/v1/interventions')]);
    setStudents(directory.items); setDrafts(items);
  };
  useEffect(() => { reload().catch((requestError: Error) => setError(formatProviderError(requestError.message))); }, []);
  const generate = async (student: Student) => {
    setBusy(student.id); setError(''); setNotice('');
    try { await api('/api/v1/interventions/generate', { method: 'POST', body: JSON.stringify({ student_id: student.id }) }); setNotice('Draft generated from model, SHAP, dated momentum, and available sources. Faculty review is required.'); await reload(); }
    catch (requestError) { setError(formatProviderError((requestError as Error).message)); }
    finally { setBusy(null); }
  };
  const saveEdit = async (draft: Draft) => {
    const value = editing[draft.id] ?? { title: draft.title, body: draft.body };
    try { await api(`/api/v1/interventions/${draft.id}`, { method: 'PATCH', body: JSON.stringify(value) }); setNotice('Faculty edits saved.'); await reload(); }
    catch (requestError) { setError((requestError as Error).message); }
  };
  const approve = async (draft: Draft) => {
    try { await api(`/api/v1/interventions/${draft.id}/approve`, { method: 'POST' }); setNotice('Faculty-approved support message stored and delivered as an in-app notification.'); await reload(); }
    catch (requestError) { setError((requestError as Error).message); }
  };

  return <div className="fade-up"><PageHeading eyebrow="Faculty review · AI-assisted" title="Interventions" description="Every generated message remains a draft until you review and approve it." />
    {error && <div className="mb-4"><ErrorNotice message={error} /></div>}{notice && <div role="status" className="mb-4 rounded-lg border border-emerald-200/20 bg-emerald-200/5 p-3 text-xs text-emerald-100">{notice}</div>}
    <section className="surface mb-5 rounded-xl p-5"><div className="flex items-center gap-2"><WandSparkles size={16} className="text-cyan-100" /><h2 className="text-sm font-semibold">Students to consider</h2></div><div className="mt-3 flex flex-wrap gap-2">{students.filter((item) => item.risk_level !== 'LOW').slice(0, 20).map((student) => <div key={student.id} className="flex items-center gap-2 rounded-lg border border-white/8 px-3 py-2"><span className="text-xs text-slate-200">{student.full_name}</span><RiskBadge level={student.risk_level} /><button disabled={busy === student.id} onClick={() => void generate(student)} title={`Generate draft for ${student.full_name}`} className="grid size-7 place-items-center rounded-md text-cyan-100 hover:bg-cyan-200/10 disabled:opacity-40"><Sparkles size={14} /></button></div>)}</div></section>
    <div className="space-y-3">{drafts.map((draft) => <article key={draft.id} className="surface rounded-xl p-5"><div className="flex flex-wrap items-start justify-between gap-3"><div><div className="eyebrow">AI-generated draft · faculty review required</div><h2 className="mt-1 text-base font-semibold text-white">{draft.title}</h2><p className="mt-1 text-[10px] text-slate-500">Student record {draft.student_id} · Provider: {draft.provider ?? 'DEMO DATA'}</p></div><span className={`rounded-full px-2.5 py-1 text-[10px] ${draft.status === 'approved' ? 'bg-emerald-200/10 text-emerald-100' : 'bg-amber-100/10 text-amber-100'}`}>{draft.status}</span></div>
        {draft.status === 'draft' ? <div className="mt-4 grid gap-3"><label className="text-[10px] text-slate-500">Draft title<input value={editing[draft.id]?.title ?? draft.title} onChange={(event) => setEditing((current) => ({ ...current, [draft.id]: { title: event.target.value, body: current[draft.id]?.body ?? draft.body } }))} className="form-input" /></label><label className="text-[10px] text-slate-500">Draft text<textarea rows={5} value={editing[draft.id]?.body ?? draft.body} onChange={(event) => setEditing((current) => ({ ...current, [draft.id]: { title: current[draft.id]?.title ?? draft.title, body: event.target.value } }))} className="form-input resize-y" /></label><div className="flex flex-wrap gap-2"><button onClick={() => void saveEdit(draft)} className="inline-flex items-center gap-2 rounded-lg border border-white/10 px-3 py-2 text-xs text-slate-200"><Pencil size={13} /> Save faculty edits</button><button onClick={() => void approve(draft)} className="inline-flex items-center gap-2 rounded-lg bg-emerald-200 px-3 py-2 text-xs font-semibold text-[#07170f]"><Check size={14} /> Approve & notify student</button></div></div> : <div className="mt-4 whitespace-pre-wrap rounded-lg border border-white/7 bg-black/10 p-4 text-xs leading-6 text-slate-300">{draft.body}</div>}
        {draft.evidence && <details className="mt-3 text-[10px] text-slate-500"><summary className="cursor-pointer">Review evidence and source record</summary><pre className="mt-2 max-h-64 overflow-auto rounded-md bg-black/20 p-3 text-[9px]">{JSON.stringify(draft.evidence, null, 2)}</pre></details>}
      </article>)}{!drafts.length && <div className="surface rounded-xl p-5"><Empty title="No intervention drafts" detail="Generate a draft from a student record when a faculty follow-up is appropriate." /></div>}</div>
  </div>;
}