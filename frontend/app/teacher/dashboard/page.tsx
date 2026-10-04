'use client';

import { motion } from 'framer-motion';
import { ArrowRight, CalendarClock, CheckCheck, ClipboardList, Sparkles, UsersRound } from 'lucide-react';
import Link from 'next/link';
import { useEffect, useState } from 'react';
import { Empty, ErrorNotice, Metric, PageHeading, PanelTitle, RiskBadge } from '@/components/ui';
import { api } from '@/lib/api';
import { formatRiskProbability } from '@/lib/risk';

type Student = { id: number; full_name: string; student_id: string; program?: string; department?: string; risk_level: string; risk_probability: number; attendance: number; current_gpa: number };
type Assignment = { id: number; title: string; subject: string; course?: string; due_date?: string | null };
type Dashboard = { teacher_name: string; summary: { students: number; assignments: number; submissions: number; pending_reviews: number; intervention_drafts: number; high_risk: number; medium_risk: number; low_risk: number }; students_needing_attention: Student[]; assignments: Assignment[]; upcoming_deadlines: Assignment[] };
type Submission = { id: number; status: string; assignment_id: number; submitted_at?: string | null; grade?: number | null };

const dayPart = () => {
  const hour = new Date().getHours();
  return hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening';
};

export default function TeacherDashboard() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [submissions, setSubmissions] = useState<Submission[]>([]);
  const [error, setError] = useState('');
  useEffect(() => {
    Promise.all([api<Dashboard>('/api/v1/dashboard/teacher'), api<Submission[]>('/api/v1/submissions')])
      .then(([dashboard, recent]) => { setData(dashboard); setSubmissions(recent); })
      .catch((requestError: Error) => setError(requestError.message));
  }, []);

  if (error) return <ErrorNotice message={error} />;
  if (!data) return <div className="space-y-5"><div className="skeleton h-28 rounded-xl" /><div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{[1, 2, 3, 4].map((item) => <div key={item} className="skeleton h-32 rounded-xl" />)}</div><div className="skeleton h-72 rounded-xl" /></div>;

  const priorities = [
    { name: 'Early warnings', count: data.summary.high_risk + data.summary.medium_risk, detail: 'students need a check-in', icon: UsersRound, href: '/teacher/early-warnings', color: 'text-rose-200' },
    { name: 'Pending reviews', count: data.summary.pending_reviews, detail: 'submissions waiting', icon: ClipboardList, href: '/teacher/assignments', color: 'text-amber-100' },
    { name: 'AI drafts', count: data.summary.intervention_drafts, detail: 'need faculty review', icon: Sparkles, href: '/teacher/interventions', color: 'text-indigo-200' },
    { name: 'Deadlines', count: data.upcoming_deadlines.length, detail: 'coming up next', icon: CalendarClock, href: '/teacher/assignments', color: 'text-cyan-200' },
  ];

  return <div className="fade-up space-y-7">
    <PageHeading eyebrow="Faculty workspace · demo data" title={`${dayPart()}, ${data.teacher_name.split(' ')[1] ?? data.teacher_name}`} description="What needs your attention today." action={<div className="rounded-full border border-emerald-200/15 bg-emerald-200/5 px-3 py-1.5 text-[10px] font-semibold tracking-[.1em] text-emerald-100">FICTIONAL DEMO DATA</div>} />
    <p className="text-xs text-slate-500">Risk probability is the model confidence for each displayed class.</p>

    <section aria-label="Priority summary" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {priorities.map((item, index) => <motion.div key={item.name} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: index * .06 }}><Link href={item.href} className="surface group block rounded-xl p-4 transition hover:-translate-y-0.5 hover:border-white/20"><div className="flex items-center justify-between"><div className="flex items-center gap-2 text-xs font-medium text-slate-400"><item.icon size={15} className={item.color} />{item.name}</div><ArrowRight size={14} className="text-slate-600 group-hover:text-white" /></div><div className="mt-4 flex items-baseline gap-2"><span className={`text-3xl font-semibold ${item.color}`}>{item.count}</span><span className="text-xs text-slate-500">{item.detail}</span></div></Link></motion.div>)}
    </section>

    <section className="surface overflow-hidden rounded-xl">
      <div className="flex flex-wrap items-end justify-between gap-3 border-b border-white/8 px-5 py-4"><div><p className="eyebrow">Priorities for today</p><h2 className="mt-1 text-lg font-semibold">Start with a person, not a chart</h2></div><Link href="/teacher/students" className="text-xs text-cyan-200 hover:text-white">Open student directory <ArrowRight size={13} className="ml-1 inline" /></Link></div>
      <div className="grid gap-0 md:grid-cols-3">
        <div className="border-b border-white/8 p-5 md:border-b-0 md:border-r"><div className="text-3xl font-semibold text-rose-200">{data.summary.high_risk + data.summary.medium_risk}</div><p className="mt-1 text-xs text-slate-400">students currently flagged for attention</p></div>
        <div className="border-b border-white/8 p-5 md:border-b-0 md:border-r"><div className="text-3xl font-semibold text-amber-100">{data.summary.pending_reviews}</div><p className="mt-1 text-xs text-slate-400">submissions waiting for your review</p></div>
        <div className="p-5"><div className="text-3xl font-semibold text-indigo-200">{data.summary.intervention_drafts}</div><p className="mt-1 text-xs text-slate-400">AI drafts require faculty approval</p></div>
      </div>
    </section>

    <div className="grid gap-4 xl:grid-cols-[1.45fr_.85fr]">
      <section className="surface min-w-0 rounded-xl p-5"><PanelTitle title="Students needing attention" href="/teacher/students" /><div className="overflow-x-auto"><table className="w-full min-w-[650px] text-left text-xs"><thead className="text-[10px] uppercase tracking-[.12em] text-slate-500"><tr><th className="pb-3 font-medium">Student</th><th className="pb-3 font-medium">Risk</th><th className="pb-3 font-medium">Class probability</th><th className="pb-3 font-medium">Reason</th><th className="pb-3" /></tr></thead><tbody>{data.students_needing_attention.slice(0, 7).map((student) => <tr key={student.id} className="border-t border-white/6"><td className="py-3"><Link href={`/teacher/students/${student.id}`} className="font-medium text-slate-100 hover:text-cyan-200">{student.full_name}</Link><div className="mt-1 font-mono text-[10px] text-slate-500">{student.student_id}</div></td><td className="py-3"><RiskBadge level={student.risk_level} /></td><td className="py-3 text-slate-400">{formatRiskProbability(student.risk_level, student.risk_probability)}</td><td className="py-3 text-slate-400">{student.attendance < 75 ? 'Attendance below 75%' : 'Academic indicators need review'}</td><td className="py-3 text-right"><Link aria-label={`Open ${student.full_name}`} href={`/teacher/students/${student.id}`}><ArrowRight size={15} className="text-slate-500 hover:text-cyan-200" /></Link></td></tr>)}</tbody></table></div>{!data.students_needing_attention.length && <Empty title="No immediate student flags" detail="New signals will appear here as academic data is recorded." />}</section>

      <section className="surface rounded-xl p-5"><PanelTitle title="Upcoming deadlines" href="/teacher/assignments" />{data.upcoming_deadlines.length ? <div className="space-y-1">{data.upcoming_deadlines.slice(0, 6).map((item) => <div key={item.id} className="flex items-start gap-3 border-t border-white/6 py-3 first:border-0"><span className="mt-1 grid size-8 shrink-0 place-items-center rounded-lg bg-cyan-300/10 text-cyan-200"><CalendarClock size={15} /></span><div className="min-w-0 flex-1"><div className="truncate text-sm font-medium">{item.title}</div><div className="mt-1 text-[11px] text-slate-500">{item.course ?? item.subject} · {item.due_date ? new Date(item.due_date).toLocaleDateString() : 'No due date'}</div></div></div>)}</div> : <Empty title="No upcoming deadlines" detail="Published assignments will appear here." />}</section>
    </div>

    <div className="grid gap-4 xl:grid-cols-[1.1fr_.9fr]">
      <section className="surface rounded-xl p-5"><PanelTitle title="Assignment activity" href="/teacher/assignments" /><div className="space-y-2">{data.assignments.slice(0, 5).map((assignment) => {
        const count = submissions.filter((item) => item.assignment_id === assignment.id).length;
        return <div key={assignment.id} className="flex items-center gap-3 rounded-lg border border-white/6 bg-black/10 px-3 py-3"><span className="grid size-8 place-items-center rounded-md bg-indigo-300/10 text-indigo-200"><CheckCheck size={15} /></span><div className="min-w-0 flex-1"><div className="truncate text-xs font-medium">{assignment.title}</div><div className="mt-1 text-[10px] text-slate-500">{assignment.course ?? assignment.subject}</div></div><span className="text-xs text-slate-400">{count} received</span></div>;
      })}{!data.assignments.length && <Empty title="No active assignments" detail="Create an assignment when the next class task is ready." />}</div></section>

      <section className="surface rounded-xl p-5"><PanelTitle title="Academic health overview" href="/teacher/risk-monitoring" /><div className="data-grid rounded-lg border border-white/6 p-4"><div className="mb-4 flex items-baseline justify-between"><span className="text-xs text-slate-400">Enrolled students</span><span className="text-xl font-semibold text-white">{data.summary.students}</span></div><div className="space-y-4">{([['High risk', data.summary.high_risk, 'bg-rose-300'], ['Medium risk', data.summary.medium_risk, 'bg-amber-200'], ['Low risk', data.summary.low_risk, 'bg-emerald-300']] as const).map(([label, count, color]) => <div key={label}><div className="mb-1.5 flex justify-between text-[11px]"><span className="text-slate-400">{label}</span><span className="text-slate-300">{count}</span></div><div className="h-1.5 overflow-hidden rounded-full bg-white/5"><div className={`h-full rounded-full ${color}`} style={{ width: `${data.summary.students ? count / data.summary.students * 100 : 0}%` }} /></div></div>)}</div></div></section>
    </div>
  </div>;
}