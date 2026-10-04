'use client';

import { zodResolver } from '@hookform/resolvers/zod';
import { Archive, Copy, FilePlus2, Pencil, Send, UsersRound } from 'lucide-react';
import Link from 'next/link';
import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { Empty, ErrorNotice, PageHeading } from '@/components/ui';
import { api } from '@/lib/api';

const assignmentSchema = z.object({
  title: z.string().min(2).max(200),
  subject: z.string().min(1),
  course: z.string().optional(),
  section: z.string().optional(),
  description: z.string().optional(),
  instructions: z.string().optional(),
  status: z.enum(['draft', 'active']),
  rubric_title: z.string().optional(),
  rubric_criteria: z.string().optional(),
  start_date: z.string().optional(),
  due_date: z.string().optional(),
  max_marks: z.coerce.number().positive().max(25),
  allowed_file_types: z.string().min(1),
  max_file_size_mb: z.coerce.number().positive().max(100),
}).refine((values) => !values.start_date || !values.due_date || new Date(values.due_date) >= new Date(values.start_date), { message: 'Due date must be after the start date', path: ['due_date'] });
type AssignmentFields = z.infer<typeof assignmentSchema>;
type Assignment = { id: number; title: string; subject: string; subject_id?: number | null; course?: string | null; section?: string | null; description?: string | null; instructions?: string | null; start_date?: string | null; due_date?: string | null; max_marks: number; status: string; allowed_file_types: string[]; max_file_size: number };
type Subject = { id: number; code: string; name: string };
const defaults: AssignmentFields = { title: '', subject: '', course: '', section: '', description: '', instructions: '', start_date: '', due_date: '', max_marks: 25, status: 'draft', rubric_title: '', rubric_criteria: '', allowed_file_types: '.pdf, .docx, .pptx, .xlsx, .txt, .png, .jpg, .jpeg, .gif, .webp, .zip', max_file_size_mb: 10 };

export default function TeacherAssignmentsPage() {
  const [assignments, setAssignments] = useState<Assignment[]>([]);
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [saving, setSaving] = useState(false);
  const { register, handleSubmit, reset, formState: { errors } } = useForm<AssignmentFields>({ resolver: zodResolver(assignmentSchema), defaultValues: defaults });

  const reload = () => Promise.all([api<Assignment[]>('/api/v1/assignments'), api<Subject[]>('/api/v1/subjects')]).then(([items, subjectItems]) => { setAssignments(items); setSubjects(subjectItems); }).catch((requestError: Error) => setError(requestError.message));
  useEffect(() => { void reload(); }, []);

  const save = async (values: AssignmentFields) => {
    setSaving(true); setError(''); setNotice('');
    const body = {
      title: values.title, subject: values.subject, course: values.course || null, section: values.section || null,
      description: values.description || null, instructions: values.instructions || null,
      start_date: values.start_date || null, due_date: values.due_date || null, max_marks: values.max_marks,
      status: values.status,
      allowed_file_types: values.allowed_file_types.split(',').map((item) => item.trim().toLowerCase()).filter(Boolean).map((item) => item.startsWith('.') ? item : `.${item}`),
      max_file_size: Math.round(values.max_file_size_mb * 1024 * 1024),
    };
    try {
      const saved = editingId
        ? await api<Assignment>(`/api/v1/assignments/${editingId}`, { method: 'PATCH', body: JSON.stringify(body) })
        : await api<Assignment>('/api/v1/assignments', { method: 'POST', body: JSON.stringify(body) });
      const criteria = (values.rubric_criteria ?? '').split('\n').map((line) => {
        const splitAt = line.lastIndexOf(':');
        if (splitAt < 1) return null;
        const name = line.slice(0, splitAt).trim();
        const maximum_score = Number(line.slice(splitAt + 1).trim());
        return name && maximum_score > 0 ? { name, maximum_score } : null;
      }).filter((item): item is { name: string; maximum_score: number } => item !== null);
      if (criteria.length) {
        const total = criteria.reduce((sum, item) => sum + item.maximum_score, 0);
        if (total > values.max_marks) throw new Error('Rubric criteria total cannot exceed maximum marks.');
        await api(`/api/v1/assignments/${saved.id}/rubric`, { method: 'POST', body: JSON.stringify({ title: values.rubric_title || 'Assignment rubric', criteria }) });
      }
      setNotice(values.status === 'active' ? (editingId ? 'Assignment updated and published.' : 'Assignment published.') : 'Assignment saved as a draft.');
      setEditingId(null); reset(defaults); await reload();
    } catch (requestError) { setError((requestError as Error).message); }
    finally { setSaving(false); }
  };

  const edit = (item: Assignment) => {
    setEditingId(item.id);
    reset({ title: item.title, subject: item.subject, course: item.course ?? '', section: item.section ?? '', description: item.description ?? '', instructions: item.instructions ?? '', start_date: item.start_date?.slice(0, 16) ?? '', due_date: item.due_date?.slice(0, 16) ?? '', max_marks: item.max_marks, status: item.status === 'active' ? 'active' : 'draft', allowed_file_types: item.allowed_file_types.join(', '), max_file_size_mb: Math.round(item.max_file_size / 1048576) || 10 });
  };

  const setStatus = async (item: Assignment, status: string) => {
    try { await api(`/api/v1/assignments/${item.id}/status`, { method: 'PATCH', body: JSON.stringify({ status }) }); await reload(); }
    catch (requestError) { setError((requestError as Error).message); }
  };
  const duplicate = async (item: Assignment) => {
    try { await api(`/api/v1/assignments/${item.id}/duplicate`, { method: 'POST' }); await reload(); }
    catch (requestError) { setError((requestError as Error).message); }
  };

  return <div className="fade-up">
    <PageHeading eyebrow="Coursework · faculty" title="Assignments" description="Create coursework and follow each submission through review." action={<span className="rounded-full border border-emerald-200/15 bg-emerald-200/5 px-3 py-1.5 text-[10px] font-semibold tracking-[.1em] text-emerald-100">DEMO DATA</span>} />
    {error && <div className="mb-4"><ErrorNotice message={error} /></div>}{notice && <div role="status" className="mb-4 rounded-lg border border-emerald-200/20 bg-emerald-200/5 px-4 py-3 text-sm text-emerald-100">{notice}</div>}
    <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1.35fr)_minmax(330px,.65fr)]">
      <section className="surface rounded-xl p-4 sm:p-5"><div className="mb-4 flex items-center justify-between"><h2 className="text-sm font-semibold">Course assignments</h2><span className="text-xs text-slate-500">{assignments.length} total</span></div><div className="space-y-2">{assignments.map((item) => <article key={item.id} className="rounded-lg border border-white/7 bg-black/10 p-4"><div className="flex flex-wrap items-start justify-between gap-3"><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><h3 className="font-medium text-white">{item.title}</h3><span className={`rounded-full px-2 py-1 text-[9px] uppercase tracking-[.1em] ${item.status === 'active' ? 'bg-emerald-300/10 text-emerald-100' : item.status === 'archived' ? 'bg-slate-500/15 text-slate-400' : 'bg-amber-200/10 text-amber-100'}`}>{item.status}</span></div><p className="mt-1 text-xs text-slate-500">{item.course ?? item.subject}{item.section ? ` · Section ${item.section}` : ' · All students'} · {item.max_marks} marks</p><p className="mt-2 text-[11px] text-slate-400">Due {item.due_date ? new Date(item.due_date).toLocaleString() : 'not scheduled'} · {item.allowed_file_types.join(', ')}</p></div><Link href={`/teacher/assignments/${item.id}/submissions`} className="inline-flex shrink-0 items-center gap-1.5 rounded-md border border-cyan-200/20 px-2.5 py-2 text-[10px] text-cyan-100 hover:bg-cyan-200/5"><UsersRound size={13} /> Review submissions</Link></div><div className="mt-4 flex flex-wrap gap-2 border-t border-white/6 pt-3"><button type="button" onClick={() => edit(item)} className="inline-flex items-center gap-1.5 rounded-md px-2 py-1.5 text-[10px] text-slate-300 hover:bg-white/5"><Pencil size={12} /> Edit</button><button type="button" onClick={() => void duplicate(item)} className="inline-flex items-center gap-1.5 rounded-md px-2 py-1.5 text-[10px] text-slate-300 hover:bg-white/5"><Copy size={12} /> Duplicate</button>{item.status === 'active' ? <button type="button" onClick={() => void setStatus(item, 'archived')} className="inline-flex items-center gap-1.5 rounded-md px-2 py-1.5 text-[10px] text-amber-100 hover:bg-white/5"><Archive size={12} /> Archive</button> : <button type="button" onClick={() => void setStatus(item, 'active')} className="inline-flex items-center gap-1.5 rounded-md px-2 py-1.5 text-[10px] text-emerald-100 hover:bg-white/5"><Send size={12} /> Publish</button>}</div></article>)}{!assignments.length && <Empty title="No assignments yet" detail="Create the first course task using the form." />}</div></section>

      <section className="surface rounded-xl p-5"><div className="flex items-center gap-2"><span className="grid size-8 place-items-center rounded-lg bg-cyan-200/10 text-cyan-100"><FilePlus2 size={16} /></span><div><h2 className="text-sm font-semibold">{editingId ? 'Edit assignment' : 'New assignment'}</h2><p className="text-[10px] text-slate-500">{editingId ? `Editing #${editingId}` : 'Save privately or publish to students.'}</p></div></div>
        <form onSubmit={handleSubmit(save)} className="mt-5 space-y-3">
          <Field label="Title" error={errors.title?.message}><input {...register('title')} className="form-input" placeholder="Weekly reflection" /></Field>
          <div className="grid grid-cols-2 gap-3"><Field label="Subject" error={errors.subject?.message}><select {...register('subject')} className="form-input"><option value="">Choose subject</option>{subjects.map((subject) => <option key={subject.id} value={subject.name}>{subject.code} · {subject.name}</option>)}</select></Field><Field label="Course"><input {...register('course')} className="form-input" placeholder="Course code" /></Field></div>
          <div className="grid grid-cols-2 gap-3"><Field label="Section"><input {...register('section')} className="form-input" placeholder="All sections" /></Field><Field label="Maximum marks" error={errors.max_marks?.message}><input type="number" min="1" max="25" {...register('max_marks')} className="form-input" /></Field></div>
          <div className="grid grid-cols-2 gap-3"><Field label="Start date"><input type="datetime-local" {...register('start_date')} className="form-input" /></Field><Field label="Due date" error={errors.due_date?.message}><input type="datetime-local" {...register('due_date')} className="form-input" /></Field></div>
          <Field label="Description"><textarea {...register('description')} rows={2} className="form-input resize-y" placeholder="A short description for students" /></Field>
          <Field label="Instructions"><textarea {...register('instructions')} rows={3} className="form-input resize-y" placeholder="What should students submit?" /></Field>
          <Field label="Allowed file types"><input {...register('allowed_file_types')} className="form-input" placeholder=".pdf, .docx, .txt" /></Field>
          <Field label="Maximum upload size (MB)" error={errors.max_file_size_mb?.message}><input type="number" min="1" max="100" {...register('max_file_size_mb')} className="form-input" /></Field>
          <Field label="Rubric title (optional)"><input {...register('rubric_title')} className="form-input" placeholder="Reflection rubric" /></Field>
          <Field label="Rubric criteria · one per line, name:points"><textarea {...register('rubric_criteria')} rows={3} className="form-input resize-y" placeholder={'Reasoning: 12\nClarity: 8'} /></Field>
          <Field label="Publish status"><select {...register('status')} className="form-input"><option value="draft">Save as draft</option><option value="active">Publish to students</option></select></Field>
          <div className="flex gap-2 pt-2"><button disabled={saving} className="flex-1 rounded-lg bg-cyan-200 px-3 py-2.5 text-xs font-semibold text-[#07141b] hover:bg-cyan-100 disabled:opacity-60">{saving ? 'Saving…' : 'Save assignment'}</button>{editingId && <button type="button" onClick={() => { setEditingId(null); reset(defaults); }} className="rounded-lg border border-white/10 px-3 py-2.5 text-xs text-slate-300">Cancel</button>}</div>
        </form>
      </section>
    </div>
  </div>;
}

function Field({ label, error, children }: { label: string; error?: string; children: React.ReactNode }) {
  return <label className="block text-[11px] font-medium text-slate-400">{label}{children}{error && <span className="mt-1 block text-[10px] text-rose-200">{error}</span>}</label>;
}