import type { ReactNode } from 'react';
import { Sora } from 'next/font/google';
import './redesign.css';

const sora = Sora({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700', '800'],
  variable: '--font-sora',
  display: 'swap',
});

export const metadata = {
  title: 'Conecta PRO — Redesign',
};

// Layout isolado do redesign: aplica Sora + tokens (.rd-root) sem tocar no app vivo.
export default function RedesignLayout({ children }: { children: ReactNode }) {
  return (
    <div className={`${sora.variable} rd-root`}>
      {children}
    </div>
  );
}
