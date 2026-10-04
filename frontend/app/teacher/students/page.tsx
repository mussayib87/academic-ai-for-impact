'use client';

import { ArrowDown, ArrowUp, Download, Search, SlidersHorizontal, UserRoundSearch } from 'lucide-react';
import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import { Empty, ErrorNotice, PageHeading, RiskBadge } from '@/components/ui';
import { API_BASE, api, readToken } from '@/lib/api';
import { formatRiskProbability } from '@/lib/risk';

type Student = { id: number; student_id: string; full_name: string; program?: string; year?: string; department?: string; section?: string; risk_level: string; risk_probability: number; attendance: number; current_gpa: number; momentum_trend?: string; assignments_completed: number };
type DirectoryResponse = { items: Student[]; total: number };

export default function StudentsPage() {
  const [items, setItems] = useState<Student[]>([]);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState('');
  const [risk, setRisk] = useState('');
  const [department, setDepartment] = useState('');
  const [section, setSection] = useState('');
  const [course, setCourse] = useState('');
  const [momentum, setMomentum] = useState('');
  const [attendanceBand, setAttendanceBand] = useState('');
  const [sort, setSort] = useState('full_name');
  const [descending, setDescending] = useState(false);
  const [page, setPage] = useState(0);
  const [error, setError] = useState('');
  const pageSize = 25;

  const query = useMemo(() => {
    const params = new URLSearchParams({ offset: String(page * pageSize), limit: String(pageSize), sort, direction: descending ? 'desc' : 'asc' });
    if (search.trim()) params.set('search', search.trim());
    if (risk) params.set('risk', risk);
    if (department) params.set('department', department);
    if (section) params.set('section', section);
    if (course) params.set('course', course);
    if (momentum) params.set('momentum', momentum);
    if (attendanceBand === 'low') params.set('attendance_max', '74.99');
    if (attendanceBand === 'watch') { params.set('attendance_min', '75'); params.set('attendance_max', '84.99'); }
    if (attendanceBand === 'steady') params.set('attendance_min', '85');
    return params.toString();
  }, [page, search, risk, department, section, course, momentum, attendanceBand, sort, descending]);

  useEffect(() => {
    api<DirectoryResponse>(`/api/v1/students?${query}`).then((result) => { setItems(result.items); setTotal(result.total); setError(''); }).catch((requestError: Error) => setError(requestError.message));
  }, [query]);

  const toggleSort = (key: string) => { if (sort === key) setDescending(!descending); else { setSort(key); setDescending(false); } };
  const exportCsv = async () => {
    const response = await fetch(`${API_BASE}/api/v1/reports/export.csv`, { headers: { Authorization: `Bearer ${readToken() ?? ''}` } });
    if (!response.ok) { setError('Could not export this report.'); return; }
    const link = document.createElement('a');
    link.href = URL.createObjectURL(await response.blob());
    link.download = 'student-risk-report.csv';
    link.click();
    URL.revokeObjectURL(link.href);
  };

  return <div className="fade-up">
    <PageHeading eyebrow="Student directory · demo data" title="Students" description="Find the right student and understand the signals that changed." action={<button type="button" onClick={exportCsv} className="inline-flex h-10 items-center gap-2 rounded-lg border border-white/10 px-3 text-xs font-medium text-slate-200 hover:bg-white/5"><Download size={15} /> Export CSV</button>} />
    <div className="surface rounded-xl p-4 sm:p-5">
      <p className="mb-3 text-xs text-slate-500">Risk is the classifier&apos;s most probable class; its probability is shown alongside it.</p>
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
        <label className="relative min-w-52 flex-1"><Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" /><span className="sr-only">Search students</span><input value={search} onChange={(event) => { setSearch(event.target.value); setPage(0); }} placeholder="Search name or student ID" className="h-10 w-full rounded-lg border border-white/10 bg-[#0b1320] pl-9 pr-3 text-sm outline-none focus:border-cyan-200/50" /></label>
        <div className="flex flex-wrap items-center gap-2"><SlidersHorizontal size={15} className="mr-1 hidden text-slate-500 sm:block" />
          <select aria-label="Filter by risk" value={risk} onChange={(event) => { setRisk(event.target.value); setPage(0); }} className="h-10 rounded-lg border border-white/10 bg-[#0b1320] px-3 text-xs text-slate-300"><option value="">All risks</option><option>HIGH</option><option>MEDIUM</option><option>LOW</option></select>
          <select aria-label="Filter by department" value={department} onChange={(event) => { setDepartment(event.target.value); setPage(0); }} className="h-10 max-w-40 rounded-lg border border-white/10 bg-[#0b1320] px-3 text-xs text-slate-300"><option value="">All departments</option>{['Engineering', 'Sciences', 'Humanities', 'Business'].map((value) => <option key={value}>{value}</option>)}</select>
          <select aria-label="Filter by course" value={course} onChange={(event) => { setCourse(event.target.value); setPage(0); }} className="h-10 rounded-lg border border-white/10 bg-[#0b1320] px-3 text-xs text-slate-300"><option value="">All courses</option><option value="AF-101-A">AF-101-A</option></select>
            <select aria-label="Filter by section" value={section} onChange={(event) => { setSection(event.target.value); setPage(0); }} className="h-10 rounded-lg border border-white/10 bg-[#0b1320] px-3 text-xs text-slate-300"><option value="">All sections</option>{['A', 'B', 'C', 'D'].map((value) => <option key={value}>{value}</option>)}</select>
          <select aria-label="Filter by momentum" value={momentum} onChange={(event) => { setMomentum(event.target.value); setPage(0); }} className="h-10 rounded-lg border border-white/10 bg-[#0b1320] px-3 text-xs text-slate-300"><option value="">All momentum</option>{['IMPROVING', 'STABLE', 'DECLINING', 'VOLATILE', 'INSUFFICIENT_DATA'].map((value) => <option key={value}>{value}</option>)}</select>
          <select aria-label="Filter by attendance" value={attendanceBand} onChange={(event) => { setAttendanceBand(event.target.value); setPage(0); }} className="h-10 rounded-lg border border-white/10 bg-[#0b1320] px-3 text-xs text-slate-300"><option value="">All attendance</option><option value="low">Below 75%</option><option value="watch">75–84%</option><option value="steady">85% and above</option></select>
        </div>
      </div>
      {error && <div className="mt-4"><ErrorNotice message={error} /></div>}
      <div className="mt-4 overflow-x-auto"><table className="w-full min-w-[1030px] text-left text-xs"><thead className="border-b border-white/8 text-[10px] uppercase tracking-[.1em] text-slate-500"><tr>
        {([['full_name', 'Student'], ['student_id', 'Student ID'], ['department', 'Program'], ['risk_level', 'Risk'], ['risk_probability', 'Class probability'], ['attendance', 'Attendance'], ['current_gpa', 'Performance'], ['momentum_trend', 'Momentum'], ['assignments_completed', 'Assignment engagement']] as const).map(([key, label]) => <th key={key} className="pb-3 pr-4 font-medium"><button type="button" onClick={() => toggleSort(key === 'student_id' || key === 'department' || key === 'momentum_trend' ? 'full_name' : key)} className="inline-flex items-center gap-1 hover:text-white">{label}{sort === key && (descending ? <ArrowDown size={11} /> : <ArrowUp size={11} />)}</button></th>)}<th className="pb-3 text-right font-medium">Action</th>
      </tr></thead><tbody>{items.map((student) => <tr key={student.id} className="border-b border-white/5 transition hover:bg-white/[.025]"><td className="py-3.5 pr-4"><Link href={`/teacher/students/${student.id}`} className="font-medium text-slate-100 hover:text-cyan-200">{student.full_name}</Link><div className="mt-1 text-[10px] text-slate-500">Year {student.year ?? '—'} · Section {student.section ?? '—'}</div></td><td className="py-3.5 pr-4 font-mono text-slate-400">{student.student_id}</td><td className="py-3.5 pr-4 text-slate-400">{student.department ?? student.program ?? '—'}</td><td className="py-3.5 pr-4"><RiskBadge level={student.risk_level} /></td><td className="py-3.5 pr-4 text-slate-300">{formatRiskProbability(student.risk_level, student.risk_probability)}</td><td className="py-3.5 pr-4"><span className={student.attendance < 75 ? 'text-rose-200' : 'text-slate-300'}>{student.attendance.toFixed(0)}%</span></td><td className="py-3.5 pr-4 text-slate-300">{student.current_gpa.toFixed(2)} GPA</td><td className="py-3.5 pr-4"><span className={student.momentum_trend === 'DECLINING' ? 'text-rose-200' : student.momentum_trend === 'IMPROVING' ? 'text-emerald-200' : 'text-slate-300'}>{student.momentum_trend?.replace('_', ' ') ?? '—'}</span></td><td className="py-3.5 pr-4 text-slate-300">{student.assignments_completed} completed</td><td className="py-3.5 text-right"><Link href={`/teacher/students/${student.id}`} aria-label={`View ${student.full_name}`} className="inline-flex rounded-md border border-white/10 px-2.5 py-1.5 text-[10px] text-slate-300 hover:border-cyan-200/30 hover:text-cyan-100">View profile</Link></td></tr>)}</tbody></table></div>
      {!error && !items.length && <div className="py-8"><Empty title="No students match these filters" detail="Try adjusting the risk, attendance, or department filters." /></div>}
      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-white/8 pt-4"><div className="text-xs text-slate-500"><UserRoundSearch size={14} className="mr-1.5 inline" />{total.toLocaleString()} students · fictional dataset</div><div className="flex items-center gap-2"><button type="button" disabled={page === 0} onClick={() => setPage(page - 1)} className="rounded-md border border-white/10 px-3 py-2 text-xs text-slate-300 disabled:opacity-40">Previous</button><span className="min-w-20 text-center text-xs text-slate-500">Page {page + 1} / {Math.max(1, Math.ceil(total / pageSize))}</span><button type="button" disabled={(page + 1) * pageSize >= total} onClick={() => setPage(page + 1)} className="rounded-md border border-white/10 px-3 py-2 text-xs text-slate-300 disabled:opacity-40">Next</button></div></div>
    </div>
  </div>;
}