import PortalShell from '@/components/PortalShell';

export default function TeacherLayout({ children }: { children: React.ReactNode }) {
  return <PortalShell role="TEACHER">{children}</PortalShell>;
}
