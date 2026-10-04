'use client';

import { ArrowRight, BellRing, Filter } from 'lucide-react';
import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import { Empty, ErrorNotice, PageHeading, RiskBadge } from '@/components/ui';
import { api } from '@/lib/api';

type Warning = { student_id: number; name: string; department?: string | null; course?: string | null; detected_at: string; risk_level: string; severity: string; signal: string; change: string; reason: string };

export default function EarlyWarningsPage() {
  const [items, setItems] = useState<Warning[]>([]);
  const [severity, setSeverity] = useState('');
  const [signal, setSignal] = useState('');
  const [department, setDepartment] = useState('');
  const [course, setCourse] = useState('');
  const [dateRange, setDateRange] = useState('30');
  const [error, setError] = useState('');
  useEffect(() => { api<Warning[]>('/api/v1/early-warnings').then(setItems).catch((requestError: Error) => setError(requestError.message)); }, []);
  const signals = Array.from(new Set(items.map((item) => item.signal)));
  const departments = Array.from(new Set(items.map((item) => item.department).filter((value): value is string => Boolean(value))));
  const courses = Array.from(new Set(items.map((item) => item.course).filter((value): value is string => Boolean(value))));
  const filtered = useMemo(() => items.filter((item) => {
    const afterDate = dateRange === 'all' || Date.now() - new Date(item.detected_at).getTime() <= Number(dateRange) * 86400000;
    return (!severity || item.severity === severity) && (!signal || item.signal === signal) && (!department || item.department === department) && (!course || item.course === course) && afterDate;
  }), [items, severity, signal, department, course, dateRange]);
  return <div className="fade-up"><PageHeading eyebrow="Signals · faculty review" title="Early warning center" description="Recent academic signals that may benefit from a timely, human check-in." action={<span className="inline-flex items-center gap-2 rounded-full border border-rose-200/15 bg-rose-200/5 px-3 py-1.5 text-[10px] text-rose-100"><BellRing size={12} />{filtered.length} signals</span>} />
    <div className="surface mb-4 flex flex-wrap items-center gap-2 rounded-xl p-3"><Filter size={14} className="ml-1 text-slate-500" /><select aria-label="Filter severity" value={severity} onChange={(event) => setSeverity(event.target.value)} className="h-9 rounded-md border border-white/10 bg-[#0b1320] px-3 text-xs text-slate-300"><option value="">All severities</option><option>HIGH</option><option>MEDIUM</option><option>LOW</option></select><select aria-label="Filter signal" value={signal} onChange={(event) => setSignal(event.target.value)} className="h-9 rounded-md border border-white/10 bg-[#0b1320] px-3 text-xs text-slate-300"><option value="">All signal types</option>{signals.map((item) => <option key={item}>{item}</option>)}</select>
      <select aria-label="Filter department" value={department} onChange={(event) => setDepartment(event.target.value)} className="h-9 rounded-md border border-white/10 bg-[#0b1320] px-3 text-xs text-slate-300"><option value="">All departments</option>{departments.map((item) => <option key={item}>{item}</option>)}</select>
      <select aria-label="Filter course" value={course} onChange={(event) => setCourse(event.target.value)} className="h-9 rounded-md border border-white/10 bg-[#0b1320] px-3 text-xs text-slate-300"><option value="">All courses</option>{courses.map((item) => <option key={item}>{item}</option>)}</select>
      <select aria-label="Filter date range" value={dateRange} onChange={(event) => setDateRange(event.target.value)} className="h-9 rounded-md border border-white/10 bg-[#0b1320] px-3 text-xs text-slate-300"><option value="7">Last 7 days</option><option value="30">Last 30 days</option><option value="90">Last 90 days</option><option value="all">Any date</option></select>
      <span className="ml-auto text-[10px] text-slate-600">Generated from dated academic records</span></div>
    {error && <ErrorNotice message={error} />}
    <section className="surface overflow-hidden rounded-xl"><div className="hidden grid-cols-[1.1fr_.55fr_1fr_1.2fr_.8fr_auto] gap-4 border-b border-white/8 px-5 py-3 text-[10px] uppercase tracking-[.1em] text-slate-500 md:grid"><span>Student</span><span>Predicted class</span><span>Signal · severity</span><span>Evidence</span><span>Detected</span><span>Action</span></div>{filtered.map((item, index) => <article key={`${item.student_id}-${item.signal}-${index}`} className="grid gap-3 border-b border-white/6 px-4 py-4 last:border-0 md:grid-cols-[1.1fr_.55fr_1fr_1.2fr_.8fr_auto] md:items-center md:gap-4 md:px-5"><div><Link href={`/teacher/students/${item.student_id}`} className="text-sm font-medium text-slate-100 hover:text-cyan-200">{item.name}</Link><div className="mt-1 text-[10px] text-slate-600">{item.department ?? 'Department not set'}</div></div><div><RiskBadge level={item.risk_level} /><div className="mt-1 text-[9px] text-slate-500">Signal severity: {item.severity}</div></div><div><div className="text-xs text-slate-300">{item.signal}</div><div className="mt-1 text-[10px] text-amber-100">{item.change}</div></div><p className="text-xs leading-5 text-slate-500">{item.reason}</p><span className="text-[10px] text-slate-500">{new Date(item.detected_at).toLocaleString()}</span><Link href={`/teacher/students/${item.student_id}`} className="inline-flex items-center gap-1 text-xs text-cyan-200">Review <ArrowRight size={13} /></Link></article>)}{!error && !filtered.length && <div className="p-5"><Empty title="No matching warnings" detail="Signals will appear as dated academic records meet the detection criteria." /></div>}</section>
  </div>;
}