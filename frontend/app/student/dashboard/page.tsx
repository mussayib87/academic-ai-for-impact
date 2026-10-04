'use client';

import { motion } from 'framer-motion';
import { ArrowRight, BookOpen, CalendarDays, CircleCheck, GraduationCap } from 'lucide-react';
import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Empty, ErrorNotice, Metric, PageHeading, PanelTitle } from '@/components/ui';
import { api } from '@/lib/api';

type Student = { full_name: string; previous_gpa: number; current_gpa: number; attendance: number; assessment: number; assignments_completed: number };
type Assignment = { id: number; title: string; course?: string | null; subject: string; due_date?: string | null };
type Submission = { id: number; assignment_id: number; status: string; grade?: number | null; feedback?: string | null; submitted_at?: string | null };
type Dashboard = { student: Student; assignments: Assignment[]; recent_submissions: Submission[]; unread_notifications: number };
type MetricSeries = Record<string, { classification: string; observations: { value: number; observed_at: string }[] }>;

export default function StudentDashboard() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [series, setSeries] = useState<MetricSeries>({});
  const [error, setError] = useState('');
  useEffect(() => {
    Promise.all([api<Dashboard>('/api/v1/dashboard/student'), api<{ metrics: MetricSeries }>('/api/v1/students/me/momentum')])
      .then(([dashboard, momentum]) => { setData(dashboard); setSeries(momentum.metrics); })
      .catch((requestError: Error) => setError(requestError.message));
  }, []);
  const chartData = useMemo(() => {
    const attendance = series.attendance?.observations ?? [];
    const assessment = series.assessment?.observations ?? [];
    return attendance.map((item, index) => ({ date: new Date(item.observed_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }), attendance: item.value, assessment: assessment[index]?.value }));
  }, [series]);

  if (error) return <ErrorNotice message={error} />;
  if (!data) return <div className="space-y-4"><div className="skeleton h-36 rounded-xl" /><div className="grid gap-3 sm:grid-cols-3"><div className="skeleton h-28 rounded-xl" /><div className="skeleton h-28 rounded-xl" /><div className="skeleton h-28 rounded-xl" /></div></div>;
  const student = data.student;
  const upcoming = data.assignments.filter((item) => item.due_date).sort((left, right) => new Date(left.due_date!).getTime() - new Date(right.due_date!).getTime()).slice(0, 4);
  const recentFeedback = data.recent_submissions.filter((item) => item.feedback || item.grade != null).slice(0, 3);

  return <div className="fade-up space-y-6">
    <PageHeading eyebrow="Your learning space · demo data" title={`You're making progress, ${student.full_name.split(' ')[0]}.`} description="Here's how things are going and what you can do next." action={<Link href="/student/support" className="inline-flex items-center gap-2 rounded-lg border border-cyan-200/20 px-3 py-2 text-xs text-cyan-100 hover:bg-cyan-200/5">Find support <ArrowRight size={14} /></Link>} />
    <div className="grid gap-3 sm:grid-cols-3"><Metric label="Current GPA" value={student.current_gpa.toFixed(2)} detail={`${student.current_gpa >= student.previous_gpa ? 'Up' : 'Down'} from ${student.previous_gpa.toFixed(2)} previously`} color="cyan" /><Metric label="Attendance" value={`${student.attendance.toFixed(0)}%`} detail="Your recorded attendance" color="mint" /><Metric label="Assessment progress" value={`${student.assessment.toFixed(0)}%`} detail={`${student.assignments_completed} assignments completed`} color="amber" /></div>
    <div className="grid gap-4 xl:grid-cols-[1.35fr_.8fr]">
      <section className="surface rounded-xl p-5"><PanelTitle title="Your progress trend" /><p className="-mt-2 mb-3 text-xs text-slate-500">Dated attendance and assessment observations</p>{chartData.length ? <div className="h-64"><ResponsiveContainer width="100%" height="100%"><LineChart data={chartData} margin={{ left: -20, right: 8, top: 8, bottom: 0 }}><CartesianGrid stroke="rgba(148,167,189,.1)" vertical={false} /><XAxis dataKey="date" tick={{ fill: '#71839a', fontSize: 10 }} axisLine={false} tickLine={false} /><YAxis domain={[0, 100]} tick={{ fill: '#71839a', fontSize: 10 }} axisLine={false} tickLine={false} /><Tooltip contentStyle={{ background: '#101929', border: '1px solid #26364d', borderRadius: 8, fontSize: 11 }} /><Line type="monotone" dataKey="attendance" stroke="#65d7df" strokeWidth={2} dot={{ r: 2, fill: '#65d7df' }} /><Line type="monotone" dataKey="assessment" stroke="#94a8ff" strokeWidth={2} dot={{ r: 2, fill: '#94a8ff' }} /></LineChart></ResponsiveContainer><div className="mt-2 flex gap-4 text-[10px] text-slate-400"><span><i className="mr-1.5 inline-block size-1.5 rounded-full bg-cyan-200" />Attendance</span><span><i className="mr-1.5 inline-block size-1.5 rounded-full bg-indigo-200" />Assessment</span></div></div> : <Empty title="Your trend is taking shape" detail="More dated observations will appear as your term progresses." />}</section>
      <section className="surface rounded-xl p-5"><PanelTitle title="What's coming up" href="/student/assignments" />{upcoming.length ? <div className="space-y-2">{upcoming.map((item) => <Link key={item.id} href="/student/assignments" className="flex items-start gap-3 rounded-lg border border-white/6 p-3 hover:border-cyan-200/20"><span className="grid size-8 shrink-0 place-items-center rounded-md bg-amber-100/10 text-amber-100"><CalendarDays size={15} /></span><span className="min-w-0"><span className="block truncate text-xs font-medium">{item.title}</span><span className="mt-1 block text-[10px] text-slate-500">Due {new Date(item.due_date!).toLocaleDateString()}</span></span></Link>)}</div> : <Empty title="No deadlines listed" detail="Published assignments will show up here." />}</section>
    </div>
    <div className="grid gap-4 lg:grid-cols-2">
      <section className="surface rounded-xl p-5"><PanelTitle title="Recent feedback" href="/student/assignments" />{recentFeedback.length ? <div className="space-y-3">{recentFeedback.map((item) => { const assignment = data.assignments.find((row) => row.id === item.assignment_id); return <div key={item.id} className="border-t border-white/6 pt-3 first:border-0 first:pt-0"><div className="flex items-center justify-between"><span className="text-xs font-medium text-slate-200">{assignment?.title ?? 'Assignment feedback'}</span>{item.grade != null && <span className="text-xs text-cyan-100">{item.grade} marks</span>}</div>{item.feedback && <p className="mt-1 text-xs leading-5 text-slate-400">{item.feedback}</p>}</div>; })}</div> : <Empty title="Feedback will appear here" detail="Once work is reviewed, you can revisit the notes here." />}</section>
      <section className="surface rounded-xl p-5"><PanelTitle title="A good next step" /><div className="flex gap-4 rounded-lg border border-emerald-200/10 bg-emerald-200/[.035] p-4"><span className="grid size-9 shrink-0 place-items-center rounded-lg bg-emerald-200/10 text-emerald-100"><GraduationCap size={17} /></span><div><p className="text-sm font-medium text-slate-100">Keep your study rhythm steady</p><p className="mt-1 text-xs leading-5 text-slate-400">Check upcoming coursework and choose one small task to start today.</p><Link href="/student/assignments" className="mt-3 inline-flex items-center gap-1 text-xs text-emerald-100">Review assignments <ArrowRight size={13} /></Link></div></div><div className="mt-3 flex items-center gap-2 text-[10px] text-slate-600"><CircleCheck size={12} />Personal learning suggestions, not risk scores.</div></section>
    </div>
  </div>;
}