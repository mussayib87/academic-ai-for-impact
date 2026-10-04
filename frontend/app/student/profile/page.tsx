'use client';

import { UserRound } from 'lucide-react';
import { useEffect, useState } from 'react';
import { ErrorNotice, PageHeading } from '@/components/ui';
import { api } from '@/lib/api';

type Profile = { student_id: string; full_name: string; program?: string; year?: string; section?: string; department?: string; previous_gpa: number; current_gpa: number; attendance: number; assessment: number; assignments_completed: number };

export default function StudentProfilePage() {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [error, setError] = useState('');
  useEffect(() => { api<Profile>('/api/v1/students/me').then(setProfile).catch((requestError: Error) => setError(requestError.message)); }, []);
  if (error) return <ErrorNotice message={error} />;
  if (!profile) return <div className="skeleton h-64 rounded-xl" />;
  return <div className="fade-up"><PageHeading eyebrow="Your account" title="Profile" description="Your academic identity and current progress." /><section className="surface max-w-3xl rounded-xl p-6"><div className="flex items-center gap-4 border-b border-white/8 pb-5"><span className="grid size-12 place-items-center rounded-full bg-cyan-200/10 text-cyan-100"><UserRound size={22} /></span><div><h2 className="text-lg font-semibold text-white">{profile.full_name}</h2><p className="mt-1 font-mono text-xs text-slate-500">{profile.student_id}</p></div></div><dl className="mt-5 grid gap-x-8 gap-y-5 sm:grid-cols-2">{[['Program', profile.program], ['Department', profile.department], ['Year', profile.year], ['Section', profile.section], ['Previous GPA', profile.previous_gpa.toFixed(2)], ['Current GPA', profile.current_gpa.toFixed(2)], ['Attendance', `${profile.attendance.toFixed(0)}%`], ['Assessment progress', `${profile.assessment.toFixed(0)}%`]].map(([label, value]) => <div key={label}><dt className="text-[10px] uppercase tracking-[.1em] text-slate-500">{label}</dt><dd className="mt-1 text-sm text-slate-200">{value || 'Not provided'}</dd></div>)}</dl><p className="mt-6 border-t border-white/8 pt-4 text-[10px] text-slate-600">Only the signed-in student&apos;s own profile is shown.</p></section></div>;
}