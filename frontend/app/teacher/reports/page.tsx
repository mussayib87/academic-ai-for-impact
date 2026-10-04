'use client';

import { BarChart3, Download, FileSpreadsheet, UsersRound } from 'lucide-react';
import { useState } from 'react';
import { ErrorNotice, PageHeading } from '@/components/ui';
import { API_BASE, readToken } from '@/lib/api';

export default function ReportsPage() {
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const download = async (kind: 'risk' | 'class' | 'assignments' | 'interventions' | 'internal_marks') => {
    setBusy(true); setError('');
    try {
      const response = await fetch(`${API_BASE}/api/v1/reports/export.csv?report_type=${kind}`, { headers: { Authorization: `Bearer ${readToken() ?? ''}` } });
      if (!response.ok) throw new Error('Unable to export student data.');
      const url = URL.createObjectURL(await response.blob());
      const anchor = document.createElement('a'); anchor.href = url; anchor.download = `academic-${kind}-report.csv`; anchor.click(); URL.revokeObjectURL(url);
    } catch (requestError) { setError((requestError as Error).message); }
    finally { setBusy(false); }
  };
  return <div className="fade-up"><PageHeading eyebrow="Reports · faculty" title="Reports" description="Export a review-ready CSV of current academic and risk records." />{error && <div className="mb-4"><ErrorNotice message={error} /></div>}<section className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">{[
    { title: 'Student risk report', detail: 'Student ID, department, predicted class and its probability, attendance, assessments, GPA, and dated momentum.', icon: UsersRound, action: 'Download CSV', kind: 'risk' as const },
    { title: 'Class summary', detail: 'Current class size and risk distribution counts.', icon: BarChart3, action: 'Download CSV', kind: 'class' as const },
    { title: 'Assignment report', detail: 'Assigned, submitted, pending, late, and graded counts by assignment.', icon: FileSpreadsheet, action: 'Download CSV', kind: 'assignments' as const },
    { title: 'Internal marks register', detail: 'Subject-wise FA1, FA2, assignment, internal marks, attendance, and calculated totals.', icon: FileSpreadsheet, action: 'Download CSV', kind: 'internal_marks' as const },
    { title: 'Intervention report', detail: 'Student, faculty-reviewed draft status, and intervention text.', icon: FileSpreadsheet, action: 'Download CSV', kind: 'interventions' as const },
  ].map((report) => <article key={report.title} className="surface rounded-xl p-5"><span className="grid size-9 place-items-center rounded-lg bg-cyan-200/10 text-cyan-100"><report.icon size={17} /></span><h2 className="mt-4 text-sm font-semibold text-white">{report.title}</h2><p className="mt-2 min-h-10 text-xs leading-5 text-slate-400">{report.detail}</p><button onClick={() => void download(report.kind)} disabled={busy} className="mt-4 inline-flex items-center gap-2 rounded-lg bg-cyan-200 px-3 py-2.5 text-xs font-semibold text-[#07141b] disabled:opacity-50"><Download size={14} />{busy ? 'Preparing…' : report.action}</button></article>)}</section><p className="mt-4 text-[10px] text-slate-600">Exports contain fictional demo records. CSV is currently supported.</p></div>;
}