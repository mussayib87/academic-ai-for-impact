'use client';

import { History, Search, Send } from 'lucide-react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { ErrorNotice, PageHeading, RiskBadge } from '@/components/ui';
import { API_BASE, api, readToken } from '@/lib/api';

type Student = { id: number; student_id: string; name: string; department?: string | null; section?: string | null; uploaded: boolean; status: string; pages: number; submitted_at: string | null; deadline: string | null; grade: number | null; submission_id: number | null };
type AssignmentSummary = { assignment: { id: number; title: string; subject: string; max_marks: number }; counts: Record<'assigned' | 'submitted' | 'pending' | 'not_submitted' | 'late' | 'graded', number>; students: Student[] };
type Submission = { id: number; student_id: number; assignment_id: number; status: string; file_name?: string; submitted_at?: string | null; grade?: number | null; feedback?: string | null };
type Rubric = { id: number; title: string; criteria: { id: number; name: string; maximum_score: number }[] };
type Version = { id: number; version_number: number; page_number: number; page_count: number; file_name: string; submitted_at: string };
type Filter = 'All' | 'Submitted' | 'Pending' | 'Not Submitted' | 'Late' | 'Graded';

export default function SubmissionReviewPage() {
  const { assignmentId } = useParams<{ assignmentId: string }>();
  const [summary, setSummary] = useState<AssignmentSummary | null>(null);
  const [submissions, setSubmissions] = useState<Submission[]>([]);
  const [rubric, setRubric] = useState<Rubric | null>(null);
  const [filter, setFilter] = useState<Filter>('All');
  const [search, setSearch] = useState('');
  const [departmentFilter, setDepartmentFilter] = useState('');
  const [sectionFilter, setSectionFilter] = useState('');
  const [gradeFilter, setGradeFilter] = useState('');
  const [dateFilter, setDateFilter] = useState('all');
  const [sortBy, setSortBy] = useState<'name' | 'usn' | 'date' | 'grade'>('name');
  const [selected, setSelected] = useState<number[]>([]);
  const [grades, setGrades] = useState<Record<number, string>>({});
  const [feedback, setFeedback] = useState<Record<number, string>>({});
  const [scores, setScores] = useState<Record<number, Record<number, string>>>({});
  const [versions, setVersions] = useState<Record<number, Version[]>>({});
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const reload = useCallback(async () => {
    const [counts, rows] = await Promise.all([
      api<AssignmentSummary>(`/api/v1/assignments/${assignmentId}/summary`),
      api<Submission[]>(`/api/v1/assignments/${assignmentId}/submissions`),
    ]);
    setSummary(counts); setSubmissions(rows);
    api<Rubric>(`/api/v1/assignments/${assignmentId}/rubric`).then(setRubric).catch(() => setRubric(null));
  }, [assignmentId]);
  useEffect(() => { reload().catch((requestError: Error) => setError(requestError.message)); }, [reload]);

  const pendingStudents = summary?.students.filter((student) => !student.uploaded) ?? [];
  const normalizedSearch = search.trim().toLowerCase();
  const filteredRoster = summary?.students.filter((student) => {
    const matchesSearch = !normalizedSearch || `${student.name} ${student.student_id}`.toLowerCase().includes(normalizedSearch);
    const matchesStatus = filter === 'All' || (filter === 'Pending' || filter === 'Not Submitted' ? !student.uploaded : student.status.toLowerCase() === filter.toLowerCase());
    const matchesDepartment = !departmentFilter || student.department === departmentFilter;
    const matchesSection = !sectionFilter || student.section === sectionFilter;
    const matchesGrade = !gradeFilter || (gradeFilter === 'graded' ? student.grade != null : student.grade == null);
    const days = Number(dateFilter);
    const matchesDate = dateFilter === 'all' || (!!student.submitted_at && Date.now() - new Date(student.submitted_at).getTime() <= days * 86400000);
    return matchesSearch && matchesStatus && matchesDepartment && matchesSection && matchesGrade && matchesDate;
  }).sort((left, right) => {
    if (sortBy === 'usn') return left.student_id.localeCompare(right.student_id);
    if (sortBy === 'date') return (right.submitted_at ?? '').localeCompare(left.submitted_at ?? '');
    if (sortBy === 'grade') return (right.grade ?? -1) - (left.grade ?? -1);
    return left.name.localeCompare(right.name);
  }) ?? [];
  const filtered = submissions.filter((item) => filter !== 'Not Submitted' && (filter === 'All' || item.status.toLowerCase() === filter.toLowerCase()));
  const getName = (studentId: number) => summary?.students.find((student) => student.id === studentId);

  const grade = async (submission: Submission) => {
    setError(''); setNotice('');
    const rubricScores = rubric?.criteria.reduce<Record<number, number>>((result, criterion) => {
      const raw = scores[submission.id]?.[criterion.id];
      if (raw !== undefined && raw !== '') result[criterion.id] = Number(raw);
      return result;
    }, {}) ?? {};
    const body = { grade: Number(grades[submission.id] ?? 0), feedback: feedback[submission.id] ?? '', rubric_scores: rubricScores };
    try {
      await api(`/api/v1/submissions/${submission.id}/grade`, { method: 'PATCH', body: JSON.stringify(body) });
      setNotice(`Grade saved for ${getName(submission.student_id)?.name ?? 'student'}.`);
      await reload();
    } catch (requestError) { setError((requestError as Error).message); }
  };

  const remind = async () => {
    if (!selected.length) return;
    try {
      const result = await api<{ reminders_created: number }>(`/api/v1/assignments/${assignmentId}/reminders`, { method: 'POST', body: JSON.stringify(selected) });
      setNotice(`${result.reminders_created} reminders created.`); setSelected([]);
    } catch (requestError) { setError((requestError as Error).message); }
  };

  const loadVersions = async (submissionId: number) => {
    try {
      const result = await api<Version[]>(`/api/v1/submissions/${submissionId}/versions`);
      setVersions((current) => ({ ...current, [submissionId]: result }));
    }
    catch (requestError) { setError((requestError as Error).message); }
  };

  const openVersion = async (submissionId: number, versionId: number) => {
    try {
      const response = await fetch(`${API_BASE}/api/v1/submissions/${submissionId}/versions/${versionId}/file`, { headers: { Authorization: `Bearer ${readToken() ?? ''}` } });
      if (!response.ok) throw new Error('Submission page is not available.');
      const objectUrl = URL.createObjectURL(await response.blob());
      window.open(objectUrl, '_blank', 'noopener,noreferrer');
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60000);
    } catch (requestError) { setError((requestError as Error).message); }
  };

  if (!summary) return error ? <ErrorNotice message={error} /> : <div className="skeleton h-80 rounded-xl" />;
  return <div className="fade-up">
    <Link href="/teacher/assignments" className="mb-4 inline-block text-xs text-slate-500 hover:text-cyan-200">← Assignments</Link>
    <PageHeading eyebrow="Submission review" title={summary.assignment.title} description={`${summary.assignment.subject} · up to ${summary.assignment.max_marks} marks`} />
    {error && <div className="mb-4"><ErrorNotice message={error} /></div>}{notice && <div role="status" className="mb-4 rounded-lg border border-emerald-200/20 bg-emerald-200/5 p-3 text-sm text-emerald-100">{notice}</div>}
    <section className="mb-5 grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-6">{(['assigned', 'submitted', 'pending', 'not_submitted', 'late', 'graded'] as const).map((item) => <div key={item} className="surface rounded-lg p-3"><div className="text-[10px] uppercase tracking-[.1em] text-slate-500">{item.replace('_', ' ')}</div><div className="mt-2 text-2xl font-semibold text-white">{summary.counts[item]}</div></div>)}</section>
    <section className="surface rounded-xl p-4 sm:p-5"><div className="flex flex-wrap items-center justify-between gap-3"><div className="flex gap-1 overflow-x-auto">{(['All', 'Submitted', 'Pending', 'Not Submitted', 'Late', 'Graded'] as const).map((item) => <button key={item} onClick={() => setFilter(item)} className={`rounded-md px-3 py-2 text-xs ${filter === item ? 'bg-white/10 text-white' : 'text-slate-500 hover:text-slate-200'}`}>{item}</button>)}</div><button disabled={!selected.length} onClick={() => void remind()} className="inline-flex items-center gap-2 rounded-lg border border-amber-100/20 px-3 py-2 text-xs text-amber-100 disabled:opacity-40"><Send size={13} /> Remind selected ({selected.length})</button></div>
      <div className="mt-4 overflow-x-auto border-y border-white/8"><div className="flex flex-wrap items-center gap-2 py-3"><h2 className="mr-auto text-xs font-semibold text-slate-200">Enrolled students · {filteredRoster.length}</h2><label className="relative w-full sm:w-56"><Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" /><input value={search} onChange={(event) => setSearch(event.target.value)} className="form-input pl-8" placeholder="Search name or USN" /></label><select aria-label="Filter department" value={departmentFilter} onChange={(event) => setDepartmentFilter(event.target.value)} className="form-input w-auto"><option value="">All departments</option>{Array.from(new Set(summary.students.map((item) => item.department).filter((value): value is string => Boolean(value)))).map((value) => <option key={value}>{value}</option>)}</select><select aria-label="Filter section" value={sectionFilter} onChange={(event) => setSectionFilter(event.target.value)} className="form-input w-auto"><option value="">All sections</option>{Array.from(new Set(summary.students.map((item) => item.section).filter((value): value is string => Boolean(value)))).map((value) => <option key={value}>{value}</option>)}</select><select aria-label="Filter grade" value={gradeFilter} onChange={(event) => setGradeFilter(event.target.value)} className="form-input w-auto"><option value="">Any grade</option><option value="graded">Graded</option><option value="ungraded">Ungraded</option></select><select aria-label="Filter submission date" value={dateFilter} onChange={(event) => setDateFilter(event.target.value)} className="form-input w-auto"><option value="all">Any submission date</option><option value="7">Last 7 days</option><option value="30">Last 30 days</option></select><select aria-label="Sort roster" value={sortBy} onChange={(event) => setSortBy(event.target.value as typeof sortBy)} className="form-input w-auto"><option value="name">Sort: name</option><option value="usn">Sort: USN</option><option value="date">Sort: submitted date</option><option value="grade">Sort: grade</option></select>{filter === 'All' || filter === 'Pending' || filter === 'Not Submitted' ? <button onClick={() => setSelected(selected.length === pendingStudents.length ? [] : pendingStudents.map((item) => item.id))} className="text-[10px] text-cyan-200">{selected.length === pendingStudents.length ? 'Clear selection' : 'Select not submitted'}</button> : null}</div><table className="w-full min-w-[1050px] text-left text-xs"><thead className="text-[10px] uppercase text-slate-500"><tr>{['Student', 'USN', 'Department', 'Section', 'Subject', 'Assignment', 'Uploaded', 'Pages', 'Status', 'Submitted', 'Deadline', 'Grade /25', 'Remind'].map((label) => <th key={label} className="px-2 py-2">{label}</th>)}</tr></thead><tbody>{filteredRoster.map((student) => <tr key={student.id} className="border-t border-white/6"><td className="px-2 py-2 text-slate-200">{student.name}</td><td className="px-2 py-2 font-mono text-slate-500">{student.student_id}</td><td className="px-2 py-2 text-slate-400">{student.department ?? '—'}</td><td className="px-2 py-2 text-slate-400">{student.section ?? '—'}</td><td className="px-2 py-2 text-slate-400">{summary.assignment.subject}</td><td className="px-2 py-2 text-slate-300">{summary.assignment.title}</td><td className="px-2 py-2 text-slate-400">{student.uploaded ? 'Yes' : 'No'}</td><td className="px-2 py-2 text-slate-400">{student.pages}</td><td className="px-2 py-2 capitalize text-slate-300">{student.status.replaceAll('_', ' ')}</td><td className="px-2 py-2 text-slate-500">{student.submitted_at ? new Date(student.submitted_at).toLocaleString() : '—'}</td><td className="px-2 py-2 text-slate-500">{student.deadline ? new Date(student.deadline).toLocaleString() : '—'}</td><td className="px-2 py-2 text-slate-400">{student.grade == null ? '—' : student.grade}</td><td className="px-2 py-2">{!student.uploaded && <input aria-label={`Select reminder for ${student.student_id}`} type="checkbox" checked={selected.includes(student.id)} onChange={(event) => setSelected((current) => event.target.checked ? [...current, student.id] : current.filter((id) => id !== student.id))} />}</td></tr>)}</tbody></table></div>
      <div className="mt-4 space-y-3">{filtered.map((submission) => {
        const student = getName(submission.student_id);
        return <article key={submission.id} className="rounded-lg border border-white/7 bg-black/10 p-4"><div className="flex flex-wrap items-start justify-between gap-3"><div><h3 className="text-sm font-medium text-white">{student?.name ?? `Student ${submission.student_id}`}</h3><p className="mt-1 font-mono text-[10px] text-slate-500">{student?.student_id ?? submission.student_id} · {submission.submitted_at ? new Date(submission.submitted_at).toLocaleString() : 'Timestamp unavailable'}</p></div><span className={`rounded-full px-2.5 py-1 text-[10px] ${submission.status === 'graded' ? 'bg-emerald-300/10 text-emerald-100' : submission.status === 'late' ? 'bg-rose-300/10 text-rose-100' : 'bg-cyan-200/10 text-cyan-100'}`}>{submission.status}</span></div>
          <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-white/6 pt-3"><span className="mr-auto text-xs text-slate-300">{submission.file_name ?? 'No file'}</span>{submission.file_name && <button onClick={() => void loadVersions(submission.id)} className="inline-flex items-center gap-1.5 rounded-md border border-white/10 px-2.5 py-2 text-[10px] text-slate-300"><History size={13} /> Review pages / history</button>}</div>
          {versions[submission.id] && <div className="mt-2 flex flex-wrap gap-2">{versions[submission.id].map((version) => <button key={version.id} onClick={() => void openVersion(submission.id, version.id)} className="rounded bg-white/5 px-2 py-1 text-[10px] text-cyan-100 hover:bg-white/10">Page {version.page_number}/{version.page_count} · v{version.version_number} · {version.file_name}</button>)}</div>}
          {submission.status !== 'graded' && <div className="mt-4 grid gap-3 border-t border-white/6 pt-4 lg:grid-cols-[.45fr_1fr_auto]">{rubric ? <div className="grid grid-cols-2 gap-2">{rubric.criteria.map((criterion) => <label key={criterion.id} className="text-[10px] text-slate-500">{criterion.name} / {criterion.maximum_score}<input type="number" min="0" max={criterion.maximum_score} value={scores[submission.id]?.[criterion.id] ?? ''} onChange={(event) => setScores((all) => ({ ...all, [submission.id]: { ...all[submission.id], [criterion.id]: event.target.value } }))} className="form-input mt-1" /></label>)}</div> : <label className="text-[10px] text-slate-500">Grade / {summary.assignment.max_marks}<input type="number" min="0" max={summary.assignment.max_marks} value={grades[submission.id] ?? ''} onChange={(event) => setGrades((all) => ({ ...all, [submission.id]: event.target.value }))} className="form-input mt-1" /></label>}<label className="text-[10px] text-slate-500">Feedback<textarea value={feedback[submission.id] ?? submission.feedback ?? ''} onChange={(event) => setFeedback((all) => ({ ...all, [submission.id]: event.target.value }))} className="form-input mt-1 min-h-10 resize-y" placeholder="Feedback for the student" /></label><button onClick={() => void grade(submission)} className="self-end rounded-lg bg-cyan-200 px-4 py-2.5 text-xs font-semibold text-[#07141b]">Save grade</button></div>}
          {submission.status === 'graded' && <div className="mt-3 border-t border-white/6 pt-3 text-xs text-slate-400">Grade: <strong className="text-white">{submission.grade} / {summary.assignment.max_marks}</strong>{submission.feedback && <span className="ml-3">{submission.feedback}</span>}</div>}
        </article>;
      })}{!filtered.length && <div className="py-8 text-center text-xs text-slate-500">No submissions match this status filter.</div>}</div>
    </section>
  </div>;
}