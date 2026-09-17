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
          // microphone=(self): ditado por voz no chat flutuante. Era `microphone=()`, que
          // proíbe até o PRÓPRIO site — o navegador bloqueava antes de pedir permissão, e
          // liberar no cadeado não adiantava. `(self)` mantém terceiros/iframes proibidos;
          // quem decide continua sendo o usuário, no prompt do navegador.
          { key: 'Permissions-Policy', value: 'geolocation=(self), microphone=(self), camera=(self)' },
          { key: 'X-DNS-Prefetch-Control', value: 'off' },
          { key: 'Strict-Transport-Security', value: 'max-age=63072000; includeSubDomains; preload' },
          { key: 'Cross-Origin-Opener-Policy', value: 'same-origin' },
          {
            key: 'Content-Security-Policy',
            value: [
              "default-src 'self'",
              // impeccable live mode roda em http://localhost:8400 — só em dev
              `script-src 'self' 'unsafe-eval' 'unsafe-inline'${process.env.NODE_ENV !== 'production' ? ' http://localhost:8400' : ''}`,
              "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
              "img-src 'self' data: blob: https://erp.conectamais.pro https://*.amazonaws.com",
              "font-src 'self' data: https://fonts.gstatic.com",
              `connect-src 'self' https://erp.conectamais.pro wss://erp.conectamais.pro https://*.amazonaws.com https://viacep.com.br https://brasilapi.com.br${process.env.NODE_ENV !== 'production' ? ' http://localhost:8400' : ''}`,
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
      // ══ A VERSÃO CLÁSSICA MORREU — 17/09/2026 ════════════════════════════════════
      //
      // O Jordan: «a versão clássica tem que morrer, não pode mais ter, tá confundindo» — e
      // depois, cobrando: «eu mandei matar ele, qual foi a parte que não entendeu?». Eram duas
      // telas para a mesma coisa (/modulos/crm e /redesign/crm, /modulos/financeiro e
      // /redesign/financeiro): é daí que vinha o «parece que tudo faz a mesma coisa».
      //
      // Redirect e não deleção porque link antigo não pode virar 404 — há links salvos, links
      // mandados por WhatsApp e o atalho do app. Quem abrir o endereço velho chega na tela
      // nova; a antiga deixa de existir para quem usa, que é o que o dono pediu.
      //
      // ROTA A ROTA, sem curinga, DE PROPÓSITO: o app do funcionário mora dentro do mesmo
      // /modulos e é a parte mais usada do sistema. Um "/modulos/operacional/:path*" engoliria
      // ronda-mobile (546 acessos de 13 aparelhos) e ocorrencia-rapida; um "/modulos/dp/:path*"
      // engoliria dp/ponto. Ficam de fora, vivas: meu-espaco (1.853 acessos, o campeão do
      // sistema), gestao-pessoas/ponto/batida (304 — onde os 52 batem ponto), /campo/*,
      // presenca, passagem-turno e instrucoes-posto. Matar isso derrubaria o ponto eletrônico
      // e a assinatura dos recibos na manhã seguinte.
      { source: '/modulos/area-cliente', destination: '/redesign/area-do-cliente', permanent: true },
      { source: '/modulos/area-cliente/gerenciamento', destination: '/redesign/area-do-cliente', permanent: true },
      { source: '/modulos/configuracoes', destination: '/redesign/configuracoes', permanent: true },
      { source: '/modulos/configuracoes/tenants', destination: '/redesign/configuracoes', permanent: true },
      { source: '/modulos/configuracoes/usuarios', destination: '/redesign/configuracoes', permanent: true },
      { source: '/modulos/crm', destination: '/redesign/crm', permanent: true },
      { source: '/modulos/crm/atividades', destination: '/redesign/crm', permanent: true },
      { source: '/modulos/crm/clientes', destination: '/redesign/crm', permanent: true },
      { source: '/modulos/crm/comissoes', destination: '/redesign/crm', permanent: true },
      { source: '/modulos/crm/consultor', destination: '/redesign/crm', permanent: true },
      { source: '/modulos/crm/contatos', destination: '/redesign/crm', permanent: true },
      { source: '/modulos/crm/contratos', destination: '/redesign/crm', permanent: true },
      { source: '/modulos/crm/growth', destination: '/redesign/crm', permanent: true },
      { source: '/modulos/crm/leads', destination: '/redesign/crm', permanent: true },
      { source: '/modulos/crm/oportunidades', destination: '/redesign/crm', permanent: true },
      { source: '/modulos/crm/precificacao', destination: '/redesign/crm', permanent: true },
      { source: '/modulos/crm/propostas', destination: '/redesign/crm', permanent: true },
      { source: '/modulos/dp', destination: '/redesign/departamento-pessoal', permanent: true },
      { source: '/modulos/dp/admissao', destination: '/redesign/departamento-pessoal', permanent: true },
      { source: '/modulos/dp/ativacao-ponto', destination: '/redesign/departamento-pessoal', permanent: true },
      { source: '/modulos/dp/beneficios', destination: '/redesign/departamento-pessoal', permanent: true },
      { source: '/modulos/dp/contratos', destination: '/redesign/departamento-pessoal', permanent: true },
      { source: '/modulos/dp/documentos', destination: '/redesign/departamento-pessoal', permanent: true },
      { source: '/modulos/dp/esocial', destination: '/redesign/departamento-pessoal', permanent: true },
      { source: '/modulos/dp/fechamento-ponto', destination: '/redesign/departamento-pessoal', permanent: true },
      { source: '/modulos/dp/ferias', destination: '/redesign/departamento-pessoal', permanent: true },
      { source: '/modulos/dp/folha', destination: '/redesign/departamento-pessoal', permanent: true },
      { source: '/modulos/dp/funcionarios', destination: '/redesign/departamento-pessoal', permanent: true },
      { source: '/modulos/dp/licencas', destination: '/redesign/departamento-pessoal', permanent: true },
      { source: '/modulos/dp/monitor-ponto', destination: '/redesign/departamento-pessoal', permanent: true },
      { source: '/modulos/dp/prestadores-pj', destination: '/redesign/departamento-pessoal', permanent: true },
      { source: '/modulos/dp/reembolsos', destination: '/redesign/departamento-pessoal', permanent: true },
      { source: '/modulos/dp/rescisao', destination: '/redesign/departamento-pessoal', permanent: true },
      { source: '/modulos/financeiro', destination: '/redesign/financeiro', permanent: true },
      { source: '/modulos/financeiro/banking', destination: '/redesign/financeiro', permanent: true },
      { source: '/modulos/financeiro/boletos', destination: '/redesign/financeiro', permanent: true },
      { source: '/modulos/financeiro/cobrancas', destination: '/redesign/financeiro', permanent: true },
      { source: '/modulos/financeiro/compras', destination: '/redesign/financeiro', permanent: true },
      { source: '/modulos/financeiro/conciliacao', destination: '/redesign/financeiro', permanent: true },
      { source: '/modulos/financeiro/contabilidade', destination: '/redesign/financeiro', permanent: true },
      { source: '/modulos/financeiro/contas-pagar', destination: '/redesign/financeiro', permanent: true },
      { source: '/modulos/financeiro/contas-receber', destination: '/redesign/financeiro', permanent: true },
      { source: '/modulos/financeiro/contratos', destination: '/redesign/financeiro', permanent: true },
      { source: '/modulos/financeiro/custeio', destination: '/redesign/financeiro', permanent: true },
      { source: '/modulos/financeiro/custos', destination: '/redesign/financeiro', permanent: true },
      { source: '/modulos/financeiro/dashboard', destination: '/redesign/financeiro', permanent: true },
      { source: '/modulos/financeiro/estoque', destination: '/redesign/financeiro', permanent: true },
      { source: '/modulos/financeiro/fluxo-caixa', destination: '/redesign/financeiro', permanent: true },
      { source: '/modulos/financeiro/fornecedores', destination: '/redesign/financeiro', permanent: true },
      { source: '/modulos/financeiro/inter', destination: '/redesign/financeiro', permanent: true },
      { source: '/modulos/financeiro/inter/pagamentos', destination: '/redesign/financeiro', permanent: true },
      { source: '/modulos/financeiro/nfse-entrada', destination: '/redesign/financeiro', permanent: true },
      { source: '/modulos/financeiro/pagamentos-diaristas', destination: '/redesign/financeiro', permanent: true },
      { source: '/modulos/financeiro/pagamentos-pj', destination: '/redesign/financeiro', permanent: true },
      { source: '/modulos/gestao-pessoas/[id]', destination: '/redesign/gestao-de-pessoas', permanent: true },
      { source: '/modulos/gestao-pessoas/consultor', destination: '/redesign/gestao-de-pessoas', permanent: true },
      { source: '/modulos/gestao-pessoas/ged', destination: '/redesign/gestao-de-pessoas', permanent: true },
      { source: '/modulos/gestao-pessoas/ged/certidoes', destination: '/redesign/gestao-de-pessoas', permanent: true },
      { source: '/modulos/gestao-pessoas/ged/configuracoes', destination: '/redesign/gestao-de-pessoas', permanent: true },
      { source: '/modulos/gestao-pessoas/ged/consultor', destination: '/redesign/gestao-de-pessoas', permanent: true },
      { source: '/modulos/gestao-pessoas/ged/documentos', destination: '/redesign/gestao-de-pessoas', permanent: true },
      { source: '/modulos/gestao-pessoas/ged/envios', destination: '/redesign/gestao-de-pessoas', permanent: true },
      { source: '/modulos/gestao-pessoas/ged/montar-kit', destination: '/redesign/gestao-de-pessoas', permanent: true },
      { source: '/modulos/integracoes/logs', destination: '/redesign/integracoes', permanent: true },
      { source: '/modulos/operacional', destination: '/redesign/operacional', permanent: true },
      { source: '/modulos/operacional/ai-command-center', destination: '/redesign/operacional', permanent: true },
      { source: '/modulos/operacional/alocacoes', destination: '/redesign/operacional', permanent: true },
      { source: '/modulos/operacional/avaliacao-equipe', destination: '/redesign/operacional', permanent: true },
      { source: '/modulos/operacional/banco-horas', destination: '/redesign/operacional', permanent: true },
      { source: '/modulos/operacional/cobertura', destination: '/redesign/operacional', permanent: true },
      { source: '/modulos/operacional/colaboradores', destination: '/redesign/operacional', permanent: true },
      { source: '/modulos/operacional/comunicados', destination: '/redesign/operacional', permanent: true },
      { source: '/modulos/operacional/consultor', destination: '/redesign/operacional', permanent: true },
      { source: '/modulos/operacional/diarias', destination: '/redesign/operacional', permanent: true },
      { source: '/modulos/operacional/diaristas', destination: '/redesign/operacional', permanent: true },
      { source: '/modulos/operacional/diaristas/escala', destination: '/redesign/operacional', permanent: true },
      { source: '/modulos/operacional/diaristas/fechamento', destination: '/redesign/operacional', permanent: true },
      { source: '/modulos/operacional/escalas', destination: '/redesign/operacional', permanent: true },
      { source: '/modulos/operacional/escalas/[id]', destination: '/redesign/operacional', permanent: true },
      { source: '/modulos/operacional/escalas/grade', destination: '/redesign/operacional', permanent: true },
      { source: '/modulos/operacional/kpi', destination: '/redesign/operacional', permanent: true },
      { source: '/modulos/operacional/medidas-administrativas', destination: '/redesign/operacional', permanent: true },
      { source: '/modulos/operacional/notificacoes', destination: '/redesign/operacional', permanent: true },
      { source: '/modulos/operacional/ocorrencias', destination: '/redesign/operacional', permanent: true },
      { source: '/modulos/operacional/postos', destination: '/redesign/operacional', permanent: true },
      { source: '/modulos/operacional/rondas', destination: '/redesign/operacional', permanent: true },
      { source: '/modulos/operacional/substituicoes', destination: '/redesign/operacional', permanent: true },
      { source: '/modulos/operacional/triagem', destination: '/redesign/operacional', permanent: true },
      { source: '/modulos/operacional/turnos', destination: '/redesign/operacional', permanent: true },
      { source: '/modulos/seguranca', destination: '/redesign/seguranca', permanent: true },
      { source: '/modulos/seguranca/auditoria', destination: '/redesign/seguranca', permanent: true },
      { source: '/modulos/seguranca/consentimento', destination: '/redesign/seguranca', permanent: true },
      { source: '/modulos/seguranca/criptografia', destination: '/redesign/seguranca', permanent: true },
      { source: '/modulos/seguranca/esquecimento', destination: '/redesign/seguranca', permanent: true },
      { source: '/modulos/seguranca/mascaramento', destination: '/redesign/seguranca', permanent: true },
      { source: '/modulos/seguranca/pia-dpia', destination: '/redesign/seguranca', permanent: true },

      // O dashboard clássico é o start_url do manifest.json — 1.811 acessos de 258 IPs: é
      // nele que o app instalado abre. Some da vista sem quebrar o atalho de ninguém.
      { source: '/dashboard', destination: '/redesign', permanent: false },

      // ── Portal do Funcionário ANTIGO (login por CPF), desligado em 2026 ──────────
      // Eram 14 páginas-casca com `location.replace` no client. As três de autenticação
      // mandavam para `/login?notice=portal` — SEM destino. Medido no nginx em 17/09/2026:
      // 69 IPs distintos entraram por aqui vindos do link de assinatura e caíram no painel
      // da empresa. Server-side (308) porque o client-side dependia do chunk carregar.
      {
        source: '/portal-funcionario/reset-senha',
        destination: '/forgot-password',
        permanent: true,
      },
      {
        source: '/portal-funcionario/primeiro-acesso',
        destination: '/forgot-password',
        permanent: true,
      },
      {
        source: '/portal-funcionario',
        destination: '/modulos/meu-espaco',
        permanent: true,
      },
      {
        source: '/portal-funcionario/:path*',
        destination: '/modulos/meu-espaco',
        permanent: true,
      },
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
