'use client';

import { AnimatePresence, motion } from 'framer-motion';
import { Bell, BookOpenCheck, ChevronDown, LogOut, Menu, X } from 'lucide-react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { api } from '@/lib/api';

type Profile = { name: string; email: string; role: string };
type Notice = { id: number; title: string; body: string; read: boolean };

const teacherLinks = [
  ['Dashboard', '/teacher/dashboard'], ['Students', '/teacher/students'], ['Analytics', '/teacher/analytics'],
  ['Assignments', '/teacher/assignments'], ['Early Warnings', '/teacher/early-warnings'],
  ['Academic Data', '/teacher/academic-data'],
  ['Internal Marks', '/teacher/internal-marks'],
  ['Risk Monitoring', '/teacher/risk-monitoring'], ['AI Interventions', '/teacher/interventions'],
  ['Reports', '/teacher/reports'], ['Settings', '/teacher/settings'],
];
const studentLinks = [
  ['My progress', '/student/dashboard'], ['Assignments', '/student/assignments'],
  ['Subjects', '/student/subjects'], ['Support', '/student/support'], ['Profile', '/student/profile'],
];

export default function PortalShell({ children, role }: { children: React.ReactNode; role: 'TEACHER' | 'STUDENT' }) {
  const pathname = usePathname();
  const router = useRouter();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [notices, setNotices] = useState<Notice[]>([]);
  const [menuOpen, setMenuOpen] = useState(false);
  const [noticeOpen, setNoticeOpen] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    const token = window.localStorage.getItem('token');
    if (!token) {
      router.replace('/login');
      return;
    }
    Promise.all([api<Profile>('/api/v1/me'), api<Notice[]>('/api/v1/notifications')])
      .then(([current, items]) => {
        if (current.role !== role) {
          router.replace(current.role === 'TEACHER' ? '/teacher/dashboard' : '/student/dashboard');
          return;
        }
        setProfile(current);
        setNotices(items);
      })
      .catch((requestError: Error) => {
        setError(requestError.message);
        window.localStorage.removeItem('token');
        router.replace('/login');
      });
  }, [role, router]);

  const links = role === 'TEACHER' ? teacherLinks : studentLinks;
  const logout = () => {
    window.localStorage.removeItem('token');
    router.replace('/login');
  };

  return (
    <div className="min-h-screen text-[var(--text)]">
      <header className="sticky top-0 z-40 border-b border-[var(--line)] bg-[#080d17]/90 backdrop-blur-xl">
        <div className="mx-auto flex min-h-[68px] max-w-[1600px] items-center gap-6 px-4 sm:px-6 xl:px-9">
          <Link href={role === 'TEACHER' ? '/teacher/dashboard' : '/student/dashboard'} className="flex shrink-0 items-center gap-3">
            <span className="grid size-9 place-items-center rounded-lg border border-cyan-200/20 bg-cyan-300/10 text-cyan-200"><BookOpenCheck size={18} /></span>
            <span className="hidden sm:block">
              <span className="block text-[13px] font-semibold leading-tight">Academic AI</span>
              <span className="block text-[10px] tracking-[.18em] text-[var(--muted)]">FOR IMPACT</span>
            </span>
          </Link>

          <nav className="hidden min-w-0 flex-1 items-center gap-1 overflow-x-auto lg:flex" aria-label="Primary navigation">
            {links.map(([label, href]) => {
              const active = pathname === href || (href.endsWith('/students') && pathname.startsWith('/teacher/students/'));
              return <Link key={href} href={href} className={`whitespace-nowrap rounded-md px-2.5 py-2 text-[12px] transition-colors ${active ? 'bg-white/8 text-white' : 'text-slate-400 hover:bg-white/5 hover:text-slate-100'}`}>{label}</Link>;
            })}
          </nav>

          <div className="ml-auto flex shrink-0 items-center gap-2">
            <div className="relative">
              <button type="button" onClick={() => setNoticeOpen(!noticeOpen)} aria-label="Notifications" className="relative grid size-9 place-items-center rounded-lg text-slate-300 hover:bg-white/8">
                <Bell size={17} />
                {notices.some((item) => !item.read) && <span className="absolute right-2 top-2 size-1.5 rounded-full bg-[var(--coral)]" />}
              </button>
              <AnimatePresence>
                {noticeOpen && <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 6 }} className="surface absolute right-0 top-12 w-80 rounded-lg p-3 shadow-2xl">
                  <div className="mb-2 flex items-center justify-between"><span className="font-semibold">Notifications</span><button onClick={() => setNoticeOpen(false)} aria-label="Close notifications"><X size={15} /></button></div>
                  {notices.length ? notices.slice(0, 5).map((notice) => <div key={notice.id} className="border-t border-white/8 py-2"><div className="text-sm font-medium">{notice.title}</div><p className="mt-1 text-xs text-slate-400">{notice.body}</p></div>) : <p className="py-4 text-sm text-slate-400">You are all caught up.</p>}
                </motion.div>}
              </AnimatePresence>
            </div>
            <div className="hidden items-center gap-2 border-l border-white/10 pl-3 sm:flex">
              <span className="grid size-8 place-items-center rounded-full bg-indigo-300/15 text-xs font-semibold text-indigo-100">{profile?.name?.split(' ').map((part) => part[0]).slice(0, 2).join('') ?? 'AI'}</span>
              <div className="hidden xl:block"><div className="max-w-32 truncate text-xs font-medium">{profile?.name ?? 'Loading profile'}</div><div className="text-[10px] text-slate-500">{role}</div></div>
              <ChevronDown size={14} className="text-slate-500" />
            </div>
            <button type="button" onClick={logout} title="Log out" aria-label="Log out" className="hidden size-9 place-items-center rounded-lg text-slate-400 hover:bg-white/8 hover:text-white sm:grid"><LogOut size={16} /></button>
            <button type="button" onClick={() => setMenuOpen(!menuOpen)} aria-label={menuOpen ? 'Close navigation' : 'Open navigation'} className="grid size-9 place-items-center rounded-lg border border-white/10 text-slate-300 lg:hidden">{menuOpen ? <X size={18} /> : <Menu size={18} />}</button>
          </div>
        </div>
        <AnimatePresence>
          {menuOpen && <motion.nav initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden border-t border-white/8 px-4 pb-3 lg:hidden" aria-label="Mobile navigation">
            <div className="grid grid-cols-2 gap-1 pt-2 sm:grid-cols-3">{links.map(([label, href]) => <Link key={href} onClick={() => setMenuOpen(false)} href={href} className={`rounded-md px-3 py-2.5 text-xs ${pathname === href ? 'bg-white/10 text-white' : 'text-slate-400 hover:bg-white/5'}`}>{label}</Link>)}</div>
            <button type="button" onClick={logout} className="mt-2 flex items-center gap-2 px-3 py-2 text-xs text-rose-300"><LogOut size={14} /> Log out</button>
          </motion.nav>}
        </AnimatePresence>
      </header>
      <main className="mx-auto max-w-[1600px] px-4 pb-14 pt-7 sm:px-6 xl:px-9">{error ? <div role="alert" className="text-sm text-rose-300">{error}</div> : profile ? children : <div className="space-y-4"><div className="skeleton h-9 w-56 rounded-md" /><div className="skeleton h-28 rounded-xl" /></div>}</main>
      <div className="fixed bottom-3 right-4 hidden text-[10px] uppercase tracking-[.16em] text-slate-600 md:block">{role === 'TEACHER' ? 'Faculty workspace' : 'Student workspace'}</div>
    </div>
  );
}