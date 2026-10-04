'use client';

import { BookOpenCheck } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Empty, ErrorNotice, PageHeading } from '@/components/ui';
import { api } from '@/lib/api';

type Subject = { course: string; course_code: string; section?: string; subject: string; teacher?: string | null; attendance?: number | null; assessments: { assessment: string; score?: number | null; maximum: number; recorded_at?: string | null }[] };
type AcademicSubject = { name: string; fa1: number | null; fa2: number | null; fa_average: number | null; assignment_mark: number | null; internal_mark: number | null; attendance_rate: number | null };
type AcademicRecords = { subjects: Record<string, AcademicSubject>; total_internal: number | null; average_internal: number | null; academic_period: string | null; academic_periods: string[] };

export default function StudentSubjectsPage() {
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [academic, setAcademic] = useState<AcademicRecords | null>(null);
  const [error, setError] = useState('');
  useEffect(() => { Promise.all([api<Subject[]>('/api/v1/subjects/me'), api<AcademicRecords>('/api/v1/students/me/academic-records')]).then(([courseSubjects, records]) => { setSubjects(courseSubjects); setAcademic(records); }).catch((requestError: Error) => setError(requestError.message)); }, []);
  const changePeriod = async (period: string) => {
    try {
      const query = period ? `?academic_period=${encodeURIComponent(period)}` : '';
      setAcademic(await api<AcademicRecords>(`/api/v1/students/me/academic-records${query}`));
    } catch (requestError) { setError((requestError as Error).message); }
  };
  return (
    <div className="fade-up">
      <PageHeading eyebrow="Your study plan" title="Subjects" description="Subject-wise marks and course records visible only to your student account." />
      {academic && <label className="mb-4 block max-w-xs text-xs text-slate-400">Academic period<select value={academic.academic_period ?? ''} onChange={(event) => void changePeriod(event.target.value)} className="form-input"><option value="">No period records</option>{academic.academic_periods.map((period) => <option key={period} value={period}>{period}</option>)}</select></label>}
      {error && <ErrorNotice message={error} />}
      {academic && <section className="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-3">
        <div className="surface rounded-lg p-4"><div className="text-xs text-slate-500">Total internal /250</div><div className="mt-2 text-xl font-semibold">{academic.total_internal?.toFixed(1) ?? 'Incomplete'}</div></div>
        <div className="surface rounded-lg p-4"><div className="text-xs text-slate-500">Average /50</div><div className="mt-2 text-xl font-semibold">{academic.average_internal?.toFixed(2) ?? 'Incomplete'}</div></div>
        <div className="surface rounded-lg p-4 col-span-2 sm:col-span-1"><div className="text-xs text-slate-500">Risk model scope</div><div className="mt-2 text-xs text-slate-300">Global; these marks are academic context.</div></div>
      </section>}
      <div className="grid gap-4 lg:grid-cols-2">
        {academic && Object.entries(academic.subjects).map(([code, item]) => <section key={code} className="surface rounded-xl p-5">
          <div className="flex items-center gap-3"><span className="grid size-9 place-items-center rounded-lg bg-cyan-200/10 text-cyan-100"><BookOpenCheck size={17} /></span><div><h2 className="text-sm font-semibold text-white">{code} · {item.name}</h2><p className="mt-1 text-[10px] text-slate-500">Formative marks are not inputs to the current global risk model.</p></div></div>
          <div className="mt-4 grid grid-cols-3 gap-2 text-xs">{[['FA1 /25', item.fa1], ['FA2 /25', item.fa2], ['FA average /25', item.fa_average], ['Assignment /25', item.assignment_mark], ['Internal /50', item.internal_mark], ['Attendance', item.attendance_rate == null ? null : `${item.attendance_rate}%`]].map(([label, value]) => <div key={label} className="border-t border-white/8 py-2"><div className="text-[10px] text-slate-500">{label}</div><div className="mt-1 text-slate-100">{value == null ? 'Not available' : value}</div></div>)}</div>
        </section>)}
      </div>
      <div className="mt-4 grid gap-4 lg:grid-cols-2">{subjects.map((item) => <section key={item.course_code} className="surface rounded-xl p-5"><div><h2 className="text-sm font-semibold text-white">{item.subject}</h2><p className="mt-1 text-xs text-slate-500">{item.course_code} · Section {item.section ?? '—'} · Teacher: {item.teacher ?? 'Not assigned'}</p></div><div className="mt-4 flex justify-between border-y border-white/7 py-3 text-xs"><span className="text-slate-500">Course attendance</span><span className="text-slate-200">{item.attendance == null ? 'No course record' : `${item.attendance.toFixed(0)}%`}</span></div><h3 className="mt-4 text-xs font-medium text-slate-300">Course assessments</h3><div className="mt-2 divide-y divide-white/6">{item.assessments.map((assessment, index) => <div key={`${assessment.assessment}-${index}`} className="flex justify-between py-2 text-xs"><span className="text-slate-400">{assessment.assessment}</span><span className="text-slate-200">{assessment.score == null ? 'Not graded' : `${assessment.score} / ${assessment.maximum}`}</span></div>)}</div></section>)}</div>
      {!error && !subjects.length && !academic && <div className="surface rounded-xl p-5"><Empty title="No subject records yet" detail="Your course team can add records when they are available." /></div>}
    </div>
  );
}