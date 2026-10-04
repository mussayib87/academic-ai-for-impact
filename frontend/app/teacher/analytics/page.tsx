'use client';

import { Activity, Download, Info } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { ErrorNotice, Metric, PageHeading, RiskBadge } from '@/components/ui';
import { api } from '@/lib/api';

type Dashboard = { summary: { students: number; high_risk: number; medium_risk: number; low_risk: number } };
type Importance = { features: { name: string; importance: number }[] };
type Monitor = { transitions: { name: string; from: string; to: string; recorded_at: string }[] };

export default function TeacherAnalyticsPage() {
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [importance, setImportance] = useState<Importance | null>(null);
  const [monitor, setMonitor] = useState<Monitor | null>(null);
  const [error, setError] = useState('');
  useEffect(() => { Promise.all([api<Dashboard>('/api/v1/dashboard/teacher'), api<Importance>('/api/v1/risk/feature-importance'), api<Monitor>('/api/v1/risk/monitoring')]).then(([summary, factors, risk]) => { setDashboard(summary); setImportance(factors); setMonitor(risk); }).catch((requestError: Error) => setError(requestError.message)); }, []);
  if (error) return <ErrorNotice message={error} />;
  if (!dashboard || !importance || !monitor) return <div className="skeleton h-96 rounded-xl" />;
  return <div className="fade-up"><PageHeading eyebrow="Academic signals · demo model" title="Analytics" description="Explainable indicators that help faculty decide where to look more closely." />
    <div className="grid gap-3 sm:grid-cols-3"><Metric label="Students represented" value={dashboard.summary.students} detail="Fictional demo records" color="cyan" /><Metric label="Model-elevated" value={dashboard.summary.high_risk + dashboard.summary.medium_risk} detail="Current saved student levels" color="amber" /><Metric label="Recorded transitions" value={monitor.transitions.length} detail="Between consecutive snapshots" color="mint" /></div>
    <div className="mt-4 grid gap-4 xl:grid-cols-[1.1fr_.9fr]"><section className="surface rounded-xl p-5"><div className="flex items-start justify-between gap-3"><div><h2 className="text-sm font-semibold">Global feature contribution</h2><p className="mt-1 text-xs text-slate-500">Mean absolute SHAP value from the trained model.</p></div><Activity size={16} className="text-cyan-200" /></div><div className="mt-5 h-[340px]"><ResponsiveContainer width="100%" height="100%"><BarChart data={importance.features} layout="vertical" margin={{ left: 12, right: 20, top: 4, bottom: 4 }}><CartesianGrid stroke="rgba(148,167,189,.1)" horizontal={false} /><XAxis type="number" tick={{ fill: '#71839a', fontSize: 10 }} axisLine={false} tickLine={false} /><YAxis type="category" dataKey="name" width={132} tickFormatter={(value: string) => value.replaceAll('_', ' ')} tick={{ fill: '#a1b0c3', fontSize: 10 }} axisLine={false} tickLine={false} /><Tooltip contentStyle={{ background: '#101929', border: '1px solid #26364d', borderRadius: 8, fontSize: 11 }} /><Bar dataKey="importance" fill="#65d7df" radius={[0, 4, 4, 0]} /></BarChart></ResponsiveContainer></div><div className="mt-3 flex gap-2 rounded-lg border border-indigo-200/10 bg-indigo-200/[.03] p-3 text-[10px] leading-5 text-slate-500"><Info size={13} className="mt-0.5 shrink-0 text-indigo-100" />Feature contributions describe this trained demonstration model; they are not causal findings or validated institutional thresholds.</div></section>
      <section className="surface rounded-xl p-5"><h2 className="text-sm font-semibold">Recent risk transitions</h2><p className="mt-1 text-xs text-slate-500">Snapshot-to-snapshot changes for faculty review.</p><div className="mt-4 space-y-2">{monitor.transitions.slice(-12).reverse().map((item, index) => <div key={`${item.name}-${index}`} className="flex items-center gap-3 border-t border-white/6 py-3"><div className="min-w-0 flex-1"><div className="truncate text-xs font-medium text-slate-200">{item.name}</div><div className="mt-1 text-[10px] text-slate-500">{new Date(item.recorded_at).toLocaleDateString()}</div></div><div className="flex items-center gap-1"><RiskBadge level={item.from} /><span className="text-slate-600">→</span><RiskBadge level={item.to} /></div></div>)}{!monitor.transitions.length && <p className="py-6 text-xs text-slate-500">No risk transitions have been recorded.</p>}</div></section></div>
  </div>;
}