'use client';

import { motion } from 'framer-motion';
import { ArrowDownRight, ArrowUpRight, ChevronLeft, Clock3, RefreshCw, Sparkles } from 'lucide-react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useEffect, useState } from 'react';
import { Metric, RiskBadge } from '@/components/ui';
import { api } from '@/lib/api';
import { formatRiskProbability } from '@/lib/risk';

type Student = { id: number; student_id: string; full_name: string; program?: string; year?: string; section?: string; department?: string; risk_level: string; risk_probability: number; previous_gpa: number; current_gpa: number; attendance: number; assessment: number; assignments_completed: number };
type Observation = { metric: string; value: number; observed_at: string };
type Submission = { id: number; assignment_id: number; status: string; grade?: number | null; feedback?: string | null; submitted_at?: string | null; file_name?: string | null };
type SubjectRecord = { name: string; fa1: number | null; fa1_observed_at: string | null; fa2: number | null; fa2_observed_at: string | null; fa_average: number | null; assignment_mark: number | null; assignment_observed_at: string | null; internal_mark: number | null; attendance_rate: number | null; attendance_observed_at: string | null };
type SubjectAssignment = { id: number; title: string; subject_code: string; status: string; due_date: string | null; max_marks: number; submission_status: string; uploaded: boolean; file_name: string | null; grade: number | null; feedback: string | null; submitted_at: string | null };
type Detail = { student: Student; momentum: Observation[]; submissions: Submission[]; risk_history: { risk_level: string; recorded_at: string }[]; academic_records: { subjects: Record<string, SubjectRecord>; risk_scope: string; academic_period: string | null; academic_periods: string[] } };
type Explanation = { prediction: { risk_level: string; risk_probability: number; risk_probability_semantics: string; model_version: string }; explanation: { target: string; target_class: string; base_value: number; contributions: Record<string, number>; feature_values: Record<string, number>; waterfall: { feature: string; value: number; contribution: number }[]; summary: string[] } };
type TabName = 'Overview' | 'EVS' | 'CN' | 'TOC' | 'RM' | 'SE' | 'Academic performance' | 'Assignments' | 'Learning activity' | 'Risk analysis' | 'SHAP';
const subjectTabs: TabName[] = ['EVS', 'CN', 'TOC', 'RM', 'SE'];
const tabs: TabName[] = ['Overview', ...subjectTabs, 'Academic performance', 'Assignments', 'Learning activity', 'Risk analysis', 'SHAP'];

export default function Student360Page() {
  const params = useParams<{ studentId: string }>();
  const [detail, setDetail] = useState<Detail | null>(null);
  const [tab, setTab] = useState<TabName>('Overview');
  const [explanation, setExplanation] = useState<Explanation | null>(null);
  const [loadingExplanation, setLoadingExplanation] = useState(false);
  const [subjectAssignments, setSubjectAssignments] = useState<SubjectAssignment[]>([]);
  const [error, setError] = useState('');

  const changeAcademicPeriod = async (academicPeriod: string) => {
    if (!detail) return;
    try {
      const query = academicPeriod ? `?academic_period=${encodeURIComponent(academicPeriod)}` : '';
      const academicRecords = await api<Detail['academic_records']>(`/api/v1/students/${detail.student.id}/academic-records${query}`);
      setDetail((current) => current ? { ...current, academic_records: academicRecords } : current);
    } catch (requestError) { setError((requestError as Error).message); }
  };

  useEffect(() => {
    api<Detail>(`/api/v1/students/${encodeURIComponent(params.studentId)}`).then(setDetail).catch((requestError: Error) => setError(requestError.message));
  }, [params.studentId]);

  const openTab = async (next: TabName) => {
    setTab(next);
    if (subjectTabs.includes(next) && detail) {
      try {
        setSubjectAssignments(await api<SubjectAssignment[]>(`/api/v1/students/${detail.student.id}/subjects/${next}/assignments`));
      } catch (requestError) { setError((requestError as Error).message); }
      return;
    }
    if (next !== 'SHAP' || explanation || loadingExplanation) return;
    setLoadingExplanation(true);
    try {
      const result = await api<Explanation>(`/api/v1/students/${params.studentId}/shap`);
      setExplanation(result);
      setDetail((current) => current ? {
        ...current,
        student: { ...current.student, risk_level: result.prediction.risk_level, risk_probability: result.prediction.risk_probability },
      } : current);
    }
    catch (requestError) { setError((requestError as Error).message); }
    finally { setLoadingExplanation(false); }
  };

  if (error) return <div role="alert" className="rounded-lg border border-rose-300/20 bg-rose-300/5 p-4 text-sm text-rose-100">{error}</div>;
  if (!detail) return <div className="space-y-4"><div className="skeleton h-36 rounded-xl" /><div className="skeleton h-72 rounded-xl" /></div>;
  const { student } = detail;
  const metricGroups = detail.momentum.reduce<Record<string, Observation[]>>((groups, item) => { (groups[item.metric] ??= []).push(item); return groups; }, {});
  const subjectRecord = subjectTabs.includes(tab) ? detail.academic_records.subjects[tab] : undefined;

  return <div className="fade-up space-y-6">
    <Link href="/teacher/students" className="inline-flex items-center gap-1 text-xs text-slate-500 hover:text-cyan-200"><ChevronLeft size={15} /> Student directory</Link>
    <p className="text-xs text-slate-500">Risk probability is confidence in the displayed class; SHAP explains that same class probability.</p>
    {subjectRecord && <label className="block max-w-xs text-xs text-slate-400">Academic period<select value={detail.academic_records.academic_period ?? ''} onChange={(event) => void changeAcademicPeriod(event.target.value)} className="form-input"><option value="">No period records</option>{detail.academic_records.academic_periods.map((period) => <option key={period} value={period}>{period}</option>)}</select></label>}
    <section className="surface relative overflow-hidden rounded-xl p-5 sm:p-7">
      <div className="absolute right-0 top-0 h-40 w-1/3 border-l border-white/[.035] bg-gradient-to-bl from-cyan-300/[.07] to-transparent" />
      <div className="relative flex flex-wrap items-start justify-between gap-5"><div><p className="eyebrow">Student 360 · {student.department ?? 'Academic profile'}</p><h1 className="mt-2 text-3xl font-semibold text-white sm:text-4xl">{student.full_name}</h1><div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-400"><span className="font-mono">{student.student_id}</span><span>{student.program ?? 'Program not set'}</span><span>Year {student.year ?? '—'}</span><span>Section {student.section ?? '—'}</span></div></div><div className="flex items-center gap-3"><RiskBadge level={student.risk_level} /><div className="text-right"><div className="text-2xl font-semibold text-white">{formatRiskProbability(student.risk_level, student.risk_probability)}</div><div className="text-[10px] uppercase tracking-[.1em] text-slate-500">Predicted class probability</div></div></div></div>
      <div className="relative mt-6 grid gap-3 sm:grid-cols-3"><Metric label="Attendance" value={`${student.attendance.toFixed(0)}%`} detail="Recorded academic observations" color={student.attendance < 75 ? 'rose' : 'cyan'} /><Metric label="Assessment" value={`${student.assessment.toFixed(0)}%`} detail="Current assessment average" color="amber" /><Metric label="Assignments" value={student.assignments_completed} detail="Completed engagements" color="mint" /></div>
    </section>

    <div className="border-b border-white/10"><div role="tablist" aria-label="Student details" className="flex gap-1 overflow-x-auto">{tabs.map((item) => <button key={item} role="tab" aria-selected={tab === item} onClick={() => void openTab(item)} className={`whitespace-nowrap border-b-2 px-3 py-3 text-xs transition ${tab === item ? 'border-cyan-200 text-cyan-100' : 'border-transparent text-slate-500 hover:text-slate-200'}`}>{item}</button>)}</div></div>

    {tab === 'SHAP' && explanation && <p className="text-xs text-slate-500">SHAP target class: {explanation.explanation.target_class} ({explanation.explanation.target}).</p>}

    {tab === 'Overview' && <section className="grid gap-4 lg:grid-cols-[1fr_1fr]"><div className="surface rounded-xl p-5"><h2 className="text-sm font-semibold">Academic progress</h2><p className="mt-1 text-xs text-slate-500">Previous term compared with current standing</p><div className="mt-6 grid grid-cols-2 gap-3"><div className="surface-soft rounded-lg p-4"><div className="text-xs text-slate-500">Previous GPA</div><div className="mt-2 text-2xl font-semibold text-slate-300">{student.previous_gpa.toFixed(2)}</div></div><div className="rounded-lg border border-cyan-200/15 bg-cyan-200/[.04] p-4"><div className="text-xs text-cyan-100/70">Current GPA</div><div className="mt-2 text-2xl font-semibold text-cyan-100">{student.current_gpa.toFixed(2)}</div><div className="mt-1 text-[10px] text-slate-500">{student.current_gpa >= student.previous_gpa ? 'Above previous term' : 'Below previous term'}</div></div></div></div><div className="surface rounded-xl p-5"><h2 className="text-sm font-semibold">Recent academic signals</h2><div className="mt-3 space-y-2">{Object.entries(metricGroups).map(([metric, rows]) => { const latest = rows.at(-1); const first = rows[0]; const up = !!latest && !!first && latest.value >= first.value; return <div key={metric} className="flex items-center gap-3 border-t border-white/6 py-3 first:border-0"><span className={`grid size-8 place-items-center rounded-lg ${up ? 'bg-emerald-300/10 text-emerald-200' : 'bg-rose-300/10 text-rose-200'}`}>{up ? <ArrowUpRight size={15} /> : <ArrowDownRight size={15} />}</span><div className="flex-1"><div className="text-xs font-medium capitalize text-slate-200">{metric.replaceAll('_', ' ')}</div><div className="mt-1 text-[10px] text-slate-500">{rows.length} dated observations</div></div><div className="text-xs text-slate-300">{latest?.value.toFixed(0) ?? '—'}</div></div>; })}{!Object.keys(metricGroups).length && <p className="py-4 text-xs text-slate-500">No dated observations are recorded.</p>}</div></div></section>}

    {subjectRecord && <section className="surface rounded-xl p-5"><div className="flex flex-wrap items-start justify-between gap-4"><div><p className="eyebrow">{tab} · subject record</p><h2 className="mt-1 text-lg font-semibold">{subjectRecord.name}</h2><p className="mt-1 text-xs text-slate-500">Subject-specific marks and attendance are not inputs to the current global risk model.</p></div><div className="text-right"><RiskBadge level={student.risk_level} /><div className="mt-1 text-[10px] text-slate-500">Global model · {formatRiskProbability(student.risk_level, student.risk_probability)}</div><button type="button" onClick={() => void openTab('SHAP')} className="mt-2 text-xs text-cyan-200 hover:underline">View global SHAP explanation</button></div></div><div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">{[['FA1 /25', subjectRecord.fa1], ['FA2 /25', subjectRecord.fa2], ['FA average /25', subjectRecord.fa_average], ['Assignment /25', subjectRecord.assignment_mark], ['Internal /50', subjectRecord.internal_mark], ['Attendance %', subjectRecord.attendance_rate]].map(([label, value]) => <div key={label} className="border-t border-white/8 py-3"><div className="text-[10px] text-slate-500">{label}</div><div className="mt-1 text-lg font-semibold text-slate-100">{value == null ? '—' : value}</div></div>)}</div><h3 className="mt-4 border-t border-white/8 pt-4 text-xs font-semibold">Subject assignments</h3><div className="mt-2 divide-y divide-white/6">{subjectAssignments.map((item) => <div key={item.id} className="grid gap-2 py-3 text-xs sm:grid-cols-[1fr_auto_auto]"><div><div className="text-slate-200">{item.title}</div><div className="mt-1 text-[10px] text-slate-500">Due {item.due_date ? new Date(item.due_date).toLocaleDateString() : 'not scheduled'} · {item.file_name ?? (item.uploaded ? 'File uploaded' : 'No file uploaded')}</div></div><span className="capitalize text-slate-400">{item.submission_status.replaceAll('_', ' ')}</span><span className="text-slate-300">{item.grade == null ? `— / ${item.max_marks}` : `${item.grade} / ${item.max_marks}`}</span>{item.feedback && <p className="text-slate-500 sm:col-span-3">{item.feedback}</p>}</div>)}{!subjectAssignments.length && <p className="py-4 text-xs text-slate-500">No assignments are linked to this subject yet.</p>}</div><p className="mt-3 text-[10px] text-slate-600">Subject-specific momentum and SHAP are unavailable because the existing model and observation schema are global.</p></section>}

    {tab === 'Academic performance' && <section className="surface rounded-xl p-5"><h2 className="text-sm font-semibold">Academic performance over time</h2><div className="mt-5 grid gap-4 sm:grid-cols-2">{['assessment', 'attendance'].map((metric) => <div key={metric} className="surface-soft rounded-lg p-4"><div className="flex justify-between"><span className="text-xs capitalize text-slate-400">{metric}</span><span className="text-xs text-slate-500">{metric === 'attendance' ? '%' : '%'}</span></div><div className="mt-4 flex h-36 items-end gap-1.5">{(metricGroups[metric] ?? []).map((item, index) => <div key={`${item.observed_at}-${index}`} title={`${new Date(item.observed_at).toLocaleDateString()}: ${item.value.toFixed(1)}%`} className="group relative flex-1 rounded-t-sm bg-gradient-to-t from-cyan-500/60 to-cyan-200/80" style={{ height: `${Math.max(4, item.value)}%` }}><span className="absolute -top-5 left-1/2 hidden -translate-x-1/2 text-[9px] text-slate-300 group-hover:block">{Math.round(item.value)}</span></div>)}</div><div className="mt-2 flex justify-between text-[9px] text-slate-600"><span>Earlier</span><span>Latest</span></div></div>)}</div></section>}

    {tab === 'Assignments' && <section className="surface rounded-xl p-5"><h2 className="text-sm font-semibold">Assignment engagement</h2><div className="mt-4 divide-y divide-white/6">{detail.submissions.map((item) => <div key={item.id} className="flex flex-wrap items-center gap-3 py-3"><span className="size-2 rounded-full bg-cyan-200" /><div className="flex-1 text-xs text-slate-200">Assignment {item.assignment_id}</div><span className="text-xs text-slate-400">{item.status}</span><span className="text-xs text-slate-300">{item.grade == null ? 'Not graded' : `${item.grade} marks`}</span><span className="text-[10px] text-slate-500">{item.submitted_at ? new Date(item.submitted_at).toLocaleString() : 'No timestamp'}</span></div>)}{!detail.submissions.length && <div className="py-8 text-center text-xs text-slate-500">No assignment submissions recorded.</div>}</div></section>}

    {tab === 'Learning activity' && <section className="surface rounded-xl p-5"><h2 className="text-sm font-semibold">Dated learning observations</h2><div className="mt-4 overflow-x-auto"><table className="w-full min-w-[450px] text-left text-xs"><thead className="text-[10px] uppercase tracking-[.1em] text-slate-500"><tr><th className="pb-3">Signal</th><th className="pb-3">Value</th><th className="pb-3">Observed</th></tr></thead><tbody>{detail.momentum.map((item, index) => <tr key={`${item.metric}-${item.observed_at}-${index}`} className="border-t border-white/6"><td className="py-3 capitalize text-slate-300">{item.metric.replaceAll('_', ' ')}</td><td className="py-3 text-slate-200">{item.value.toFixed(1)}</td><td className="py-3 text-slate-500">{new Date(item.observed_at).toLocaleDateString()}</td></tr>)}</tbody></table></div>{!detail.momentum.length && <div className="py-6 text-center text-xs text-slate-500">No learning activity observations are available.</div>}</section>}

    {tab === 'Risk analysis' && <section className="surface rounded-xl p-5"><div className="flex items-center gap-2"><Sparkles size={16} className="text-amber-100" /><h2 className="text-sm font-semibold">Risk history</h2></div><p className="mt-1 text-xs text-slate-500">Historical saved class labels; older entries may predate the current argmax policy.</p><div className="mt-5 flex flex-wrap gap-3">{detail.risk_history.map((item, index) => <div key={`${item.recorded_at}-${index}`} className="surface-soft min-w-44 rounded-lg p-4"><div className="flex items-center justify-between"><RiskBadge level={item.risk_level} /><span className="text-[10px] text-slate-500">Historical</span></div><div className="mt-3 text-[10px] text-slate-500">{new Date(item.recorded_at).toLocaleString()}</div></div>)}{!detail.risk_history.length && <div className="text-xs text-slate-500">No risk history has been saved yet.</div>}</div></section>}

    {tab === 'SHAP' && <section className="surface rounded-xl p-5 sm:p-6"><div className="flex flex-wrap items-start justify-between gap-3"><div><p className="eyebrow">Model explanation</p><h2 className="mt-1 text-lg font-semibold">Why is this student at risk?</h2><p className="mt-1 text-xs text-slate-500">Contributions are calculated from this student’s features and the current trained model.</p></div><span className="rounded-full border border-indigo-200/15 bg-indigo-200/[.05] px-3 py-1.5 text-[10px] text-indigo-100">{explanation?.prediction.model_version ?? 'SHAP'}</span></div>
      {loadingExplanation && <div className="mt-5 flex items-center gap-2 text-xs text-slate-400"><RefreshCw size={14} className="animate-spin" />Calculating model explanation…</div>}
      {explanation && <><div className="mt-5 rounded-lg border border-white/7 bg-black/10 px-4 py-3"><div className="text-xs text-slate-400">SHAP target {explanation.explanation.target_class}<strong className="ml-2 text-white">{formatRiskProbability(explanation.prediction.risk_level, explanation.prediction.risk_probability)}</strong></div><div className="mt-3 space-y-3">{explanation.explanation.waterfall.map((item) => { const magnitude = Math.min(Math.abs(item.contribution) * 100 * 3, 100); return <div key={item.feature} className="grid grid-cols-[130px_1fr_56px] items-center gap-3"><div className="truncate text-[11px] capitalize text-slate-400">{item.feature.replaceAll('_', ' ')}</div><div className="relative h-2 rounded-full bg-white/5"><div className={`absolute top-0 h-full rounded-full ${item.contribution >= 0 ? 'bg-rose-300' : 'bg-emerald-300'}`} style={{ width: `${magnitude}%`, left: item.contribution >= 0 ? '50%' : `${50 - magnitude}%` }} /><span className="absolute left-1/2 top-[-3px] h-3.5 w-px bg-slate-500" /></div><div className={`text-right font-mono text-[10px] ${item.contribution >= 0 ? 'text-rose-200' : 'text-emerald-200'}`}>{item.contribution >= 0 ? '+' : ''}{item.contribution.toFixed(3)}</div></div>})}</div></div><div className="mt-4"><h3 className="text-xs font-semibold text-slate-200">Largest contributing signals</h3><ul className="mt-2 space-y-2">{explanation.explanation.summary.map((item) => <li key={item} className="flex gap-2 text-xs leading-5 text-slate-400"><span className="mt-1.5 size-1 shrink-0 rounded-full bg-cyan-200" />{item}</li>)}</ul></div><p className="mt-5 flex items-center gap-2 border-t border-white/8 pt-4 text-[10px] text-slate-600"><Clock3 size={12} /> Explanations support faculty review and are not a diagnosis.</p></>}
      {!explanation && !loadingExplanation && <button onClick={() => void openTab('SHAP')} className="mt-5 inline-flex items-center gap-2 rounded-lg border border-cyan-200/20 px-3 py-2 text-xs text-cyan-100 hover:bg-cyan-200/5"><Sparkles size={14} /> Calculate explanation</button>}
    </section>}
  </div>;
}