'use client';

import { motion } from 'framer-motion';
import { ArrowRight, BookOpenCheck, LockKeyhole } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { API_BASE } from '@/lib/api';

type LoginResponse = { access_token: string; user: { role: string } };

export default function LoginPage() {
  const [email, setEmail] = useState('teacher@example.com');
  const [password, setPassword] = useState('teacher123');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const router = useRouter();

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError('');
    try {
      const response = await fetch(`${API_BASE}/api/v1/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      });
      const data = await response.json() as LoginResponse | { detail?: string };
      if (!response.ok || !('access_token' in data)) throw new Error('detail' in data ? data.detail : 'Sign in failed');
      window.localStorage.setItem('token', data.access_token);
      router.push(data.user.role === 'TEACHER' ? '/teacher/dashboard' : '/student/dashboard');
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to reach the Academic AI API.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="relative grid min-h-screen overflow-hidden lg:grid-cols-[1.05fr_.95fr]">
      <section className="relative flex min-h-[42vh] flex-col justify-between border-b border-white/8 px-6 py-8 sm:px-12 lg:min-h-screen lg:border-b-0 lg:border-r lg:border-white/8 lg:px-16 lg:py-12">
        <div className="flex items-center gap-3"><span className="grid size-10 place-items-center rounded-lg border border-cyan-200/20 bg-cyan-300/10 text-cyan-200"><BookOpenCheck size={20} /></span><div className="text-sm font-semibold">Academic AI <span className="font-normal text-slate-500">for Impact</span></div></div>
        <div className="fade-up max-w-2xl py-12">
          <p className="eyebrow">Student support, made timely</p>
          <h1 className="mt-5 max-w-xl text-4xl font-semibold leading-[1.08] tracking-normal text-white sm:text-6xl">Notice the change.<br /><span className="text-cyan-200">Make room to help.</span></h1>
          <p className="mt-6 max-w-lg text-base leading-7 text-slate-400">A shared academic workspace for educators and students, built around early signals and thoughtful action.</p>
          <div className="mt-12 grid max-w-xl grid-cols-3 border-y border-white/10 py-5">
            <div><div className="text-xl font-semibold text-white">01</div><div className="mt-1 text-xs text-slate-500">Observe</div></div>
            <div className="border-l border-white/10 pl-5"><div className="text-xl font-semibold text-white">02</div><div className="mt-1 text-xs text-slate-500">Understand</div></div>
            <div className="border-l border-white/10 pl-5"><div className="text-xl font-semibold text-white">03</div><div className="mt-1 text-xs text-slate-500">Support</div></div>
          </div>
        </div>
        <div className="flex items-center gap-2 text-[11px] text-slate-600"><LockKeyhole size={13} /> Private academic workspace</div>
      </section>

      <section className="flex items-center justify-center px-5 py-12 sm:px-10">
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .4 }} className="w-full max-w-[410px]">
          <p className="eyebrow">Welcome back</p>
          <h2 className="mt-3 text-3xl font-semibold text-white">Sign in to continue</h2>
          <p className="mt-2 text-sm text-slate-400">Use your faculty or student account.</p>
          <form onSubmit={onSubmit} className="mt-8 space-y-5">
            <div><label htmlFor="email" className="mb-2 block text-xs font-medium text-slate-300">Email address</label><input id="email" type="email" autoComplete="username" required value={email} onChange={(event) => setEmail(event.target.value)} className="h-12 w-full rounded-lg border border-[var(--line)] bg-[#0b1320] px-4 text-sm text-white outline-none transition focus:border-cyan-300/70 focus:ring-2 focus:ring-cyan-300/10" /></div>
            <div><label htmlFor="password" className="mb-2 block text-xs font-medium text-slate-300">Password</label><input id="password" type="password" autoComplete="current-password" required value={password} onChange={(event) => setPassword(event.target.value)} className="h-12 w-full rounded-lg border border-[var(--line)] bg-[#0b1320] px-4 text-sm text-white outline-none transition focus:border-cyan-300/70 focus:ring-2 focus:ring-cyan-300/10" /></div>
            {error && <p role="alert" className="rounded-lg border border-rose-300/20 bg-rose-300/5 px-3 py-2 text-sm text-rose-200">{error}</p>}
            <button disabled={loading} className="group flex h-12 w-full items-center justify-center gap-2 rounded-lg bg-cyan-200 px-4 font-semibold text-[#07141b] transition hover:bg-cyan-100 disabled:cursor-wait disabled:opacity-60">{loading ? 'Signing in...' : 'Continue'}{!loading && <ArrowRight size={16} className="transition-transform group-hover:translate-x-1" />}</button>
          </form>
          <div className="surface-soft mt-7 rounded-lg p-4">
            <div className="eyebrow">Demo data account</div>
            <div className="mt-3 grid grid-cols-[72px_1fr] gap-y-2 text-xs"><span className="text-slate-500">Faculty</span><span className="font-mono text-slate-300">teacher@example.com / teacher123</span><span className="text-slate-500">Student</span><span className="font-mono text-slate-300">student@example.com / student123</span></div>
          </div>
          <p className="mt-5 text-center text-[10px] text-slate-600">Fictional demonstration accounts; do not use real student data.</p>
        </motion.div>
      </section>
    </main>
  );
}