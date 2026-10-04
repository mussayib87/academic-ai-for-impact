import './globals.css';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Academic AI for Impact',
  description: 'AI-powered academic support platform',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
