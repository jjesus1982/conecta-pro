'use client';

import { useState } from 'react';
import {
  FileText,
  Users,
  Shield,
  PenTool,
  Download,
  Loader2,
  Calendar,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

const API_BASE = '/api/v1/ged';

function showToast(msg: string, type: 'success' | 'error' = 'success') {
  const el = document.createElement('div');
  el.className = `fixed top-4 right-4 z-[9999] px-4 py-3 rounded-lg shadow-lg text-sm font-medium text-white transition-opacity ${type === 'error' ? 'bg-red-500' : 'bg-emerald-500'}`;
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => { el.style.opacity = '0'; setTimeout(() => el.remove(), 300); }, 3000);
}

function getAuthHeaders() {
  let token: string | null = null;
  try {
    token = localStorage.getItem('access_token') || localStorage.getItem('token');
  } catch {
    token = null;
  }
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

interface ReportCard {
  id: string;
  title: string;
  description: string;
  icon: React.ElementType;
  color: string;
  bgColor: string;
  endpoint: string;
}

const reports: ReportCard[] = [
  {
    id: 'mensal',
    title: 'Relatório Mensal',
    description: 'Resumo completo dos kits documentais do período selecionado, incluindo status de envio e aprovação.',
    icon: FileText,
    color: 'text-blue-500',
    bgColor: 'bg-blue-500/10',
    endpoint: '/reports/monthly',
  },
  {
    id: 'cliente',
    title: 'Relatório por Cliente',
    description: 'Detalhamento por cliente com histórico de kits, documentos pendentes e taxa de conclusão.',
    icon: Users,
    color: 'text-emerald-500',
    bgColor: 'bg-emerald-500/10',
    endpoint: '/reports/by-client',
  },
  {
    id: 'compliance',
    title: 'Análise de Compliance',
    description: 'Verificação de conformidade documental, certidões vencidas e documentos obrigatórios faltantes.',
    icon: Shield,
    color: 'text-purple-500',
    bgColor: 'bg-purple-500/10',
    endpoint: '/reports/compliance',
  },
  {
    id: 'assinaturas',
    title: 'Histórico de Assinaturas',
    description: 'Rastreamento de todas as assinaturas digitais realizadas no período, com informações de certificado.',
    icon: PenTool,
    color: 'text-amber-500',
    bgColor: 'bg-amber-500/10',
    endpoint: '/reports/signatures',
  },
];

export default function RelatoriosPage() {
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [generatingId, setGeneratingId] = useState<string | null>(null);

  async function handleGenerate(report: ReportCard) {
    if (!startDate || !endDate) {
      showToast('Selecione o periodo (data inicio e data fim).', 'error');
      return;
    }

    setGeneratingId(report.id);
    try {
      const params = new URLSearchParams({
        start_date: startDate,
        end_date: endDate,
      });
      const res = await fetch(`${API_BASE}${report.endpoint}?${params.toString()}`, {
        headers: getAuthHeaders(),
      });
      if (res.ok) {
        const blob = await res.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        const ext = res.headers.get('content-type')?.includes('pdf') ? 'pdf' : 'xlsx';
        a.download = `${report.id}-${startDate}-${endDate}.${ext}`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);
      } else {
        showToast('Erro ao gerar relatório. Tente novamente.', 'error');
      }
    } catch (err) {
      console.error('handleGenerate:', err);
      showToast('Erro ao gerar relatório. Verifique sua conexão.', 'error');
    } finally {
      setGeneratingId(null);
    }
  }

  async function handleDownload(report: ReportCard) {
    if (!startDate || !endDate) {
      showToast('Selecione o periodo (data inicio e data fim).', 'error');
      return;
    }

    setGeneratingId(report.id);
    try {
      const params = new URLSearchParams({
        start_date: startDate,
        end_date: endDate,
        format: 'pdf',
      });
      const res = await fetch(`${API_BASE}${report.endpoint}/download?${params.toString()}`, {
        headers: getAuthHeaders(),
      });
      if (res.ok) {
        const blob = await res.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${report.id}-${startDate}-${endDate}.pdf`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);
      } else {
        showToast('Erro ao baixar relatório.', 'error');
      }
    } catch (err) {
      console.error('handleDownload:', err);
      showToast('Erro ao carregar relatório', 'error');
    } finally {
      setGeneratingId(null);
    }
  }

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-[hsl(var(--foreground))]">Relatórios GED</h1>
        <p className="text-[hsl(var(--muted-foreground))] mt-1">Gere e exporte relatórios do módulo de documentos</p>
      </div>

      <Card className="border border-[hsl(var(--border))]">
        <CardContent className="p-4">
          <div className="flex flex-wrap items-end gap-4">
            <Calendar className="h-5 w-5 text-[hsl(var(--muted-foreground))] mb-1" />
            <div>
              <label className="block text-xs text-[hsl(var(--muted-foreground))] mb-1">Data Início</label>
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="px-3 py-2 bg-[hsl(var(--card))] text-[hsl(var(--foreground))] border border-[hsl(var(--border))] rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
              />
            </div>
            <div>
              <label className="block text-xs text-[hsl(var(--muted-foreground))] mb-1">Data Fim</label>
              <input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className="px-3 py-2 bg-[hsl(var(--card))] text-[hsl(var(--foreground))] border border-[hsl(var(--border))] rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
              />
            </div>
            {(!startDate || !endDate) && (
              <p className="text-xs text-amber-500 mb-1">Selecione o período para gerar os relatórios</p>
            )}
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {reports.map((report) => {
          const Icon = report.icon;
          const isGenerating = generatingId === report.id;
          return (
            <Card key={report.id} className="border border-[hsl(var(--border))]">
              <CardHeader className="pb-2">
                <div className="flex items-start gap-3">
                  <div className={`p-3 rounded-lg ${report.bgColor}`}>
                    <Icon className={`h-6 w-6 ${report.color}`} />
                  </div>
                  <div className="flex-1">
                    <CardTitle className="text-base font-semibold">{report.title}</CardTitle>
                    <p className="text-sm text-[hsl(var(--muted-foreground))] mt-1">{report.description}</p>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="pt-0">
                <div className="flex gap-2 mt-2">
                  <button
                    onClick={() => handleGenerate(report)}
                    disabled={isGenerating || !startDate || !endDate}
                    className="flex items-center gap-2 px-3 py-2 text-sm font-medium bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  >
                    {isGenerating ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <FileText className="h-4 w-4" />
                    )}
                    Gerar
                  </button>
                  <button
                    onClick={() => handleDownload(report)}
                    disabled={isGenerating || !startDate || !endDate}
                    className="flex items-center gap-2 px-3 py-2 text-sm font-medium bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-lg hover:bg-[hsl(var(--secondary))] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  >
                    <Download className="h-4 w-4" />
                    Download PDF
                  </button>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
