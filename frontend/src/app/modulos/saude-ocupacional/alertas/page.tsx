"use client";

import { useEffect, useState } from "react";
import {
  AlertTriangle,
  CheckCircle,
  Clock,
  FileText,
  RefreshCw,
  Shield,
  ShieldAlert,
  Stethoscope,
} from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8080";

interface StatCard {
  label: string;
  value: number | string;
  color: "red" | "yellow" | "green" | "blue";
  icon: React.ReactNode;
}

interface VencimentoASO {
  aso_id?: string;
  funcionario_id?: string;
  dias_para_vencer?: number;
  data_vencimento?: string;
  funcao?: string;
  setor?: string;
}

async function fetchApi(path: string, token?: string) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    cache: "no-store",
  });
  if (!res.ok) return null;
  return res.json();
}

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("access_token") || sessionStorage.getItem("access_token");
}

function Badge({ color, children }: { color: string; children: React.ReactNode }) {
  const colors: Record<string, string> = {
    red: "bg-red-100 text-red-800 border-red-200",
    yellow: "bg-yellow-100 text-yellow-800 border-yellow-200",
    green: "bg-green-100 text-green-800 border-green-200",
    blue: "bg-blue-100 text-blue-800 border-blue-200",
  };
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border ${colors[color] || colors.blue}`}>
      {children}
    </span>
  );
}

function StatCardComponent({ label, value, color, icon }: StatCard) {
  const borders: Record<string, string> = {
    red: "border-red-400 bg-red-50",
    yellow: "border-yellow-400 bg-yellow-50",
    green: "border-green-400 bg-green-50",
    blue: "border-blue-400 bg-blue-50",
  };
  const texts: Record<string, string> = {
    red: "text-red-700",
    yellow: "text-yellow-700",
    green: "text-green-700",
    blue: "text-blue-700",
  };

  return (
    <div className={`rounded-xl border-l-4 p-4 shadow-sm ${borders[color]}`}>
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-gray-500">{label}</p>
          <p className={`font-data text-3xl font-semibold tabular-nums mt-1 ${texts[color]}`}>{value}</p>
        </div>
        <div className={`${texts[color]} opacity-60`}>{icon}</div>
      </div>
    </div>
  );
}

export default function AlertasSSTPage() {
  const [loading, setLoading] = useState(true);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);

  // Stats
  const [pcmsoStats, setPcmsoStats] = useState<Record<string, unknown> | null>(null);
  const [epiStats, setEpiStats] = useState<Record<string, unknown> | null>(null);
  const [ppraStats, setPpraStats] = useState<Record<string, unknown> | null>(null);
  const [vencimentos, setVencimentos] = useState<VencimentoASO[]>([]);
  const [moduleStatus, setModuleStatus] = useState<Record<string, unknown> | null>(null);

  const loadData = async () => {
    setLoading(true);
    const token = getToken();

    const [pcmso, epi, ppra, venc, status] = await Promise.all([
      fetchApi("/api/v1/health-occupational/pcmso/estatisticas", token || undefined),
      fetchApi("/api/v1/health-occupational/epi/estatisticas", token || undefined),
      fetchApi("/api/v1/health-occupational/ppra/estatisticas", token || undefined),
      fetchApi("/api/v1/health-occupational/pcmso/vencimentos?dias=30", token || undefined),
      fetchApi("/api/v1/health-occupational/status", token || undefined),
    ]);

    setPcmsoStats(pcmso?.data || pcmso);
    setEpiStats(epi?.data || epi);
    setPpraStats(ppra?.data || ppra);

    // vencimentos pode ser array ou objeto com data
    if (Array.isArray(venc)) setVencimentos(venc);
    else if (venc?.data && Array.isArray(venc.data)) setVencimentos(venc.data);
    else setVencimentos([]);

    setModuleStatus(status?.data || status);
    setLastUpdate(new Date());
    setLoading(false);
  };

  useEffect(() => {
    loadData();
    // Atualiza a cada 5 minutos
    const interval = setInterval(loadData, 5 * 60 * 1000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Extrair valores dos stats
  const examesTotal = (pcmsoStats as Record<string, unknown>)?.total_exames as number ?? 0;
  const examesAgendados = (pcmsoStats as Record<string, unknown>)?.agendados as number ?? 0;
  const asosPendentes = (pcmsoStats as Record<string, unknown>)?.pendentes as number ?? 0;
  const epiTotal = (epiStats as Record<string, unknown>)?.total_epis as number ?? 0;
  const epiEstoqueBaixo = (epiStats as Record<string, unknown>)?.estoque_baixo as number ?? 0;
  const riscosMapeados = (ppraStats as Record<string, unknown>)?.total_mapeamentos as number ?? 0;
  const riscosCriticos = (ppraStats as Record<string, unknown>)?.riscos_intoleravel as number ??
    (ppraStats as Record<string, unknown>)?.nivel_intoleravel as number ?? 0;

  // Compliance do módulo
  const compliance = (moduleStatus as Record<string, unknown>)?.compliance as Record<string, boolean> ?? {};
  const complianceKeys = Object.keys(compliance);

  const statCards: StatCard[] = [
    {
      label: "Exames Agendados",
      value: examesAgendados,
      color: examesAgendados > 0 ? "yellow" : "green",
      icon: <Stethoscope size={36} />,
    },
    {
      label: "ASOs a Vencer (30d)",
      value: vencimentos.length,
      color: vencimentos.length === 0 ? "green" : vencimentos.length > 5 ? "red" : "yellow",
      icon: <FileText size={36} />,
    },
    {
      label: "EPIs Estoque Baixo",
      value: epiEstoqueBaixo,
      color: epiEstoqueBaixo === 0 ? "green" : epiEstoqueBaixo > 3 ? "red" : "yellow",
      icon: <ShieldAlert size={36} />,
    },
    {
      label: "Riscos Críticos",
      value: riscosCriticos,
      color: riscosCriticos === 0 ? "green" : "red",
      icon: <AlertTriangle size={36} />,
    },
  ];

  // suppress unused variable warning
  void asosPendentes;

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold text-[hsl(var(--foreground))] flex items-center gap-2">
            <Shield className="text-blue-600" size={28} />
            Painel de Alertas SST
          </h1>
          <p className="text-gray-500 text-sm mt-1">
            Monitoramento em tempo real — NR-6, NR-7, NR-9
          </p>
        </div>
        <div className="flex items-center gap-3">
          {lastUpdate && (
            <span className="text-xs text-gray-400">
              Atualizado: {lastUpdate.toLocaleTimeString("pt-BR")}
            </span>
          )}
          <button
            onClick={loadData}
            disabled={loading}
            className="flex items-center gap-1 px-3 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
          >
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
            Atualizar
          </button>
        </div>
      </div>

      {/* Stat Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {statCards.map((card) => (
          <StatCardComponent key={card.label} {...card} />
        ))}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* ASOs Vencendo */}
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm">
          <div className="p-4 border-b border-gray-100 flex items-center justify-between">
            <h2 className="font-semibold text-gray-800 flex items-center gap-2">
              <FileText size={18} className="text-orange-500" />
              ASOs Vencendo (30 dias)
            </h2>
            <Badge color={vencimentos.length > 0 ? "yellow" : "green"}>
              {vencimentos.length} registros
            </Badge>
          </div>
          <div className="p-4">
            {loading ? (
              <div className="text-center py-8 text-gray-400">Carregando...</div>
            ) : vencimentos.length === 0 ? (
              <div className="flex flex-col items-center py-8 text-gray-400">
                <CheckCircle size={32} className="text-green-400 mb-2" />
                <p>Nenhum ASO vencendo em 30 dias</p>
              </div>
            ) : (
              <div className="space-y-2 max-h-64 overflow-y-auto">
                {vencimentos.slice(0, 10).map((v, i) => (
                  <div key={i} className="flex items-center justify-between p-2 bg-orange-50 rounded-lg">
                    <div>
                      <p className="text-sm font-medium text-gray-700">
                        {v.funcao || "Função não informada"}
                      </p>
                      <p className="text-xs text-gray-500">{v.setor || "—"}</p>
                    </div>
                    <div className="text-right">
                      <Badge color={(v.dias_para_vencer ?? 999) <= 7 ? "red" : "yellow"}>
                        {v.dias_para_vencer ?? "?"} dias
                      </Badge>
                      <p className="text-xs text-gray-400 mt-0.5">{v.data_vencimento}</p>
                    </div>
                  </div>
                ))}
                {vencimentos.length > 10 && (
                  <p className="text-xs text-gray-400 text-center pt-2">
                    + {vencimentos.length - 10} registros adicionais
                  </p>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Compliance NRs */}
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm">
          <div className="p-4 border-b border-gray-100">
            <h2 className="font-semibold text-gray-800 flex items-center gap-2">
              <Shield size={18} className="text-blue-500" />
              Status de Conformidade (NRs)
            </h2>
          </div>
          <div className="p-4 space-y-3">
            {loading ? (
              <div className="text-center py-8 text-gray-400">Carregando...</div>
            ) : complianceKeys.length === 0 ? (
              <div className="flex flex-col items-center py-8 text-gray-400">
                <Clock size={32} className="mb-2" />
                <p>Dados de conformidade indisponíveis</p>
              </div>
            ) : (
              complianceKeys.map((key) => (
                <div key={key} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                  <span className="text-sm font-medium text-gray-700 uppercase">{key}</span>
                  {compliance[key] ? (
                    <Badge color="green">
                      <CheckCircle size={12} className="mr-1" /> Conforme
                    </Badge>
                  ) : (
                    <Badge color="red">
                      <AlertTriangle size={12} className="mr-1" /> Pendente
                    </Badge>
                  )}
                </div>
              ))
            )}

            {/* Stats resumo */}
            <div className="mt-4 pt-4 border-t border-gray-100 grid grid-cols-3 gap-2 text-center">
              <div>
                <p className="text-lg font-bold text-blue-600">{epiTotal}</p>
                <p className="text-xs text-gray-500">EPIs Cadastrados</p>
              </div>
              <div>
                <p className="text-lg font-bold text-blue-600">{examesTotal}</p>
                <p className="text-xs text-gray-500">Exames Totais</p>
              </div>
              <div>
                <p className="text-lg font-bold text-blue-600">{riscosMapeados}</p>
                <p className="text-xs text-gray-500">Riscos Mapeados</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Ações Rápidas */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-4">
        <h2 className="font-semibold text-gray-800 mb-4">Ações Rápidas</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[
            { label: "Agendar Exame", href: "/modulos/saude-ocupacional/exames", icon: <Stethoscope size={20} />, color: "blue" },
            { label: "Entregar EPI", href: "/modulos/saude-ocupacional/epi", icon: <Shield size={20} />, color: "green" },
            { label: "Mapear Risco", href: "/modulos/saude-ocupacional/riscos", icon: <AlertTriangle size={20} />, color: "orange" },
            { label: "Emitir ASO", href: "/modulos/saude-ocupacional/exames", icon: <FileText size={20} />, color: "purple" },
          ].map((action) => (
            <a
              key={action.label}
              href={action.href}
              className="flex flex-col items-center gap-2 p-4 rounded-lg border border-gray-200 hover:border-blue-300 hover:bg-blue-50 transition-colors text-center"
            >
              <span className="text-blue-600">{action.icon}</span>
              <span className="text-sm font-medium text-gray-700">{action.label}</span>
            </a>
          ))}
        </div>
      </div>
    </div>
  );
}
