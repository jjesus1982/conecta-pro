import type { Metadata, Viewport } from 'next';
import { Providers } from '@/contexts/providers';
import { Toaster } from '@/components/ui/toaster';
import { Toaster as SonnerToaster } from 'sonner';
import '@/styles/globals.css';
import { Space_Grotesk, IBM_Plex_Mono } from 'next/font/google';

// Tipografia com personalidade (tira a "cara de IA" do Inter-em-tudo):
const fontDisplay = Space_Grotesk({ subsets: ['latin'], weight: ['500', '600', '700'], variable: '--font-display', display: 'swap' });
const fontMono = IBM_Plex_Mono({ subsets: ['latin'], weight: ['400', '500', '600'], variable: '--font-data', display: 'swap' });

export const metadata: Metadata = {
  title: {
    default: 'Conecta PRO',
    template: '%s | Conecta PRO',
  },
  description: 'Sistema ERP para gestão de vigilância e segurança patrimonial',
  keywords: ['ERP', 'vigilância', 'segurança', 'gestão', 'Conecta PRO'],
  authors: [{ name: 'Grupo Conecta Mais' }],
  robots: 'noindex, nofollow',
  icons: {
    icon: '/favicon.ico',
  },
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  maximumScale: 1,
  themeColor: '#0a0c10',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="pt-BR" className={`dark ${fontDisplay.variable} ${fontMono.variable}`} suppressHydrationWarning>
      <head>
        <link rel="manifest" href="/manifest.json" />
        <meta name="apple-mobile-web-app-capable" content="yes" />
        <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent" />
        <meta name="apple-mobile-web-app-title" content="Conecta PRO" />
      </head>
      <body className="min-h-screen bg-[hsl(var(--background))] antialiased">
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:fixed focus:top-4 focus:left-4 focus:z-[9999] focus:px-4 focus:py-2 focus:rounded-lg focus:bg-[hsl(var(--primary))] focus:text-[hsl(var(--primary-foreground))] focus:text-sm focus:font-medium focus:outline-none focus:ring-2 focus:ring-offset-2"
        >
          Pular para o conteudo principal
        </a>
        <Providers>
          <main id="main-content">
            {children}
          </main>
          <Toaster />
          <SonnerToaster richColors position="top-right" />
        </Providers>
      </body>
    </html>
  );
}
