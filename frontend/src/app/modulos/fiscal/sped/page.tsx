'use client';

import { RefreshCw, AlertCircle, Database, Eye, FileText, Download, CheckSquare, Loader2, Plus } from 'lucide-react';
import { useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { PageHeader } from '@/components/ui/page-header';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { SpedDetailModal } from '@/components/fiscal/sped-detail-modal';
import {
  useGerarArquivoSpedFiscal,
  useGerarArquivoSpedContabil,
  useValidarSped,
} from '@/hooks/government';
import { cn } from '@/lib/utils';

interface SpedFile {
  id: string;
  tipo: string;
  mes_referencia: string;
  ano_referencia: number;
  status: string;
  data_geracao: string;
  registros?: number;
}

const statusConfig: Record<string, { label: string; color: string }> = {
  gerado: { label: 'Gerado', color: 'bg-blue-100 text-blue-800' },
  validado: { label: 'Validado', color: 'bg-green-100 text-green-800' },
  pendente: { label: 'Pendente', color: 'bg-yellow-100 text-yellow-800' },
  erro: { label: 'Erro', color: 'bg-red-100 text-red-800' },
  enviado: { label: 'Enviado', color: 'bg-emerald-100 text-emerald-800' },
};

const meses = [
  { value: '01', label: 'Janeiro' },
  { value: '02', label: 'Fevereiro' },
  { value: '03', label: 'Marco' },
  { value: '04', label: 'Abril' },
  { value: '05', label: 'Maio' },
  { value: '06', label: 'Junho' },
  { value: '07', label: 'Julho' },
  { value: '08', label: 'Agosto' },
  { value: '09', label: 'Setembro' },
  { value: '10', label: 'Outubro' },
  { value: '11', label: 'Novembro' },
  { value: '12', label: 'Dezembro' },
];

const currentYear = new Date().getFullYear();
const anos = Array.from({ length: 5 }, (_, i) => currentYear - i);

export default function SpedPage() {
  const [activeTab, setActiveTab] = useState('fiscal');
  // init ESTÁVEL (igual no SSR e na hidratação — evita React #418); sincroniza no mount
  const [mesSelecionado, setMesSelecionado] = useState('01');
  const [anoSelecionado, setAnoSelecionado] = useState(currentYear);
  useEffect(() => {
    setMesSelecionado(String(new Date().getMonth() + 1).padStart(2, '0'));
    setAnoSelecionado(new Date().getFullYear());
  }, []);
  const [selectedSped, setSelectedSped] = useState<any | null>(null);
  const [showDetailModal, setShowDetailModal] = useState(false);

  // Local state for generated files
  const [fiscalFiles, setFiscalFiles] = useState<SpedFile[]>([]);
  const [contabilFiles, setContabilFiles] = useState<SpedFile[]>([]);
  const [reinfFiles, setReinfFiles] = useState<SpedFile[]>([]);

  const gerarFiscalMutation = useGerarArquivoSpedFiscal();
  const gerarContabilMutation = useGerarArquivoSpedContabil();
  const validarMutation = useValidarSped();

  const formatDate = (dateStr: string | null | undefined) => {
    if (!dateStr) return '-';
    return new Date(dateStr).toLocaleDateString('pt-BR', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const handleGerarFiscal = () => {
    gerarFiscalMutation.mutate(
      {
        mes_referencia: mesSelecionado,
        ano_referencia: anoSelecionado,
      },
      {
        onSuccess: (data: any) => {
          const newFile: SpedFile = {
            id: `fiscal-${Date.now()}`,
            tipo: 'fiscal',
            mes_referencia: mesSelecionado,
            ano_referencia: anoSelecionado,
            status: 'gerado',
            data_geracao: new Date().toISOString(),
            registros: data?.data?.total_registros ?? data?.registros,
          };
          setFiscalFiles((prev) => [newFile, ...prev]);
        },
      }
    );
  };

  const handleGerarContabil = () => {
    gerarContabilMutation.mutate(
      {
        mes_referencia: mesSelecionado,
        ano_referencia: anoSelecionado,
      },
      {
        onSuccess: (data: any) => {
          const newFile: SpedFile = {
            id: `contabil-${Date.now()}`,
            tipo: 'contabil',
            mes_referencia: mesSelecionado,
            ano_referencia: anoSelecionado,
            status: 'gerado',
            data_geracao: new Date().toISOString(),
            registros: data?.data?.total_registros ?? data?.registros,
          };
          setContabilFiles((prev) => [newFile, ...prev]);
        },
      }
    );
  };

  const handleValidar = (tipo: 'fiscal' | 'contabil' | 'reinf', fileId: string) => {
    validarMutation.mutate(
      {
        tipo,
        mes_referencia: mesSelecionado,
        ano_referencia: anoSelecionado,
      },
      {
        onSuccess: (data: any) => {
          const updateFn = (files: SpedFile[]) =>
            files.map((f) =>
              f.id === fileId
                ? { ...f, status: data?.success ? 'validado' : 'erro' }
                : f
            );

          if (tipo === 'fiscal') setFiscalFiles(updateFn);
          else if (tipo === 'contabil') setContabilFiles(updateFn);
          else setReinfFiles(updateFn);
        },
      }
    );
  };

  const getFilesList = (tipo: string) => {
    switch (tipo) {
      case 'fiscal':
        return fiscalFiles;
      case 'contabil':
        return contabilFiles;
      case 'reinf':
        return reinfFiles;
      default:
        return [];
    }
  };

  const renderPeriodSelector = () => (
    <div className="flex items-center gap-4 p-4 bg-[hsl(var(--muted))] rounded-lg">
      <div>
        <label className="block text-xs text-[hsl(var(--muted-foreground))] mb-1">Mes</label>
        <select
          value={mesSelecionado}
          onChange={(e) => setMesSelecionado(e.target.value)}
          className="px-3 py-2 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))] text-[hsl(var(--foreground))] text-sm"
        >
          {meses.map((m) => (
            <option key={m.value} value={m.value}>{m.label}</option>
          ))}
        </select>
      </div>
      <div>
        <label className="block text-xs text-[hsl(var(--muted-foreground))] mb-1">Ano</label>
        <select
          value={anoSelecionado}
          onChange={(e) => setAnoSelecionado(Number(e.target.value))}
          className="px-3 py-2 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))] text-[hsl(var(--foreground))] text-sm"
        >
          {anos.map((a) => (
            <option key={a} value={a}>{a}</option>
          ))}
        </select>
      </div>
    </div>
  );

  const renderFileTable = (files: SpedFile[], tipo: 'fiscal' | 'contabil' | 'reinf') => (
    <div className="mt-4">
      {files.length === 0 ? (
        <div className="text-center py-8">
          <Database className="w-10 h-10 text-[hsl(var(--muted-foreground))] mx-auto mb-3" />
          <p className="text-[hsl(var(--muted-foreground))]">
            Nenhum arquivo gerado para este periodo
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-[hsl(var(--border))]">
                <th className="text-left p-3 text-sm font-medium text-[hsl(var(--muted-foreground))]">
                  Periodo
                </th>
                <th className="text-left p-3 text-sm font-medium text-[hsl(var(--muted-foreground))]">
                  Data Geracao
                </th>
                <th className="text-left p-3 text-sm font-medium text-[hsl(var(--muted-foreground))]">
                  Status
                </th>
                <th className="w-32 p-3 text-sm font-medium text-[hsl(var(--muted-foreground))]">
                  Ações
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[hsl(var(--border))]">
              {files.map((file) => {
                const st = statusConfig[file.status] || statusConfig.pendente || { label: 'Pendente', color: 'bg-yellow-100 text-yellow-800' };
                return (
                  <tr
                    key={file.id}
                    className="hover:bg-[hsl(var(--secondary))]/50 transition-colors"
                  >
                    <td className="p-3">
                      <span className="text-sm text-[hsl(var(--foreground))]">
                        {file.mes_referencia}/{file.ano_referencia}
                      </span>
                    </td>
                    <td className="p-3">
                      <span className="text-sm text-[hsl(var(--muted-foreground))]">
                        {formatDate(file.data_geracao)}
                      </span>
                    </td>
                    <td className="p-3">
                      <span className={cn('inline-flex px-2 py-1 text-xs font-medium rounded-full', st.color)}>
                        {st.label}
                      </span>
                    </td>
                    <td className="p-3">
                      <div className="flex items-center gap-1">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => {
                            setSelectedSped({ ...file, tipo });
                            setShowDetailModal(true);
                          }}
                          title="Ver detalhes"
                        >
                          <Eye className="w-4 h-4" />
                        </Button>
                        {file.status === 'gerado' && (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleValidar(tipo, file.id)}
                            disabled={validarMutation.isPending}
                            title="Validar"
                          >
                            <CheckSquare className="w-4 h-4 text-green-500" />
                          </Button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <PageHeader
        eyebrow="FISCAL"
        title="SPED"
        subtitle="Sistema Publico de Escrituracao Digital"
        icon={<Database className="h-5 w-5" />}
      />

      {/* Period Selector */}
      {renderPeriodSelector()}

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="fiscal">Fiscal</TabsTrigger>
          <TabsTrigger value="contabil">Contabil</TabsTrigger>
          <TabsTrigger value="reinf">EFD-Reinf</TabsTrigger>
        </TabsList>

        <TabsContent value="fiscal">
          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="font-semibold text-[hsl(var(--foreground))]">SPED Fiscal</h3>
                  <p className="text-sm text-[hsl(var(--muted-foreground))]">
                    Escrituracao Fiscal Digital - ICMS/IPI
                  </p>
                </div>
                <Button
                  onClick={handleGerarFiscal}
                  disabled={gerarFiscalMutation.isPending}
                >
                  {gerarFiscalMutation.isPending ? (
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  ) : (
                    <Plus className="w-4 h-4 mr-2" />
                  )}
                  Gerar Arquivo
                </Button>
              </div>
              {renderFileTable(fiscalFiles, 'fiscal')}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="contabil">
          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="font-semibold text-[hsl(var(--foreground))]">SPED Contabil</h3>
                  <p className="text-sm text-[hsl(var(--muted-foreground))]">
                    Escrituracao Contabil Digital - ECD
                  </p>
                </div>
                <Button
                  onClick={handleGerarContabil}
                  disabled={gerarContabilMutation.isPending}
                >
                  {gerarContabilMutation.isPending ? (
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  ) : (
                    <Plus className="w-4 h-4 mr-2" />
                  )}
                  Gerar Arquivo
                </Button>
              </div>
              {renderFileTable(contabilFiles, 'contabil')}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="reinf">
          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="font-semibold text-[hsl(var(--foreground))]">EFD-Reinf</h3>
                  <p className="text-sm text-[hsl(var(--muted-foreground))]">
                    Escrituracao Fiscal Digital de Retencoes e Informações
                  </p>
                </div>
              </div>
              <div className="text-center py-8">
                <FileText className="w-10 h-10 text-[hsl(var(--muted-foreground))] mx-auto mb-3" />
                <p className="text-[hsl(var(--muted-foreground))]">
                  Use a pagina dedicada de EFD-Reinf para gerar eventos individuais
                </p>
                <Button
                  variant="outline"
                  className="mt-3"
                  onClick={() => window.location.href = '/modulos/fiscal/reinf'}
                >
                  Ir para EFD-Reinf
                </Button>
              </div>
              {renderFileTable(reinfFiles, 'reinf')}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Detail Modal */}
      <SpedDetailModal
        isOpen={showDetailModal}
        onClose={() => {
          setShowDetailModal(false);
          setSelectedSped(null);
        }}
        sped={selectedSped}
      />
    </div>
  );
}
