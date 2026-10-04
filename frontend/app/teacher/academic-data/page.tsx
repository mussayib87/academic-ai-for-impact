'use client';

import { FileSpreadsheet, UploadCloud } from 'lucide-react';
import { useEffect, useState } from 'react';
import { ErrorNotice, PageHeading } from '@/components/ui';
import { API_BASE, api, readToken } from '@/lib/api';

type DatasetType = 'marks' | 'assessments' | 'attendance' | 'learning_activities' | 'subject_records' | 'risk_outcomes';
type ImportResult = {
  batch_id: number;
  dataset_type: DatasetType;
  source_filename: string;
  imported_rows: number;
  rejected_rows: number;
  unmatched_students: number;
  unmatched_student_ids: string[];
  duplicate_rows: number;
  duplicate_import: boolean;
  validation_errors: { row: number; student_id?: string; subject_code?: string; academic_period?: string; errors: string[] }[];
};
type ImportBatch = { id: number; dataset_type: DatasetType; source_filename: string; imported_rows: number; rejected_rows: number; duplicate_rows: number; created_at: string };

const schemas: Record<DatasetType, string[]> = {
  marks: ['student_id', 'assessment', 'score', 'recorded_at', 'maximum_marks (optional)', 'course_code (optional)'],
  assessments: ['student_id', 'assessment', 'score', 'maximum_marks', 'recorded_at', 'course_code (optional)'],
  attendance: ['student_id', 'attendance_rate', 'observed_at', 'attended (optional)', 'course_code (optional)'],
  learning_activities: ['student_id', 'activity_type', 'quantity', 'occurred_at', 'course_code (optional)'],
  subject_records: ['USN', 'Subject', 'Academic_Period', 'FA1 (optional)', 'FA1_Observed_At (optional)', 'FA2 (optional)', 'FA2_Observed_At (optional)', 'Assignment (optional)', 'Assignment_Observed_At (optional)', 'Attendance (optional)', 'Attendance_Observed_At (optional)'],
  risk_outcomes: ['USN', 'Academic_Period', 'Risk_Target', 'Observed_At', 'Outcome_Source'],
};

export default function AcademicDataPage() {
  const [datasetType, setDatasetType] = useState<DatasetType>('assessments');
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [batches, setBatches] = useState<ImportBatch[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const reload = () => api<ImportBatch[]>('/api/v1/academic-data/imports').then(setBatches).catch((requestError: Error) => setError(requestError.message));
  useEffect(() => { void reload(); }, []);

  const upload = async () => {
    if (!file) { setError('Choose a CSV or XLSX file first.'); return; }
    setBusy(true); setError(''); setResult(null);
    const form = new FormData();
    form.set('dataset_type', datasetType);
    form.set('file', file);
    try {
      const response = await fetch(`${API_BASE}/api/v1/academic-data/import`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${readToken() ?? ''}` },
        body: form,
        cache: 'no-store',
      });
      const body = await response.json() as ImportResult | { detail?: string | { message?: string; validation_errors?: ImportResult['validation_errors'] } };
      if (!response.ok) {
        const detail = (body as { detail?: string | { message?: string } }).detail;
        throw new Error(typeof detail === 'string' ? detail : detail?.message ?? `Import failed (${response.status}).`);
      }
      setResult(body as ImportResult);
      setFile(null);
      await reload();
    } catch (requestError) { setError((requestError as Error).message); }
    finally { setBusy(false); }
  };

  return <div className="fade-up">
    <PageHeading eyebrow="Academic records · faculty" title="Academic data" description="Import validated, period-scoped subject marks and dated academic observations." />
    {error && <div className="mb-4"><ErrorNotice message={error} /></div>}
    <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(320px,.72fr)]">
      <section className="surface rounded-xl p-5">
        <div className="flex items-center gap-2"><FileSpreadsheet size={16} className="text-cyan-100" /><h2 className="text-sm font-semibold">New import</h2></div>
        <div className="mt-5 grid gap-4 sm:grid-cols-2">
          <label className="text-xs text-slate-400">Record type<select value={datasetType} onChange={(event) => setDatasetType(event.target.value as DatasetType)} className="form-input"><option value="marks">Marks / internal scores</option><option value="assessments">Assessments</option><option value="attendance">Attendance</option><option value="learning_activities">Learning activities</option><option value="subject_records">FA1 / FA2 subject marks</option><option value="risk_outcomes">Independent academic-period risk outcome</option></select></label>
          <label className="text-xs text-slate-400">Academic data file<input type="file" accept=".csv,.xlsx" onChange={(event) => setFile(event.target.files?.[0] ?? null)} className="form-input file:mr-3 file:border-0 file:bg-transparent file:text-xs file:text-cyan-100" /></label>
        </div>
        <div className="mt-4 border-y border-white/8 py-4">
          <div className="text-[10px] font-semibold uppercase text-slate-500">Required columns</div>
          <div className="mt-2 flex flex-wrap gap-1.5">{schemas[datasetType].map((column) => <span key={column} className="rounded border border-white/8 bg-black/10 px-2 py-1 font-mono text-[10px] text-slate-300">{column}</span>)}</div>
          <p className="mt-3 text-[11px] leading-5 text-slate-500">Match an existing USN. Marks require a period code (for example, 2026-S1); FA1/FA2/assignment are 0–25. Add each field&apos;s source-observation date for future time-aligned ML eligibility. Outcomes must come from an independent, documented source, never this model or labels derived from these marks.</p>
        </div>
        <button type="button" disabled={busy || !file} onClick={() => void upload()} className="mt-4 inline-flex items-center gap-2 rounded-md bg-cyan-200 px-3 py-2.5 text-xs font-semibold text-[#07141b] disabled:opacity-50"><UploadCloud size={14} />{busy ? 'Validating and importing…' : 'Validate and import'}</button>
        {result && <div role="status" className="mt-5 border-t border-white/8 pt-4">
          <div className="text-xs font-semibold text-white">{result.duplicate_import ? 'This file was already imported' : `Batch #${result.batch_id} · ${result.source_filename}`}</div>
          <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">{[['Imported', result.imported_rows], ['Rejected', result.rejected_rows], ['Unmatched IDs', result.unmatched_students], ['Duplicates', result.duplicate_rows]].map(([label, value]) => <div key={label} className="rounded border border-white/8 bg-black/10 p-3"><div className="text-[10px] text-slate-500">{label}</div><div className="mt-1 text-lg font-semibold text-slate-100">{value}</div></div>)}</div>
          {result.validation_errors.length > 0 && <div className="mt-3 max-h-56 overflow-auto rounded border border-rose-200/15 bg-rose-200/[.03] p-3"><div className="mb-2 text-[10px] font-semibold uppercase text-rose-200">Row validation errors</div>{result.validation_errors.map((item) => <div key={item.row} className="border-t border-white/5 py-2 text-[11px] text-slate-300"><span className="font-mono text-rose-200">Row {item.row}</span>{item.student_id && ` · ${item.student_id}`}{item.subject_code && ` · ${item.subject_code}`}{item.academic_period && ` · ${item.academic_period}`} · {item.errors.join(' ')}</div>)}</div>}
          {result.unmatched_student_ids.length > 0 && <p className="mt-3 text-[11px] text-rose-200">Unmatched student IDs: {result.unmatched_student_ids.join(', ')}</p>}
        </div>}
      </section>
      <section className="surface rounded-xl p-5"><h2 className="text-sm font-semibold">Recent import batches</h2><div className="mt-4 divide-y divide-white/6">{batches.map((batch) => <article key={batch.id} className="py-3 first:pt-0"><div className="flex items-start justify-between gap-3"><div className="min-w-0"><div className="truncate text-xs font-medium text-slate-200">{batch.source_filename}</div><div className="mt-1 text-[10px] text-slate-500">{batch.dataset_type.replace('_', ' ')} · {new Date(batch.created_at).toLocaleString()}</div></div><span className="shrink-0 rounded border border-cyan-200/10 px-2 py-1 text-[10px] text-cyan-100">#{batch.id}</span></div><div className="mt-2 text-[10px] text-slate-400">{batch.imported_rows} imported · {batch.rejected_rows} rejected · {batch.duplicate_rows} duplicates</div></article>)}{!batches.length && <p className="py-6 text-xs text-slate-500">No academic data imports yet.</p>}</div></section>
    </div>
  </div>;
}