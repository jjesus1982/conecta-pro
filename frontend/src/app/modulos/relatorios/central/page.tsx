'use client';

import { useState, useCallback, useEffect } from 'react';
import {
  FileText,
  Users,
  DollarSign,
  ShieldCheck,
  FolderOpen,
  Download,
  Loader2,
  Calendar,
  Building2,
  Star,
  Clock,
  BarChart3,
  AlertTriangle,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

function getAuthHeaders() {
  const token =
    typeof window !== 'undefined'
      ? localStorage.getItem('access_token') || localStorage.getItem('token')
      : null;
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

const MONTHS = [
  'Janeiro', 'Fevereiro', 'Marco', 'Abril', 'Maio', 'Junho',
  'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro',
];

interface ReportDef {
  id: string;
  title: string;
  description: string;
  icon: React.ElementType;
  category: string;
  favorite?: boolean;
}

const reportDefs: ReportDef[] = [
  { id: 'cert_status', title: 'Status de Certidoes', description: 'Todas as certidoes com status, validade e alertas de vencimento.', icon: ShieldCheck, category: 'compliance', favorite: true },
  { id: 'headcount', title: 'Headcount por Cliente', description: 'Quantidade de funcionarios alocados por cliente/posto.', icon: Users, category: 'rh', favorite: true },
  { id: 'ged_summary', title: 'Resumo GED', description: 'Documentos, kits ativos, assinaturas pendentes e stats.', icon: FolderOpen, category: 'ged', favorite: true },
  { id: 'integrations', title: 'Integracoes Governamentais', description: 'Status de todos os servicos gov (online/offline).', icon: Building2, category: 'compliance' },
  { id: 'kits', title: 'Kits Documentais', description: 'Lista de kits com status, tipo e atribuicoes.', icon: FileText, category: 'ged' },
  { id: 'financial', title: 'Resumo Financeiro', description: 'Visao geral de faturamento, clientes e kits por periodo.', icon: DollarSign, category: 'financeiro' },
];

interface HistoryEntry {
  id: string;
  report_title: string;
  period: string;
  generated_at: string;
}

export default function CentralRelatoriosPage() {
  const now = new Date();
  const [month, setMonth] = useState(String(now.getMonth() + 1));
  const [year, setYear] = useState(String(now.getFullYear()));
  const [generating, setGenerating] = useState('');
  const [history, setHistory] = useState<HistoryEntry[]>([]);

  useEffect(() => {
    const saved = localStorage.getItem('report_history');
    if (saved) try { setHistory(JSON.parse(saved)); } catch { /* */ }
  }, []);

  const saveHistory = (entry: HistoryEntry) => {
    const updated = [entry, ...history].slice(0, 20);
    setHistory(updated);
    localStorage.setItem('report_history', JSON.stringify(updated));
  };

  const generatePDF = useCallback(async (reportId: string) => {
    setGenerating(reportId);
    try {
      const { default: jsPDF } = await import('jspdf');
      await import('jspdf-autotable');
      const doc = new jsPDF();
      const periodLabel = `${MONTHS[parseInt(month) - 1]} ${year}`;

      // Header
      doc.setFillColor(10, 37, 64);
      doc.rect(0, 0, 210, 30, 'F');
      doc.setTextColor(255, 255, 255);
      doc.setFontSize(16);
      doc.text('Conecta PRO - Relatorio', 14, 15);
      doc.setFontSize(9);
      doc.text('GRUPO CONECTA MAIS (consolidado) | Eletronica 35.710.481/0001-03 | Patrimonial 66.014.833/0001-10', 14, 22);
      doc.text(`Gerado em: ${new Date().toLocaleString('pt-BR')} | Periodo: ${periodLabel}`, 14, 27);
      doc.setTextColor(0, 0, 0);

      let yPos = 40;

      if (reportId === 'cert_status') {
        doc.setFontSize(14);
        doc.text('Status de Certidoes Negativas', 14, yPos);
        yPos += 8;

        const res = await fetch('/api/v1/bidding/certificates', { headers: getAuthHeaders() });
        if (res.ok) {
          const data = await res.json();
          const items = Array.isArray(data) ? data : data.items ?? [];

          const tableData = items.map((c: Record<string, unknown>) => [
            String(c.nome ?? c.tipo ?? ''),
            String(c.situacao ?? ''),
            c.data_validade ? new Date(String(c.data_validade)).toLocaleDateString('pt-BR') : '-',
            `${c.dias_para_vencer ?? 0}d`,
            (c.esta_valida as boolean) ? 'Valida' : 'VENCIDA',
          ]);

          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          (doc as any).autoTable({
            startY: yPos,
            head: [['Certidao', 'Situação', 'Validade', 'Dias', 'Status']],
            body: tableData,
            styles: { fontSize: 8 },
            headStyles: { fillColor: [10, 37, 64] },
          });
        }
      } else if (reportId === 'headcount') {
        doc.setFontSize(14);
        doc.text('Headcount - Funcionarios Ativos', 14, yPos);
        yPos += 8;

        const res = await fetch('/api/v1/operacional/employees/?page=1&page_size=200', { headers: getAuthHeaders() });
        if (res.ok) {
          const data = await res.json();
          const items = Array.isArray(data) ? data : data.items ?? [];

          const tableData = items.map((e: Record<string, unknown>) => [
            String(e.full_name ?? e.name ?? e.nome ?? ''),
            String(e.cargo ?? e.position ?? e.role ?? '-'),
            String(e.departamento ?? e.department ?? '-'),
            String(e.status ?? 'ativo'),
          ]);

          doc.setFontSize(10);
          doc.text(`Total: ${items.length} funcionarios`, 14, yPos);
          yPos += 6;

          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          (doc as any).autoTable({
            startY: yPos,
            head: [['Nome', 'Cargo', 'Departamento', 'Status']],
            body: tableData,
            styles: { fontSize: 7 },
            headStyles: { fillColor: [10, 37, 64] },
          });
        }
      } else if (reportId === 'ged_summary') {
        doc.setFontSize(14);
        doc.text('Resumo GED - Gestao Eletronica de Documentos', 14, yPos);
        yPos += 10;

        const [gedRes, kitRes, sigRes] = await Promise.all([
          fetch('/api/v1/ged/documents/stats/summary', { headers: getAuthHeaders() }),
          fetch('/api/v1/document-kits/stats', { headers: getAuthHeaders() }),
          fetch('/api/v1/ged/document-signatures/stats/summary', { headers: getAuthHeaders() }),
        ]);

        const ged = gedRes.ok ? await gedRes.json() : {};
        const kit = kitRes.ok ? await kitRes.json() : {};
        const sig = sigRes.ok ? await sigRes.json() : {};

        const summaryData = [
          ['Total de Documentos', String(ged.total_documents ?? 0)],
          ['Pendentes Aprovacao', String(ged.pending_approval ?? 0)],
          ['Pendentes Assinatura', String(ged.pending_signature ?? 0)],
          ['Kits Ativos', String(kit.kits_ativos ?? 0)],
          ['Kits Total', String(kit.total_kits ?? 0)],
          ['Assinaturas Pendentes', String(sig.pending ?? 0)],
          ['Assinaturas Concluidas', String(sig.signed ?? 0)],
        ];

        // eslint-disable-next-line @typescript-eslint/no-explicit-any
          (doc as any).autoTable({
          startY: yPos,
          head: [['Metrica', 'Valor']],
          body: summaryData,
          styles: { fontSize: 9 },
          headStyles: { fillColor: [10, 37, 64] },
          columnStyles: { 0: { cellWidth: 100 }, 1: { cellWidth: 40, halign: 'right' as const } },
        });
      } else if (reportId === 'integrations') {
        doc.setFontSize(14);
        doc.text('Integracoes Governamentais', 14, yPos);
        yPos += 8;

        const res = await fetch('/api/v1/government/dashboard/status', { headers: getAuthHeaders() });
        if (res.ok) {
          const data = await res.json();
          const integrations = data.integrations ?? [];

          doc.setFontSize(10);
          doc.text(`Total: ${data.total ?? 0} | Online: ${data.online ?? 0} | Offline: ${data.offline ?? 0}`, 14, yPos);
          yPos += 6;

          const tableData = integrations.map((i: Record<string, unknown>) => [
            String(i.name ?? ''),
            String(i.status ?? ''),
            i.last_check ? new Date(String(i.last_check)).toLocaleString('pt-BR') : '-',
          ]);

          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          (doc as any).autoTable({
            startY: yPos,
            head: [['Servico', 'Status', 'Ultima Verificacao']],
            body: tableData,
            styles: { fontSize: 8 },
            headStyles: { fillColor: [10, 37, 64] },
          });
        }
      } else if (reportId === 'kits') {
        doc.setFontSize(14);
        doc.text('Kits Documentais', 14, yPos);
        yPos += 8;

        const res = await fetch('/api/v1/document-kits', { headers: getAuthHeaders() });
        if (res.ok) {
          const data = await res.json();
          const items = Array.isArray(data) ? data : data.items ?? [];

          const tableData = items.map((k: Record<string, unknown>) => [
            String(k.codigo ?? ''),
            String(k.nome ?? ''),
            String(k.tipo ?? ''),
            String(k.status ?? ''),
            String(k.total_itens ?? 0),
          ]);

          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          (doc as any).autoTable({
            startY: yPos,
            head: [['Codigo', 'Nome', 'Tipo', 'Status', 'Itens']],
            body: tableData,
            styles: { fontSize: 8 },
            headStyles: { fillColor: [10, 37, 64] },
          });
        }
      } else if (reportId === 'financial') {
        doc.setFontSize(14);
        doc.text('Resumo Financeiro', 14, yPos);
        yPos += 10;

        const [kitRes, certRes, gedRes] = await Promise.all([
          fetch('/api/v1/document-kits/stats', { headers: getAuthHeaders() }),
          fetch('/api/v1/bidding/certificates', { headers: getAuthHeaders() }),
          fetch('/api/v1/ged/documents/stats/summary', { headers: getAuthHeaders() }),
        ]);

        const kit = kitRes.ok ? await kitRes.json() : {};
        const certData = certRes.ok ? await certRes.json() : [];
        const certs = Array.isArray(certData) ? certData : certData.items ?? [];
        const ged = gedRes.ok ? await gedRes.json() : {};

        const overviewData = [
          ['Kits Ativos', String(kit.kits_ativos ?? 0)],
          ['Documentos GED', String(ged.total_documents ?? 0)],
          ['Certidoes Validas', String(certs.filter((c: Record<string, unknown>) => c.esta_valida).length)],
          ['Certidoes Vencidas', String(certs.filter((c: Record<string, unknown>) => !c.esta_valida).length)],
          ['Taxa Conclusao Kits', `${kit.taxa_conclusao ?? 0}%`],
        ];

        // eslint-disable-next-line @typescript-eslint/no-explicit-any
          (doc as any).autoTable({
          startY: yPos,
          head: [['Indicador', 'Valor']],
          body: overviewData,
          styles: { fontSize: 9 },
          headStyles: { fillColor: [10, 37, 64] },
        });
      }

      // Footer
      const pageCount = doc.getNumberOfPages();
      for (let i = 1; i <= pageCount; i++) {
        doc.setPage(i);
        doc.setFontSize(7);
        doc.setTextColor(150, 150, 150);
        doc.text(`Conecta PRO | Pagina ${i} de ${pageCount} | Gerado automaticamente`, 14, 287);
      }

      const reportDef = reportDefs.find(r => r.id === reportId);
      const fileName = `${reportId}_${year}_${month.padStart(2, '0')}.pdf`;
      doc.save(fileName);

      saveHistory({
        id: `${Date.now()}`,
        report_title: reportDef?.title ?? reportId,
        period: `${MONTHS[parseInt(month) - 1]} ${year}`,
        generated_at: new Date().toISOString(),
      });
    } catch (err) {
      console.error('Erro ao gerar PDF:', err);
    } finally {
      setGenerating('');
    }
  }, [month, year, history]);

  const favorites = reportDefs.filter(r => r.favorite);
  const categories: Record<string, ReportDef[]> = {};
  for (const r of reportDefs) {
    if (!categories[r.category]) categories[r.category] = [];
    categories[r.category]!.push(r);
  }

  const categoryLabels: Record<string, { label: string; icon: React.ElementType }> = {
    financeiro: { label: 'Financeiro', icon: DollarSign },
    rh: { label: 'RH e Headcount', icon: Users },
    ged: { label: 'GED e Kits', icon: FolderOpen },
    compliance: { label: 'Compliance', icon: ShieldCheck },
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold flex items-center gap-2">
            <BarChart3 className="h-6 w-6" />
            Central de Relatorios
          </h1>
          <p className="text-muted-foreground">
            Gere relatorios PDF com dados reais do sistema
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Select value={month} onValueChange={setMonth} aria-label="Month">
            <SelectTrigger className="w-[130px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {MONTHS.map((m, i) => (
                <SelectItem key={i} value={String(i + 1)}>{m}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={year} onValueChange={setYear} aria-label="Year">
            <SelectTrigger className="w-[90px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="2025">2025</SelectItem>
              <SelectItem value="2026">2026</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Favorites */}
      <div>
        <h2 className="text-sm font-semibold text-muted-foreground mb-3 flex items-center gap-1.5">
          <Star className="h-3.5 w-3.5" /> Favoritos
        </h2>
        <div className="grid gap-3 md:grid-cols-3">
          {favorites.map((report) => {
            const Icon = report.icon;
            return (
              <Card key={report.id} className="hover:shadow-md transition-shadow">
                <CardContent className="p-4">
                  <div className="flex items-start justify-between">
                    <div className="flex items-start gap-3">
                      <div className="p-2 rounded-lg bg-primary/10">
                        <Icon className="h-5 w-5 text-primary" />
                      </div>
                      <div>
                        <h3 className="font-medium text-sm">{report.title}</h3>
                        <p className="text-xs text-muted-foreground mt-0.5">{report.description}</p>
                      </div>
                    </div>
                  </div>
                  <Button
                    size="sm"
                    className="w-full mt-3"
                    onClick={() => generatePDF(report.id)}
                    disabled={generating === report.id}
                  >
                    {generating === report.id ? (
                      <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" />
                    ) : (
                      <Download className="h-3.5 w-3.5 mr-1" />
                    )}
                    Gerar PDF
                  </Button>
                </CardContent>
              </Card>
            );
          })}
        </div>
      </div>

      {/* Categories */}
      <Tabs defaultValue="compliance" className="space-y-4">
        <TabsList>
          {Object.entries(categoryLabels).map(([key, cfg]) => {
            const CatIcon = cfg.icon;
            return (
              <TabsTrigger key={key} value={key} className="flex items-center gap-1.5">
                <CatIcon className="h-3.5 w-3.5" />
                {cfg.label}
              </TabsTrigger>
            );
          })}
        </TabsList>

        {Object.entries(categories).map(([catKey, reports]) => (
          <TabsContent key={catKey} value={catKey}>
            <div className="grid gap-3 md:grid-cols-2">
              {reports.map((report) => {
                const Icon = report.icon;
                return (
                  <Card key={report.id}>
                    <CardContent className="p-4">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3 flex-1 min-w-0">
                          <Icon className="h-5 w-5 text-muted-foreground flex-shrink-0" />
                          <div className="min-w-0">
                            <h3 className="font-medium text-sm">{report.title}</h3>
                            <p className="text-xs text-muted-foreground truncate">{report.description}</p>
                          </div>
                        </div>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => generatePDF(report.id)}
                          disabled={generating === report.id}
                          className="ml-3 flex-shrink-0"
                        >
                          {generating === report.id ? (
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          ) : (
                            <Download className="h-3.5 w-3.5" />
                          )}
                        </Button>
                      </div>
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          </TabsContent>
        ))}
      </Tabs>

      {/* History */}
      {history.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-1.5">
              <Clock className="h-4 w-4" />
              Ultimos Relatorios Gerados
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b">
                  <th className="text-left p-3 font-medium text-muted-foreground">Relatorio</th>
                  <th className="text-left p-3 font-medium text-muted-foreground">Periodo</th>
                  <th className="text-left p-3 font-medium text-muted-foreground">Data</th>
                </tr>
              </thead>
              <tbody>
                {history.slice(0, 10).map((entry) => (
                  <tr key={entry.id} className="border-b last:border-0 hover:bg-muted/50">
                    <td className="p-3 font-medium">{entry.report_title}</td>
                    <td className="p-3 text-muted-foreground">{entry.period}</td>
                    <td className="p-3 text-muted-foreground">
                      {new Date(entry.generated_at).toLocaleString('pt-BR')}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
