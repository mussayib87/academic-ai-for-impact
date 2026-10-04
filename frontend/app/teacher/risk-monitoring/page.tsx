'use client';

import { ArrowDownRight, ArrowUpRight, Minus, TrendingUp } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Empty, ErrorNotice, Metric, PageHeading, RiskBadge } from '@/components/ui';
import { api } from '@/lib/api';

type MonitorData = { distribution: Record<string, number>; momentum: Record<string, number>; transitions: { student_id: number; name: string; from: string; to: string; recorded_at: string }[]; history_note: string; history: { student_id: number; risk_level: string; recorded_at: string }[] };

export default function RiskMonitoringPage() {
  const [data, setData] = useState<MonitorData | null>(null);
  const [error, setError] = useState('');
  useEffect(() => { api<MonitorData>('/api/v1/risk/monitoring').then(setData).catch((requestError: Error) => setError(requestError.message)); }, []);
  const trend = useMemo(() => {
    if (!data) return [];
    const weeks = new Map<string, { date: string; HIGH: number; MEDIUM: number; LOW: number }>();
    for (const item of data.history) {
      const week = new Date(item.recorded_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
      const row = weeks.get(week) ?? { date: week, HIGH: 0, MEDIUM: 0, LOW: 0 };
      const level = item.risk_level as 'HIGH' | 'MEDIUM' | 'LOW';
      row[level] = (row[level] ?? 0) + 1;
      weeks.set(week, row);
    }
    return Array.from(weeks.values()).slice(-12);
  }, [data]);
  if (error) return <ErrorNotice message={error} />;
  if (!data) return <div className="skeleton h-80 rounded-xl" />;
  return <div className="fade-up"><PageHeading eyebrow="Risk monitoring · dated records" title="Risk, in motion" description="Track where students move between levels and where support may be helping." />
    <div className="grid gap-3 sm:grid-cols-3"><Metric label="High risk" value={data.distribution.HIGH ?? 0} detail="Current student records" color="rose" /><Metric label="Medium risk" value={data.distribution.MEDIUM ?? 0} detail="Current student records" color="amber" /><Metric label="Low risk" value={data.distribution.LOW ?? 0} detail="Current student records" color="mint" /></div>
    <section className="surface mt-3 rounded-xl p-4"><div className="mb-3 text-[10px] uppercase tracking-[.1em] text-slate-500">Academic momentum · dated assessments</div><div className="grid grid-cols-2 gap-3 sm:grid-cols-4">{(['IMPROVING', 'STABLE', 'DECLINING', 'VOLATILE'] as const).map((level) => <div key={level} className="rounded-lg border border-white/6 bg-black/10 p-3"><div className="text-[10px] text-slate-500">{level}</div><div className="mt-1 text-xl font-semibold text-slate-100">{data.momentum[level] ?? 0}</div></div>)}</div><p className="mt-3 text-[10px] text-slate-600">Students with fewer than four observations: {data.momentum.INSUFFICIENT_DATA ?? 0}. Trends are not classified before the minimum history is met.</p></section>
    <div className="mt-4 grid gap-4 xl:grid-cols-[1.15fr_.85fr]"><section className="surface rounded-xl p-5"><div className="flex items-center gap-2"><TrendingUp size={15} className="text-cyan-200" /><h2 className="text-sm font-semibold">Recorded risk snapshots</h2></div><p className="mt-1 text-xs text-slate-500">{data.history_note}</p>{trend.length ? <div className="mt-4 h-72"><ResponsiveContainer width="100%" height="100%"><BarChart data={trend}><CartesianGrid stroke="rgba(148,167,189,.1)" vertical={false} /><XAxis dataKey="date" tick={{ fill: '#71839a', fontSize: 10 }} axisLine={false} tickLine={false} /><YAxis tick={{ fill: '#71839a', fontSize: 10 }} axisLine={false} tickLine={false} /><Tooltip contentStyle={{ background: '#101929', border: '1px solid #26364d', borderRadius: 8, fontSize: 11 }} /><Bar dataKey="HIGH" stackId="risk" fill="#ff7f76" radius={[3, 3, 0, 0]} /><Bar dataKey="MEDIUM" stackId="risk" fill="#f3bd69" /><Bar dataKey="LOW" stackId="risk" fill="#70d9ad" /></BarChart></ResponsiveContainer></div> : <div className="mt-5"><Empty title="No risk snapshots yet" detail="Risk history appears once model predictions are saved." /></div>}</section>
      <section className="surface rounded-xl p-5"><h2 className="text-sm font-semibold">Risk transitions</h2><p className="mt-1 text-xs text-slate-500">Changes between consecutive recorded snapshots.</p><div className="mt-4 space-y-2">{data.transitions.map((item, index) => <div key={`${item.student_id}-${item.recorded_at}-${index}`} className="flex items-center gap-3 border-t border-white/6 py-3"><span className={`grid size-8 place-items-center rounded-full ${item.to === 'HIGH' ? 'bg-rose-300/10 text-rose-200' : item.to === 'LOW' ? 'bg-emerald-300/10 text-emerald-200' : 'bg-amber-200/10 text-amber-100'}`}>{item.to === 'HIGH' ? <ArrowUpRight size={15} /> : item.to === 'LOW' ? <ArrowDownRight size={15} /> : <Minus size={15} />}</span><div className="min-w-0 flex-1"><div className="truncate text-xs font-medium text-slate-200">{item.name}</div><div className="mt-1 text-[10px] text-slate-500">{new Date(item.recorded_at).toLocaleString()}</div></div><div className="flex items-center gap-1"><RiskBadge level={item.from} /><span className="text-slate-600">→</span><RiskBadge level={item.to} /></div></div>)}{!data.transitions.length && <Empty title="No level transitions" detail="New snapshots will make changes visible here." />}</div></section></div>
  </div>;
}