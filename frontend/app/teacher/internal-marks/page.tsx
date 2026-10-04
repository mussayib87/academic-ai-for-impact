'use client';

import { ArrowDownUp, Download, Search } from 'lucide-react';
import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import { ErrorNotice, PageHeading, RiskBadge } from '@/components/ui';
import { API_BASE, api, readToken } from '@/lib/api';

type SubjectCode = 'EVS' | 'CN' | 'TOC' | 'RM' | 'SE';
type Field = 'fa1' | 'fa2' | 'assignment_mark' | 'attendance_rate';
type SubjectRecord = { fa1: number | null; fa2: number | null; fa_average: number | null; assignment_mark: number | null; internal_mark: number | null; attendance_rate: number | null };
type RegisterRow = { id: number; student_id: string; full_name: string; department?: string | null; section?: string | null; subjects: Record<SubjectCode, SubjectRecord>; total_internal: number | null; average_internal: number | null; risk_level: string; risk_probability: number };
type Subject = { code: SubjectCode; name: string };
type RegisterResponse = { subjects: Subject[]; items: RegisterRow[]; total: number; risk_scope: string; academic_period: string | null; academic_periods: string[] };
type Readiness = { training_ready: boolean; students_in_database: number; subject_records: number; fa1_present: number; fa2_present: number; complete_fa1_fa2_observations: number; complete_period_aligned_observations_with_valid_target: number; distinct_academic_periods: string[]; duplicate_import_rows: number; conflicting_import_rows_rejected: number; other_rejected_import_rows: number; blockers: string[] };

const fieldLabels: Record<Field, string> = { fa1: 'FA1', fa2: 'FA2', assignment_mark: 'Assignment', attendance_rate: 'Attendance %' };
const subjectCodes: SubjectCode[] = ['EVS', 'CN', 'TOC', 'RM', 'SE'];
const pageSize = 25;

export default function InternalMarksPage() {
  const [rows, setRows] = useState<RegisterRow[]>([]);
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [search, setSearch] = useState('');
  const [scope, setScope] = useState<'ALL' | SubjectCode>('ALL');
  const [academicPeriod, setAcademicPeriod] = useState('');
  const [periodDraft, setPeriodDraft] = useState('');
  const [academicPeriods, setAcademicPeriods] = useState<string[]>([]);
  const [sortBy, setSortBy] = useState<'student_id' | 'full_name'>('student_id');
  const [page, setPage] = useState(0);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [loading, setLoading] = useState(true);
  const [readiness, setReadiness] = useState<Readiness | null>(null);

  useEffect(() => {
    Promise.all([api<RegisterResponse>('/api/v1/academic-register?limit=500'), api<Readiness>('/api/v1/ml/academic-data/readiness')])
      .then(([result, readinessResult]) => { setRows(result.items); setSubjects(result.subjects); setAcademicPeriods(result.academic_periods); setAcademicPeriod(result.academic_period ?? ''); setPeriodDraft(result.academic_period ?? ''); setReadiness(readinessResult); })
      .catch((requestError: Error) => setError(requestError.message))
      .finally(() => setLoading(false));
  }, []);

  const visible = useMemo(() => {
    const normalized = search.trim().toLowerCase();
    return rows.filter((row) => !normalized || `${row.student_id} ${row.full_name} ${row.department ?? ''} ${row.section ?? ''}`.toLowerCase().includes(normalized))
      .sort((left, right) => left[sortBy].localeCompare(right[sortBy]));
  }, [rows, search, sortBy]);
  const pages = Math.max(1, Math.ceil(visible.length / pageSize));
  const pageRows = visible.slice(page * pageSize, (page + 1) * pageSize);
  const shownSubjects = scope === 'ALL' ? subjectCodes : [scope];

  const setDraft = (rowId: number, code: SubjectCode, field: Field, value: string) => {
    setDrafts((current) => ({ ...current, [`${rowId}:${code}:${field}`]: value }));
  };

  const saveCell = async (row: RegisterRow, code: SubjectCode, field: Field) => {
    const key = `${row.id}:${code}:${field}`;
    if (!(key in drafts)) return;
    if (!academicPeriod) { setError('Choose an academic period before editing marks.'); return; }
    const raw = drafts[key].trim();
    const value = raw === '' ? null : Number(raw);
    const maximum = field === 'attendance_rate' ? 100 : 25;
    if (value !== null && (!Number.isFinite(value) || value < 0 || value > maximum)) {
      setError(`${fieldLabels[field]} must be between 0 and ${maximum}.`);
      return;
    }
    setError(''); setNotice(''); setSaving(key);
    try {
      const result = await api<{ register_row: RegisterRow }>(`/api/v1/academic-register/${row.id}/${code}?academic_period=${encodeURIComponent(academicPeriod)}`, {
        method: 'PATCH',
        body: JSON.stringify({ [field]: value }),
      });
      setRows((current) => current.map((item) => item.id === row.id ? result.register_row : item));
      setDrafts((current) => { const { [key]: _saved, ...rest } = current; return rest; });
      setNotice(`${row.full_name} · ${code} ${fieldLabels[field]} saved.`);
    } catch (requestError) { setError((requestError as Error).message); }
    finally { setSaving(null); }
  };

  const loadAcademicPeriod = async () => {
    const nextPeriod = periodDraft.trim().toUpperCase();
    if (!/^\d{4}-S[12]$/.test(nextPeriod)) { setError('Academic period must use YYYY-S1 or YYYY-S2.'); return; }
    setLoading(true); setError(''); setNotice('');
    try {
      const result = await api<RegisterResponse>(`/api/v1/academic-register?limit=500&academic_period=${encodeURIComponent(nextPeriod)}`);
      setRows(result.items); setSubjects(result.subjects); setAcademicPeriods(result.academic_periods); setAcademicPeriod(result.academic_period ?? nextPeriod); setPeriodDraft(result.academic_period ?? nextPeriod); setPage(0); setDrafts({});
    } catch (requestError) { setError((requestError as Error).message); }
    finally { setLoading(false); }
  };

  const download = async () => {
    try {
      if (!academicPeriod) throw new Error('Choose an academic period before exporting the register.');
      const response = await fetch(`${API_BASE}/api/v1/reports/export.csv?report_type=internal_marks&academic_period=${encodeURIComponent(academicPeriod)}`, { headers: { Authorization: `Bearer ${readToken() ?? ''}` } });
      if (!response.ok) throw new Error('Unable to export the marks register.');
      const url = URL.createObjectURL(await response.blob());
      const anchor = document.createElement('a'); anchor.href = url; anchor.download = 'academic-internal-marks.csv'; anchor.click(); URL.revokeObjectURL(url);
    } catch (requestError) { setError((requestError as Error).message); }
  };

  return <div>
    <PageHeading eyebrow="Academic records · faculty" title="Internal marks register" description="Five-subject register. Subject marks are academic context; current risk remains a global model prediction." action={<button type="button" onClick={() => void download()} className="inline-flex items-center gap-2 rounded-md border border-white/10 px-3 py-2 text-xs text-slate-200"><Download size={14} /> Export CSV</button>} />
    {error && <div className="mb-3"><ErrorNotice message={error} /></div>}
    {notice && <div role="status" className="mb-3 border-l-2 border-emerald-300 px-3 py-2 text-xs text-emerald-100">{notice}</div>}
    {readiness && <section className="mb-3 border-y border-white/10 py-3"><div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="text-xs font-semibold text-slate-200">Future ML data readiness · {readiness.training_ready ? 'Ready for review' : 'Not ready'}</h2><p className="mt-1 text-[10px] text-slate-500">Academic records do not enter the current model automatically.</p></div><div className="flex flex-wrap gap-x-4 gap-y-1 text-[10px] tabular-nums text-slate-400"><span>{readiness.subject_records} subject-period rows</span><span>FA1 {readiness.fa1_present}</span><span>FA2 {readiness.fa2_present}</span><span>{readiness.complete_fa1_fa2_observations} complete marks</span><span>{readiness.complete_period_aligned_observations_with_valid_target} aligned outcomes</span><span>{readiness.distinct_academic_periods.length} periods</span><span>{readiness.conflicting_import_rows_rejected} conflicts rejected</span><span>{readiness.duplicate_import_rows} duplicate rows</span></div></div><ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[10px] text-amber-100">{readiness.blockers.slice(0, 3).map((blocker) => <li key={blocker}>{blocker}</li>)}</ul></section>}
    <div className="mb-3 flex flex-wrap items-center gap-3 border-y border-white/10 py-3">
      <label className="relative min-w-56 flex-1"><Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" /><input value={search} onChange={(event) => { setSearch(event.target.value); setPage(0); }} className="form-input pl-9" placeholder="Search USN, student, department" /></label>
      <label className="text-xs text-slate-400">View<select value={scope} onChange={(event) => { setScope(event.target.value as 'ALL' | SubjectCode); setPage(0); }} className="form-input mt-1 min-w-44"><option value="ALL">Master register</option>{subjects.map((subject) => <option key={subject.code} value={subject.code}>{subject.code} · {subject.name}</option>)}</select></label>
      <button type="button" onClick={() => setSortBy((current) => current === 'student_id' ? 'full_name' : 'student_id')} className="mt-4 inline-flex items-center gap-2 rounded-md border border-white/10 px-3 py-2 text-xs text-slate-300" title="Toggle student sorting"><ArrowDownUp size={14} /> Sort by {sortBy === 'student_id' ? 'USN' : 'name'}</button>
      <label className="text-xs text-slate-400">Academic period<input list="academic-period-options" value={periodDraft} onChange={(event) => setPeriodDraft(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') { event.preventDefault(); void loadAcademicPeriod(); } }} className="form-input mt-1 w-36" placeholder="2026-S1" /><datalist id="academic-period-options">{academicPeriods.map((value) => <option key={value} value={value} />)}</datalist></label>
      <button type="button" onClick={() => void loadAcademicPeriod()} className="mt-4 rounded-md border border-cyan-200/20 px-3 py-2 text-xs text-cyan-100">Load period</button>
      <div className="mt-4 text-xs tabular-nums text-slate-500">{visible.length} students</div>
    </div>
    <div className="overflow-auto border border-[var(--line)] bg-[#0a111c]" style={{ maxHeight: 'calc(100vh - 255px)' }}>
      <table className="w-max min-w-full border-separate border-spacing-0 text-left text-xs">
        <thead className="sticky top-0 z-30 bg-[#121e2d]">
          <tr>
            <th rowSpan={2} className="sticky left-0 z-40 min-w-28 border-b border-r border-white/10 bg-[#121e2d] px-3 py-3">USN</th>
            <th rowSpan={2} className="sticky left-28 z-40 min-w-52 border-b border-r border-white/10 bg-[#121e2d] px-3 py-3">Student Name</th>
            <th rowSpan={2} className="min-w-32 border-b border-r border-white/10 px-3 py-3">Department / Section</th>
            {shownSubjects.map((code) => <th key={code} colSpan={scope === 'ALL' ? 6 : 8} className="border-b border-r border-white/10 bg-[#17263a] px-3 py-3 text-center font-semibold text-cyan-100">{code} · {subjects.find((item) => item.code === code)?.name}</th>)}
            {scope === 'ALL' && <><th rowSpan={2} className="min-w-28 border-b border-r border-white/10 px-3 py-3 text-center">Total /250</th><th rowSpan={2} className="min-w-28 border-b border-r border-white/10 px-3 py-3 text-center">Average /50</th><th rowSpan={2} className="min-w-32 border-b border-r border-white/10 px-3 py-3">Global risk</th></>}
            <th rowSpan={2} className="min-w-24 border-b border-white/10 px-3 py-3">Student 360</th>
          </tr>
          <tr>{shownSubjects.flatMap((code) => (scope === 'ALL' ? ['FA1 /25', 'FA2 /25', 'FA Avg /25', 'Assignment /25', 'Internal /50', 'Attendance %'] : ['FA1 /25', 'FA2 /25', 'FA Avg /25', 'Assignment /25', 'Internal /50', 'Attendance %', 'Risk', 'Trend']).map((label, index) => <th key={`${code}-${label}`} className="sticky top-10 z-30 min-w-24 border-b border-r border-white/10 bg-[#121e2d] px-2 py-2 text-center font-medium text-slate-400">{label}</th>))}</tr>
        </thead>
        <tbody>
          {pageRows.map((row) => <tr key={row.id} className="group hover:bg-white/[.025]">
            <th scope="row" className="sticky left-0 z-20 border-b border-r border-white/8 bg-[#0d1724] px-3 py-2 text-left font-mono text-slate-300">{row.student_id}</th>
            <td className="sticky left-28 z-20 border-b border-r border-white/8 bg-[#0d1724] px-3 py-2 font-medium text-slate-100">{row.full_name}</td>
            <td className="border-b border-r border-white/8 px-3 py-2 text-slate-500">{row.department ?? '—'} · {row.section ?? '—'}</td>
            {shownSubjects.flatMap((code) => {
              const record = row.subjects[code];
              const fields: Field[] = ['fa1', 'fa2', 'assignment_mark', 'attendance_rate'];
              const cells = fields.flatMap((field) => {
                const key = `${row.id}:${code}:${field}`;
                const value = drafts[key] ?? (record[field] == null ? '' : String(record[field]));
                return [<td key={key} className="border-b border-r border-white/8 p-1"><input aria-label={`${row.student_id} ${code} ${fieldLabels[field]}`} type="number" min="0" max={field === 'attendance_rate' ? 100 : 25} step="0.1" value={value} disabled={saving === key} onChange={(event) => setDraft(row.id, code, field, event.target.value)} onBlur={() => void saveCell(row, code, field)} onKeyDown={(event) => { if (event.key === 'Enter') { event.currentTarget.blur(); } }} className="w-20 border border-cyan-200/10 bg-[#101b2a] px-2 py-1.5 text-right tabular-nums text-slate-100 outline-none focus:border-cyan-200/60" /></td>];
              });
              cells.splice(2, 0, <td key={`${row.id}:${code}:fa-average`} className="border-b border-r border-white/8 bg-white/[.02] px-2 py-2 text-center tabular-nums text-slate-300">{record.fa_average == null ? '—' : record.fa_average.toFixed(1)}</td>);
              cells.splice(4, 0, <td key={`${row.id}:${code}:internal`} className="border-b border-r border-white/8 bg-cyan-200/[.035] px-2 py-2 text-center font-semibold tabular-nums text-cyan-100">{record.internal_mark == null ? '—' : record.internal_mark.toFixed(1)}</td>);
              if (scope !== 'ALL') {
                cells.push(<td key={`${row.id}:${code}:risk`} className="border-b border-r border-white/8 px-2 py-2"><div className="flex items-center gap-2"><RiskBadge level={row.risk_level} /><span className="text-[10px] text-slate-500">global</span></div><div className="mt-1 text-[10px] text-slate-400">{(row.risk_probability * 100).toFixed(1)}% P({row.risk_level})</div></td>);
                cells.push(<td key={`${row.id}:${code}:trend`} className="border-b border-r border-white/8 px-2 py-2 text-center text-slate-500">Not modeled</td>);
              }
              return cells;
            })}
            {scope === 'ALL' && <><td className="border-b border-r border-white/8 bg-cyan-200/[.035] px-3 py-2 text-center font-semibold tabular-nums text-cyan-100">{row.total_internal == null ? '—' : row.total_internal.toFixed(1)}</td><td className="border-b border-r border-white/8 bg-cyan-200/[.035] px-3 py-2 text-center font-semibold tabular-nums text-cyan-100">{row.average_internal == null ? '—' : row.average_internal.toFixed(2)}</td></>}
            {scope === 'ALL' && <td className="border-b border-white/8 px-3 py-2"><div className="flex items-center gap-2"><RiskBadge level={row.risk_level} /><span className="text-[10px] text-slate-500">global</span></div><div className="mt-1 text-[10px] text-slate-400">{(row.risk_probability * 100).toFixed(1)}% P({row.risk_level})</div></td>}
            <td className="border-b border-white/8 px-3 py-2"><Link className="text-cyan-200 hover:underline" href={`/teacher/students/${row.id}`}>Open profile</Link></td>
          </tr>)}
          {!pageRows.length && <tr><td colSpan={scope === 'ALL' ? 37 : 12} className="px-5 py-12 text-center text-slate-500">{loading ? 'Loading student records…' : 'No students match this search.'}</td></tr>}
        </tbody>
      </table>
    </div>
    <div className="mt-3 flex items-center justify-end gap-3 text-xs text-slate-400"><button type="button" disabled={page === 0} onClick={() => setPage((value) => Math.max(0, value - 1))} className="rounded border border-white/10 px-3 py-2 disabled:opacity-40">Previous</button><span>Page {page + 1} of {pages}</span><button type="button" disabled={page + 1 >= pages} onClick={() => setPage((value) => Math.min(pages - 1, value + 1))} className="rounded border border-white/10 px-3 py-2 disabled:opacity-40">Next</button></div>
    <p className="mt-3 text-[10px] text-slate-600">{academicPeriod ? `Period ${academicPeriod}. ` : 'Select a period before editing or exporting. '}{academicPeriod && !academicPeriods.includes(academicPeriod) ? 'This period has no imported records yet. ' : ''}Internal /50 = ((FA1 + FA2) / 2) + Assignment. Calculated fields are read-only. FA1/FA2 are not features in the current trained model; risk remains global.</p>
  </div>;
}
