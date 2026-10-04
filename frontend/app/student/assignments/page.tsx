'use client';

import { CheckCircle2, Clock3, FileUp, UploadCloud } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { Empty, ErrorNotice, PageHeading } from '@/components/ui';
import { getAssignmentStatus } from '@/lib/academic';
import { api } from '@/lib/api';

type Assignment = { id: number; title: string; subject: string; course?: string | null; description?: string | null; instructions?: string | null; due_date?: string | null; max_marks: number; status: string; allowed_file_types: string[]; max_file_size: number };
type Submission = { id: number; assignment_id: number; status: string; page_count: number; file_name?: string | null; submitted_at?: string | null; grade?: number | null; feedback?: string | null };
type View = 'All' | 'Active' | 'Pending' | 'Submitted' | 'Late' | 'Completed';
const views: View[] = ['All', 'Active', 'Pending', 'Submitted', 'Late', 'Completed'];

export default function StudentAssignmentsPage() {
  const [assignments, setAssignments] = useState<Assignment[]>([]);
  const [submissions, setSubmissions] = useState<Submission[]>([]);
  const [view, setView] = useState<View>('All');
  const [files, setFiles] = useState<Record<number, File[]>>({});
  const [busy, setBusy] = useState<number | null>(null);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  const reload = () => Promise.all([api<Assignment[]>('/api/v1/assignments'), api<Submission[]>('/api/v1/submissions')]).then(([tasks, work]) => { setAssignments(tasks); setSubmissions(work); }).catch((requestError: Error) => setError(requestError.message));
  useEffect(() => { void reload(); }, []);
  const filtered = useMemo(() => assignments.filter((assignment) => {
    const submission = submissions.find((item) => item.assignment_id === assignment.id);
    const status = getAssignmentStatus(assignment.status, submission?.status);
    return view === 'All' || (view === 'Active' && assignment.status === 'active') || status === view;
  }), [assignments, submissions, view]);

  const upload = async (assignment: Assignment) => {
    const pages = files[assignment.id] ?? [];
    if (!pages.length) { setError('Choose at least one file before submitting.'); return; }
    setBusy(assignment.id); setError(''); setMessage('');
    const form = new FormData();
    form.append('assignment_id', String(assignment.id));
    pages.forEach((page) => form.append('files', page));
    try {
      await api('/api/v1/submissions', { method: 'POST', body: form });
      setMessage(`“${assignment.title}” was submitted.`);
      setFiles((current) => ({ ...current, [assignment.id]: [] }));
      await reload();
    } catch (requestError) { setError((requestError as Error).message); }
    finally { setBusy(null); }
  };

  return <div className="fade-up">
    <PageHeading eyebrow="Your coursework" title="Assignments" description="See what is due, submit your work, and follow feedback." action={<span className="rounded-full border border-emerald-200/15 bg-emerald-200/5 px-3 py-1.5 text-[10px] font-semibold tracking-[.1em] text-emerald-100">DEMO DATA</span>} />
    {error && <div className="mb-4"><ErrorNotice message={error} /></div>}{message && <div role="status" className="mb-4 rounded-lg border border-emerald-200/20 bg-emerald-200/5 px-4 py-3 text-sm text-emerald-100">{message}</div>}
    <div className="mb-4 flex gap-1 overflow-x-auto border-b border-white/10">{views.map((item) => <button key={item} onClick={() => setView(item)} className={`whitespace-nowrap border-b-2 px-3 py-3 text-xs ${view === item ? 'border-cyan-200 text-cyan-100' : 'border-transparent text-slate-500 hover:text-white'}`}>{item}</button>)}</div>
    <div className="grid gap-3 xl:grid-cols-2">{filtered.map((assignment) => {
      const submission = submissions.find((item) => item.assignment_id === assignment.id);
      const status = getAssignmentStatus(assignment.status, submission?.status);
      const canReplace = submission?.status !== 'graded';
      return <article key={assignment.id} className="surface rounded-xl p-5"><div className="flex items-start justify-between gap-4"><div><div className="text-[10px] uppercase tracking-[.12em] text-cyan-200">{assignment.course ?? assignment.subject}</div><h2 className="mt-1 text-lg font-semibold text-white">{assignment.title}</h2><p className="mt-2 text-xs leading-5 text-slate-400">{assignment.description ?? assignment.instructions ?? 'No further instructions have been added.'}</p></div><span className={`shrink-0 rounded-full border px-2.5 py-1 text-[10px] ${status === 'Completed' ? 'border-emerald-200/20 bg-emerald-200/5 text-emerald-100' : status === 'Late' ? 'border-rose-200/20 bg-rose-200/5 text-rose-100' : status === 'Submitted' ? 'border-cyan-200/20 bg-cyan-200/5 text-cyan-100' : 'border-amber-100/20 bg-amber-100/5 text-amber-100'}`}>{status}</span></div>
        <div className="mt-4 grid grid-cols-2 gap-3 border-y border-white/7 py-3 text-xs"><div><span className="text-slate-500">Due</span><div className="mt-1 text-slate-200">{assignment.due_date ? new Date(assignment.due_date).toLocaleString() : 'No due date'}</div></div><div><span className="text-slate-500">Marks</span><div className="mt-1 text-slate-200">{submission?.grade == null ? `Up to ${assignment.max_marks}` : `${submission.grade} / ${assignment.max_marks}`}</div></div></div>
        {submission && <div className="mt-3 rounded-lg bg-black/10 px-3 py-2.5"><div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-slate-400"><CheckCircle2 size={13} className="text-cyan-200" />{submission.file_name ?? 'Submission'}<span>·</span>{submission.page_count} page file(s)<span>·</span><Clock3 size={12} />{submission.submitted_at ? new Date(submission.submitted_at).toLocaleString() : 'Timestamp unavailable'}</div>{submission.feedback && <p className="mt-2 border-t border-white/7 pt-2 text-xs leading-5 text-slate-300">{submission.feedback}</p>}</div>}
        {canReplace && assignment.status === 'active' && <div className="mt-4 flex flex-wrap items-center gap-2"><label className="flex min-w-0 flex-1 cursor-pointer items-center gap-2 rounded-lg border border-white/10 bg-black/10 px-3 py-2 text-xs text-slate-300 hover:border-cyan-200/20"><FileUp size={15} className="shrink-0 text-cyan-200" /><span className="truncate">{files[assignment.id]?.length ? `${files[assignment.id].length} page file(s) selected` : 'Choose one or more submission pages'}</span><input type="file" multiple accept={assignment.allowed_file_types.join(',')} onChange={(event) => setFiles((current) => ({ ...current, [assignment.id]: Array.from(event.target.files ?? []) }))} className="sr-only" /></label><button type="button" disabled={busy === assignment.id} onClick={() => void upload(assignment)} className="inline-flex items-center gap-2 rounded-lg bg-cyan-200 px-3 py-2.5 text-xs font-semibold text-[#07141b] disabled:opacity-50"><UploadCloud size={14} />{busy === assignment.id ? 'Uploading…' : submission ? 'Replace files' : 'Submit'}</button></div>}
        <p className="mt-3 text-[10px] text-slate-600">Accepted: {assignment.allowed_file_types.join(', ')} · Limit {Math.round(assignment.max_file_size / 1048576)} MB</p>
      </article>;
    })}</div>
    {!filtered.length && <div className="surface rounded-xl p-5"><Empty title="No assignments in this view" detail="New published coursework will appear here." /></div>}
  </div>;
}