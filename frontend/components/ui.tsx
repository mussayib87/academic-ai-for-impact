import { ArrowUpRight } from 'lucide-react';
import Link from 'next/link';

export function PageHeading({ eyebrow, title, description, action }: { eyebrow: string; title: string; description?: string; action?: React.ReactNode }) {
  return <div className="mb-7 flex flex-wrap items-end justify-between gap-4"><div><p className="eyebrow">{eyebrow}</p><h1 className="mt-2 text-3xl font-semibold tracking-normal text-white">{title}</h1>{description && <p className="mt-2 max-w-2xl text-sm text-slate-400">{description}</p>}</div>{action}</div>;
}

export function RiskBadge({ level }: { level: string }) {
  const style = level === 'HIGH' ? 'border-rose-300/20 bg-rose-300/10 text-rose-200' : level === 'MEDIUM' ? 'border-amber-200/20 bg-amber-200/10 text-amber-100' : 'border-emerald-200/20 bg-emerald-200/10 text-emerald-100';
  return <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] font-semibold tracking-[.08em] ${style}`}><span className="size-1.5 rounded-full bg-current" />{level}</span>;
}

export function Metric({ label, value, detail, color = 'cyan', href }: { label: string; value: string | number; detail: string; color?: 'cyan' | 'rose' | 'amber' | 'mint'; href?: string }) {
  const colors = { cyan: 'text-cyan-200', rose: 'text-rose-200', amber: 'text-amber-100', mint: 'text-emerald-200' };
  const content = <div className="surface group relative min-h-32 overflow-hidden rounded-xl p-4 transition hover:border-white/20 sm:p-5"><div className="flex items-start justify-between"><span className="text-xs font-medium text-slate-400">{label}</span>{href && <ArrowUpRight size={14} className="text-slate-600 transition group-hover:text-cyan-200" />}</div><div className={`mt-4 text-3xl font-semibold ${colors[color]}`}>{value}</div><div className="mt-1 text-[11px] text-slate-500">{detail}</div></div>;
  return href ? <Link href={href}>{content}</Link> : content;
}

export function Empty({ title, detail }: { title: string; detail: string }) {
  return <div className="rounded-lg border border-dashed border-white/10 px-5 py-8 text-center"><div className="text-sm font-medium text-slate-300">{title}</div><p className="mt-1 text-xs text-slate-500">{detail}</p></div>;
}

export function ErrorNotice({ message }: { message: string }) {
  return <div role="alert" className="whitespace-pre-line rounded-lg border border-rose-300/20 bg-rose-300/5 px-4 py-3 text-sm text-rose-100">{message}</div>;
}

export function PanelTitle({ title, href, linkLabel = 'View all' }: { title: string; href?: string; linkLabel?: string }) {
  return <div className="mb-4 flex items-center justify-between"><h2 className="text-sm font-semibold text-slate-100">{title}</h2>{href && <Link href={href} className="text-xs text-cyan-200 hover:text-cyan-100">{linkLabel}</Link>}</div>;
}