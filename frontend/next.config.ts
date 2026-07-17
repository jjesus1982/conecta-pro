import type { NextConfig } from 'next';
import withBundleAnalyzer from '@next/bundle-analyzer';

const bundleAnalyzer = withBundleAnalyzer({
  enabled: process.env.ANALYZE === 'true',
});

const nextConfig: NextConfig = {
  output: 'standalone',

  // TypeScript: ignorar erros para build de produção
  typescript: {
    ignoreBuildErrors: true,
  },

  // Configuração de ambiente
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || 'https://erp.conectamais.pro',
    NEXT_PUBLIC_APP_NAME: 'Conecta PRO',
    NEXT_PUBLIC_APP_VERSION: '2.0.0',
  },

  // Otimização de imports - FASE 4
  experimental: {
    // Otimizar imports de bibliotecas grandes
    optimizePackageImports: [
      'lucide-react',
      '@radix-ui/react-dialog',
      '@radix-ui/react-dropdown-menu',
      '@radix-ui/react-select',
      '@radix-ui/react-tooltip',
      '@radix-ui/react-popover',
      '@radix-ui/react-tabs',
      '@radix-ui/react-accordion',
      'date-fns',
      'recharts',
      'echarts',
      'echarts-for-react',
      'zod',
    ],

    // serverComponentsExternalPackages moved to top-level in Next.js 16

    // Partial Prerendering (Next.js 14+)
    ppr: false, // Habilitar quando estiver estável
  },

  // Server external packages (moved from experimental in Next.js 16)
  serverExternalPackages: ['xlsx'],

  // Turbopack (Next.js 16)
  turbopack: {
    resolveExtensions: ['.tsx', '.ts', '.jsx', '.js', '.json'],
  },

  // Otimização de imagens
  images: {
    formats: ['image/avif', 'image/webp'],
    deviceSizes: [640, 750, 828, 1080, 1200, 1920],
    imageSizes: [16, 32, 48, 64, 96, 128, 256, 384],
    minimumCacheTTL: 60,
    dangerouslyAllowSVG: true,
    contentDispositionType: 'attachment',
    remotePatterns: [
      {
        protocol: 'https',
        hostname: 'erp.conectamais.pro',
      },
      {
        protocol: 'https',
        hostname: '*.amazonaws.com',
      },
    ],
  },

  // Compressão
  compress: true,

  // Headers de segurança e performance
  async headers() {
    return [
      {
        // Headers de segurança para páginas (exclui assets estáticos)
        source: '/((?!_next/static|_next/image|favicon.ico).*)',
        headers: [
          { key: 'X-Frame-Options', value: 'DENY' },
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
          { key: 'Permissions-Policy', value: 'geolocation=(self), microphone=(), camera=(self)' },
          { key: 'X-DNS-Prefetch-Control', value: 'off' },
          { key: 'Strict-Transport-Security', value: 'max-age=63072000; includeSubDomains; preload' },
          { key: 'Cross-Origin-Opener-Policy', value: 'same-origin' },
          {
            key: 'Content-Security-Policy',
            value: [
              "default-src 'self'",
              "script-src 'self' 'unsafe-eval' 'unsafe-inline'",
              "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
              "img-src 'self' data: blob: https://erp.conectamais.pro https://*.amazonaws.com",
              "font-src 'self' data: https://fonts.gstatic.com",
              "connect-src 'self' https://erp.conectamais.pro wss://erp.conectamais.pro https://*.amazonaws.com https://viacep.com.br",
              "frame-ancestors 'none'",
              "base-uri 'self'",
              "form-action 'self'",
              "object-src 'none'",
            ].join('; '),
          },
        ],
      },
      {
        // Assets estáticos: cache longo, sem CSP/CORP restritivo
        source: '/_next/static/:path*',
        headers: [
          { key: 'Cache-Control', value: 'public, max-age=31536000, immutable' },
          { key: 'X-Content-Type-Options', value: 'nosniff' },
        ],
      },
      {
        // Páginas HTML: sem cache agressivo
        source: '/((?!_next/static|_next/image|favicon.ico|api/).*)',
        headers: [
          { key: 'Cache-Control', value: 'no-cache, no-store, must-revalidate' },
        ],
      },
      {
        // API routes sem cache
        source: '/api/:path*',
        headers: [
          { key: 'Cache-Control', value: 'no-store, max-age=0' },
        ],
      },
    ];
  },

  // Redirects para URLs legadas
  async redirects() {
    return [
      {
        source: '/modulos/dp/folha-salarial',
        destination: '/modulos/dp/folha',
        permanent: true,
      },
      {
        source: '/modulos/dp/folha-salarial/:path*',
        destination: '/modulos/dp/folha/:path*',
        permanent: true,
      },
      // Rotas legadas de Gestão de Pessoas
      {
        source: '/modulos/ged',
        destination: '/modulos/gestao-pessoas/ged',
        permanent: true,
      },
      {
        source: '/modulos/ged/:path*',
        destination: '/modulos/gestao-pessoas/ged/:path*',
        permanent: true,
      },
      {
        source: '/modulos/ponto',
        destination: '/modulos/gestao-pessoas/ponto',
        permanent: true,
      },
      {
        source: '/modulos/ponto/:path*',
        destination: '/modulos/gestao-pessoas/ponto/:path*',
        permanent: true,
      },
      // Rotas legadas de Saude Ocupacional
      {
        source: '/modulos/saude-ocupacional',
        destination: '/modulos/gestao-pessoas/saude-ocupacional',
        permanent: true,
      },
      {
        source: '/modulos/saude-ocupacional/:path*',
        destination: '/modulos/gestao-pessoas/saude-ocupacional/:path*',
        permanent: true,
      },
    ];
  },

  // Rewrites para API — proxy para FastAPI em qualquer ambiente (dev e produção)
  async rewrites() {
    const backendHost =
      process.env.BACKEND_URL || 'http://backend:8080';
    return [
      {
        source: '/api/v1/:path*',
        destination: `${backendHost}/api/v1/:path*`,
      },
    ];
  },

  // Webpack config (fallback quando Turbopack não está disponível)
  webpack: (config, { isServer, nextRuntime }) => {
    // Otimizações de bundle
    if (!isServer) {
      // Split chunks para bibliotecas grandes
      config.optimization = {
        ...config.optimization,
        splitChunks: {
          chunks: 'all',
          cacheGroups: {
            // Vendor separado
            vendor: {
              test: /[\\/]node_modules[\\/]/,
              name: 'vendors',
              chunks: 'all',
              priority: 10,
            },
            // Charts separados (carregado sob demanda)
            charts: {
              test: /[\\/](recharts|echarts|echarts-for-react)[\\/]/,
              name: 'charts',
              chunks: 'async',
              priority: 20,
            },
            // UI components
            ui: {
              test: /[\\/](@radix-ui|lucide-react)[\\/]/,
              name: 'ui',
              chunks: 'all',
              priority: 5,
            },
          },
        },
      };

      // Ignorar locales do moment se ainda estiver presente
      config.ignoreWarnings = [
        { module: /moment[\\/]locale/ },
      ];
    }

    return config;
  },

  // Logging
  logging: {
    fetches: {
      fullUrl: process.env.NODE_ENV === 'development',
    },
  },

  // Build ID baseado em timestamp — invalida caches RSC do browser a cada deploy
  generateBuildId: async () => `conecta-pro-${Date.now()}`,

  // DistDir customizado
  distDir: '.next',

  // Powered by header
  poweredByHeader: false,
};

export default bundleAnalyzer(nextConfig);
