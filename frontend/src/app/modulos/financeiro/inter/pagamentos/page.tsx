"use client";

import { useState, useEffect, useCallback, type ReactNode } from "react";
import { msgFromDetail } from '@/lib/string';
import dynamic from "next/dynamic";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Wallet, TrendingDown, ShieldCheck, Lock, CheckCircle2, AlertTriangle, Camera, FileText } from "lucide-react";

// Scanner de câmera (QR PIX + código de barras boleto) — client-only (usa a câmera)
const ScannerPagamento = dynamic(() => import("@/components/financeiro/ScannerPagamento"), { ssr: false });

// ── tipos ─────────────────────────────────────────────────────────────────────

type PaymentType = "boleto" | "pix" | "darf" | "gps" | "ted_interno";
type PaymentStatus = "preparado" | "aprovado" | "executado" | "confirmado" | "cancelado" | "erro";

interface Payment {
  id: string;
  payment_type: PaymentType;
  valor: number;
  data_pagamento: string;
  status: PaymentStatus;
  inter_payment_id?: string;
  approved_at?: string;
  executed_at?: string;
  observacoes?: string;
  created_at: string;
}

interface SaldoLimite {
  saldo_inter: number;
  limite_diario: number;
  consumido_hoje: number;
  disponivel_hoje: number;
  limite_restante: number;
}

// ── helpers ───────────────────────────────────────────────────────────────────

const API = "/api/v1/financeiro/inter/payments";

async function apiFetch(path: string, options?: RequestInit) {
  const token = localStorage.getItem("access_token") || "";
  const res = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      ...(options?.headers || {}),
    },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(msgFromDetail(err.detail) || res.statusText);
  }
  return res.json();
}

const STATUS_COLOR: Record<PaymentStatus, string> = {
  preparado: "bg-yellow-100 text-yellow-800",
  aprovado: "bg-blue-100 text-blue-800",
  executado: "bg-purple-100 text-purple-800",
  confirmado: "bg-green-100 text-green-800",
  cancelado: "bg-gray-100 text-gray-600",
  erro: "bg-red-100 text-red-800",
};

const TYPE_LABEL: Record<PaymentType, string> = {
  boleto: "Boleto",
  pix: "PIX",
  darf: "DARF",
  gps: "GPS",
  ted_interno: "TED",
};

function StatusBadge({ status }: { status: PaymentStatus }) {
  return (
    <span className={`px-2 py-1 rounded-full text-xs font-medium ${STATUS_COLOR[status] || "bg-gray-100 text-gray-600"}`}>
      {status.toUpperCase()}
    </span>
  );
}

function fmt(v: number) {
  return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(v);
}

// ── componente: formulário novo pagamento ─────────────────────────────────────

function NovoPagamentoForm({ onPrepared, saldo }: { onPrepared: () => void; saldo: SaldoLimite | null }) {
  const [type, setType] = useState<PaymentType>("pix");
  const [valor, setValor] = useState("");
  const [dataPgto, setDataPgto] = useState(() => new Date().toISOString().slice(0, 10));
  const [obs, setObs] = useState("");
  const [dest, setDest] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [confirmando, setConfirmando] = useState(false);

  const handleDestChange = (key: string, val: string) =>
    setDest((prev) => ({ ...prev, [key]: val }));

  // Agenda de beneficiários (como o app do Inter): digita o nome → carrega a chave PIX.
  const [benefQ, setBenefQ] = useState("");
  const [benefList, setBenefList] = useState<Array<Record<string, string>>>([]);
  const [benefOpen, setBenefOpen] = useState(false);
  const buscarBenef = async (q: string) => {
    setBenefQ(q); setBenefOpen(true);
    if (q.trim().length < 2) { setBenefList([]); return; }
    try {
      const r = await apiFetch(`/api/v1/financial/beneficiarios?q=${encodeURIComponent(q)}`) as { beneficiarios?: Array<Record<string, string>> };
      setBenefList(r?.beneficiarios || []);
    } catch { setBenefList([]); }
  };
  const escolherBenef = (b: Record<string, string>) => {
    setDest((prev) => ({ ...prev, chave: b.chave_pix || "", tipo_chave: b.tipo_chave || prev.tipo_chave || "CPF", nome_recebedor: b.nome || "" }));
    setBenefQ(b.nome || ""); setBenefOpen(false); setBenefList([]);
  };

  // Copia-e-cola / QR Code (PIX) e código de barras (boleto)
  const [scannerOpen, setScannerOpen] = useState(false);
  const [colaCola, setColaCola] = useState("");
  const [msgCodigo, setMsgCodigo] = useState("");
  const processarCodigo = async (texto: string, formato?: "qr" | "barcode") => {
    const t = (texto || "").trim();
    if (!t) return;
    setMsgCodigo("");
    const soDigitos = t.replace(/\D/g, "");
    const ehPix = /br\.gov\.bcb\.pix/i.test(t) || t.toUpperCase().startsWith("000201");
    // Boleto: código de barras / linha digitável — só comprimentos válidos (44 barra, 47/48 linha)
    if (!ehPix && (formato === "barcode" || soDigitos.length >= 40)) {
      if (![44, 47, 48].includes(soDigitos.length)) {
        setMsgCodigo(`Código de barras incompleto (${soDigitos.length} dígitos). Escaneie de novo, bem enquadrado.`);
        return;
      }
      setType("boleto");
      setDest({ codigo_barras: soDigitos });
      // Auto-preenche o valor nominal (igual o app do Inter): barcode(44) pos 9-19; linha(47) pos 37-47.
      let cents = "";
      if (soDigitos.length === 44 && !soDigitos.startsWith("8")) cents = soDigitos.slice(9, 19);
      else if (soDigitos.length === 47) cents = soDigitos.slice(37, 47);
      const nominal = cents ? parseInt(cents, 10) / 100 : 0;
      if (nominal > 0) setValor(String(nominal.toFixed(2)));
      setMsgCodigo(`Boleto lido${nominal > 0 ? ` — valor R$ ${nominal.toFixed(2)}` : ""}. Confira e pague.`);
      return;
    }
    // PIX copia-e-cola / QR
    try {
      const r = await apiFetch(`${API}/decodificar-pix`, { method: "POST", body: JSON.stringify({ brcode: t }) }) as Record<string, string | number | boolean | null>;
      if (!r.valido) { setMsgCodigo(String(r.motivo || "Código PIX inválido.")); return; }
      if (r.dinamico) { setMsgCodigo(String(r.motivo || "QR dinâmico — pague pelo app do Inter.")); return; }
      setType("pix");
      setDest((prev) => ({ ...prev, chave: String(r.chave || ""), tipo_chave: String(r.tipo_chave || "EVP"), nome_recebedor: String(r.nome || prev.nome_recebedor || "") }));
      if (r.valor) setValor(String(r.valor));
      if (r.nome) setBenefQ(String(r.nome));
      setMsgCodigo(`PIX lido: ${r.nome || r.chave}${r.valor ? ` — R$ ${r.valor}` : ""}. Confira e confirme.`);
    } catch { setMsgCodigo("Falha ao decodificar o código."); }
  };
  const anexarBoletoPdf = async (file: File | undefined) => {
    if (!file) return;
    setMsgCodigo("Lendo o PDF do boleto…");
    const fd = new FormData();
    fd.append("arquivo", file);
    try {
      const token = localStorage.getItem("access_token") || "";
      const res = await fetch(`${API}/extrair-boleto-pdf`, { method: "POST", headers: { Authorization: `Bearer ${token}` }, body: fd });
      const r = await res.json();
      if (!res.ok || !r.encontrado) { setMsgCodigo(r?.motivo || msgFromDetail(r?.detail) || "Não consegui ler a linha digitável do PDF."); return; }
      setType("boleto");
      setDest({ codigo_barras: String(r.linha_digitavel) });
      if (r.valor) setValor(Number(r.valor).toFixed(2));
      setMsgCodigo(`Boleto lido do PDF${r.valor ? ` — R$ ${Number(r.valor).toFixed(2)}` : ""}. Confira e pague.`);
    } catch { setMsgCodigo("Falha ao ler o PDF do boleto."); }
  };

  const handleConfirmar = async () => {
    setLoading(true);
    setError("");
    try {
      await apiFetch(API, {
        method: "POST",
        body: JSON.stringify({
          payment_type: type,
          destinatario: dest,
          valor: parseFloat(valor),
          data_pagamento: dataPgto,
          observacoes: obs,
        }),
      });
      setConfirmando(false);
      setValor("");
      setDest({});
      onPrepared();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Erro ao preparar pagamento");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-100">
      <h3 className="text-lg font-semibold text-[#0A2540] mb-4">Novo Pagamento</h3>

      {/* Copia-e-cola / QR (PIX) e código de barras (boleto) */}
      <div className="mb-4 rounded-lg border border-dashed border-gray-300 bg-gray-50 p-3">
        <label className="block text-sm font-medium text-gray-700 mb-1">PIX copia-e-cola, QR Code ou código de barras</label>
        <div className="flex gap-2">
          <input
            className="flex-1 border rounded-lg px-3 py-2 text-sm"
            value={colaCola}
            onChange={(e) => setColaCola(e.target.value)}
            onBlur={() => colaCola.trim() && processarCodigo(colaCola)}
            placeholder="Cole o PIX copia-e-cola ou a linha digitável do boleto"
          />
          <button
            type="button"
            onClick={() => processarCodigo(colaCola)}
            className="text-sm border border-gray-300 text-gray-700 px-3 py-2 rounded-lg hover:bg-gray-100 whitespace-nowrap"
          >
            Ler
          </button>
          <button
            type="button"
            onClick={() => setScannerOpen(true)}
            className="text-sm bg-[#0A2540] text-white px-3 py-2 rounded-lg hover:bg-[#0d2f52] flex items-center gap-1 whitespace-nowrap"
          >
            <Camera className="h-4 w-4" /> Escanear
          </button>
          <label className="text-sm border border-[#0A2540] text-[#0A2540] px-3 py-2 rounded-lg hover:bg-gray-100 flex items-center gap-1 whitespace-nowrap cursor-pointer">
            <FileText className="h-4 w-4" /> Boleto PDF
            <input
              type="file"
              accept="application/pdf,.pdf"
              className="hidden"
              onChange={(e) => { anexarBoletoPdf(e.target.files?.[0]); e.target.value = ""; }}
            />
          </label>
        </div>
        <p className="text-[11px] text-gray-400 mt-1">Boleto: melhor anexar o PDF (mais confiável que a câmera). PIX: escanear o QR ou colar o copia-e-cola.</p>
        {msgCodigo && <p className="text-xs mt-2 text-[#0A2540]">{msgCodigo}</p>}
      </div>

      {scannerOpen && (
        <ScannerPagamento
          onClose={() => setScannerOpen(false)}
          onDetect={(texto, formato) => { setScannerOpen(false); setColaCola(texto); processarCodigo(texto, formato); }}
        />
      )}

      <div className="grid grid-cols-2 gap-4 mb-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Tipo</label>
          <select
            className="w-full border rounded-lg px-3 py-2 text-sm"
            value={type}
            onChange={(e) => { setType(e.target.value as PaymentType); setDest({}); }}
          >
            {Object.entries(TYPE_LABEL).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Valor (R$)</label>
          <input
            type="number"
            step="0.01"
            min="0.01"
            className="w-full border rounded-lg px-3 py-2 text-sm"
            value={valor}
            onChange={(e) => setValor(e.target.value)}
            placeholder="0,00"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Data Pagamento</label>
          <input
            type="date"
            className="w-full border rounded-lg px-3 py-2 text-sm"
            value={dataPgto}
            onChange={(e) => setDataPgto(e.target.value)}
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Observações</label>
          <input
            className="w-full border rounded-lg px-3 py-2 text-sm"
            value={obs}
            onChange={(e) => setObs(e.target.value)}
            placeholder="Opcional"
          />
        </div>
      </div>

      {/* Campos dinâmicos por tipo */}
      <div className="grid grid-cols-2 gap-4 mb-4">
        {type === "boleto" && (
          <div className="col-span-2">
            <label className="block text-sm font-medium text-gray-700 mb-1">Código de Barras</label>
            <input
              className="w-full border rounded-lg px-3 py-2 text-sm font-mono"
              value={dest.codigo_barras || ""}
              onChange={(e) => handleDestChange("codigo_barras", e.target.value)}
              placeholder="Digite o código de barras"
            />
          </div>
        )}
        {type === "pix" && (
          <>
            <div className="col-span-2 relative">
              <label className="block text-sm font-medium text-gray-700 mb-1">Buscar beneficiário salvo</label>
              <input
                className="w-full border rounded-lg px-3 py-2 text-sm"
                value={benefQ}
                onChange={(e) => buscarBenef(e.target.value)}
                onFocus={() => benefQ.trim().length >= 2 && setBenefOpen(true)}
                onBlur={() => setTimeout(() => setBenefOpen(false), 150)}
                placeholder="Digite o nome (ex.: Saúde Manaus) e selecione — a chave carrega sozinha"
              />
              {benefOpen && benefList.length > 0 && (
                <div className="absolute z-20 mt-1 w-full bg-white border border-gray-200 rounded-lg shadow-lg max-h-56 overflow-auto">
                  {benefList.map((b) => (
                    <button
                      type="button"
                      key={b.id}
                      onMouseDown={(e) => { e.preventDefault(); escolherBenef(b); }}
                      className="w-full text-left px-3 py-2 text-sm hover:bg-gray-50 flex items-center justify-between gap-2"
                    >
                      <span>
                        <span className="font-medium">{b.nome}</span>
                        <span className="text-xs text-gray-400 ml-2">{b.tipo_chave || "PIX"}: {b.chave_pix}</span>
                      </span>
                      {b.categoria && b.categoria !== "avulso" && (
                        <span className="text-[10px] uppercase tracking-wide text-gray-400">{b.categoria}</span>
                      )}
                    </button>
                  ))}
                </div>
              )}
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Tipo Chave</label>
              <select
                className="w-full border rounded-lg px-3 py-2 text-sm"
                value={dest.tipo_chave || "CPF"}
                onChange={(e) => handleDestChange("tipo_chave", e.target.value)}
              >
                {["CPF", "CNPJ", "EMAIL", "TELEFONE", "EVP"].map((t) => (
                  <option key={t}>{t}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Chave PIX</label>
              <input
                className="w-full border rounded-lg px-3 py-2 text-sm"
                value={dest.chave || ""}
                onChange={(e) => handleDestChange("chave", e.target.value)}
                placeholder="Chave PIX do destinatário"
              />
            </div>
            <div className="col-span-2">
              <label className="block text-sm font-medium text-gray-700 mb-1">Nome do Recebedor</label>
              <input
                className="w-full border rounded-lg px-3 py-2 text-sm"
                value={dest.nome_recebedor || ""}
                onChange={(e) => handleDestChange("nome_recebedor", e.target.value)}
                placeholder="Nome (opcional)"
              />
            </div>
          </>
        )}
        {type === "darf" && (
          <>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Código Receita</label>
              <input
                className="w-full border rounded-lg px-3 py-2 text-sm"
                value={dest.codigo_receita || ""}
                onChange={(e) => handleDestChange("codigo_receita", e.target.value)}
                placeholder="Ex: 0220"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Período Apuração</label>
              <input
                type="month"
                className="w-full border rounded-lg px-3 py-2 text-sm"
                value={dest.periodo_apuracao || ""}
                onChange={(e) => handleDestChange("periodo_apuracao", e.target.value)}
              />
            </div>
          </>
        )}
        {type === "gps" && (
          <>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Código Pagamento</label>
              <input
                className="w-full border rounded-lg px-3 py-2 text-sm"
                value={dest.codigo_pagamento || ""}
                onChange={(e) => handleDestChange("codigo_pagamento", e.target.value)}
                placeholder="Ex: 1910"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Competência</label>
              <input
                type="month"
                className="w-full border rounded-lg px-3 py-2 text-sm"
                value={dest.competencia || ""}
                onChange={(e) => handleDestChange("competencia", e.target.value)}
              />
            </div>
          </>
        )}
        {type === "ted_interno" && (
          <>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Banco</label>
              <input className="w-full border rounded-lg px-3 py-2 text-sm" value={dest.banco || ""} onChange={(e) => handleDestChange("banco", e.target.value)} placeholder="Ex: 077" />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Agência</label>
              <input className="w-full border rounded-lg px-3 py-2 text-sm" value={dest.agencia || ""} onChange={(e) => handleDestChange("agencia", e.target.value)} placeholder="0001" />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Conta</label>
              <input className="w-full border rounded-lg px-3 py-2 text-sm" value={dest.conta || ""} onChange={(e) => handleDestChange("conta", e.target.value)} placeholder="370990072" />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Nome</label>
              <input className="w-full border rounded-lg px-3 py-2 text-sm" value={dest.nome || ""} onChange={(e) => handleDestChange("nome", e.target.value)} placeholder="Nome do titular" />
            </div>
          </>
        )}
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-3 mb-4 text-red-700 text-sm">
          <AlertTriangle className="w-4 h-4 inline" /> {error}
        </div>
      )}

      {/* Alertas de limite/saldo */}
      {saldo && valor && parseFloat(valor) > 0 && (
        <>
          {parseFloat(valor) > saldo.disponivel_hoje && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-3 mb-3 text-red-700 text-sm">
              ⛔ Valor excede o limite diário disponível ({fmt(saldo.disponivel_hoje)})
            </div>
          )}
          {parseFloat(valor) > 0 && saldo.disponivel_hoje <= 0 && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-3 mb-3 text-red-700 text-sm">
              ⛔ Limite diário esgotado (R$ 5.000 atingido)
            </div>
          )}
        </>
      )}

      {confirmando ? (
        <div className="bg-amber-50 border border-amber-300 rounded-xl p-4 mb-4">
          <p className="font-semibold text-amber-800 mb-2 flex items-center gap-1"><AlertTriangle className="w-4 h-4" /> Confirme o pagamento</p>
          <p className="text-sm text-amber-700">
            Tipo: <strong>{TYPE_LABEL[type]}</strong> | Valor: <strong>{fmt(parseFloat(valor || "0"))}</strong>
            {type === "pix" && dest.chave && <> | Chave: <strong>{dest.chave}</strong></>}
            {type === "boleto" && dest.codigo_barras && <> | Código: <strong>{dest.codigo_barras.slice(0, 10)}...</strong></>}
          </p>
          <p className="text-xs text-amber-600 mt-2">
            Este é apenas a PREPARAÇÃO. Você precisará aprovar com OTP de email antes da execução.
          </p>
          <div className="flex gap-2 mt-3">
            <button
              onClick={handleConfirmar}
              disabled={loading}
              className="bg-[#FF6B35] hover:bg-orange-600 text-white px-4 py-2 rounded-lg text-sm font-medium"
            >
              {loading ? "Preparando..." : "Confirmar Preparação"}
            </button>
            <button
              onClick={() => setConfirmando(false)}
              className="bg-gray-100 text-gray-700 px-4 py-2 rounded-lg text-sm font-medium"
            >
              Cancelar
            </button>
          </div>
        </div>
      ) : (
        <button
          onClick={() => {
            if (saldo && parseFloat(valor) > saldo.disponivel_hoje) {
              setError(`Valor excede o limite diário disponível (${fmt(saldo.disponivel_hoje)})`);
              return;
            }
            setError("");
            setConfirmando(true);
          }}
          disabled={!valor || parseFloat(valor) <= 0}
          className="bg-[#0A2540] hover:bg-[#1a3a5c] text-white px-6 py-2 rounded-lg text-sm font-medium disabled:opacity-40"
        >
          Preparar Pagamento
        </button>
      )}
    </div>
  );
}

// ── componente: aprovação (OTP) ───────────────────────────────────────────────

function AprovacaoPagamento({ payment, onAction }: { payment: Payment; onAction: () => void }) {
  const [otpSent, setOtpSent] = useState(false);
  const [otpCode, setOtpCode] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleGerarOTP = async () => {
    setLoading(true);
    setError("");
    try {
      await apiFetch(`${API}/${payment.id}/gerar-otp`, { method: "POST" });
      setOtpSent(true);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Erro ao gerar OTP");
    } finally {
      setLoading(false);
    }
  };

  const handleAprovarExecutar = async () => {
    if (!otpCode || otpCode.length !== 6) { setError("Digite o código de 6 dígitos"); return; }
    setLoading(true);
    setError("");
    try {
      await apiFetch(`${API}/${payment.id}/aprovar`, {
        method: "POST",
        body: JSON.stringify({ otp_code: otpCode }),
      });
      await apiFetch(`${API}/${payment.id}/executar`, { method: "POST" });
      onAction();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Erro na aprovação/execução");
    } finally {
      setLoading(false);
    }
  };

  const handleCancelar = async () => {
    setLoading(true);
    try {
      await apiFetch(`${API}/${payment.id}/cancelar`, {
        method: "POST",
        body: JSON.stringify({ motivo: "Cancelado pelo usuário" }),
      });
      onAction();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Erro ao cancelar");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-amber-50 border-2 border-amber-400 rounded-xl p-6">
      <div className="flex items-center gap-2 mb-4">
        <span className="text-2xl">🔐</span>
        <h3 className="text-lg font-bold text-amber-900">Aprovação de Pagamento</h3>
      </div>
      <div className="bg-white rounded-lg p-4 mb-4 border border-amber-200">
        <div className="grid grid-cols-3 gap-4 text-sm">
          <div><span className="text-gray-500">Tipo:</span><br /><strong>{TYPE_LABEL[payment.payment_type]}</strong></div>
          <div><span className="text-gray-500">Valor:</span><br /><strong className="text-2xl text-red-600">{fmt(payment.valor)}</strong></div>
          <div><span className="text-gray-500">Data:</span><br /><strong>{payment.data_pagamento}</strong></div>
        </div>
      </div>
      <div className="bg-red-50 border border-red-200 rounded-lg p-3 mb-4 text-sm text-red-700">
        <AlertTriangle className="w-4 h-4 inline" /> <strong>ATENÇÃO:</strong> Este pagamento será EXECUTADO imediatamente após aprovação.
        Verifique 2x os dados acima. Operação <strong>irreversível</strong>.
      </div>

      {!otpSent ? (
        <button
          onClick={handleGerarOTP}
          disabled={loading}
          className="bg-[#0A2540] text-white px-4 py-2 rounded-lg text-sm font-medium mr-2"
        >
          {loading ? "Enviando..." : "📧 Enviar código OTP por email"}
        </button>
      ) : (
        <div className="space-y-3">
          <p className="text-sm text-green-700 flex items-center gap-1"><CheckCircle2 className="w-4 h-4" /> Código enviado para jjesus@conectamais.pro. Digite o código:</p>
          <input
            type="text"
            maxLength={6}
            className="border-2 border-[#0A2540] rounded-lg px-4 py-3 text-2xl text-center font-mono tracking-widest w-40"
            value={otpCode}
            onChange={(e) => setOtpCode(e.target.value.replace(/\D/g, ""))}
            placeholder="000000"
          />
          <div className="flex gap-2">
            <button
              onClick={handleAprovarExecutar}
              disabled={loading || otpCode.length !== 6}
              className="bg-[#FF6B35] hover:bg-orange-600 text-white px-6 py-2 rounded-lg text-sm font-bold disabled:opacity-40"
            >
              {loading ? "Executando..." : <span className="inline-flex items-center gap-1"><CheckCircle2 className="w-4 h-4" /> Aprovar e Executar</span>}
            </button>
          </div>
        </div>
      )}

      {error && <p className="text-red-600 text-sm mt-3 flex items-center gap-1"><AlertTriangle className="w-3.5 h-3.5" /> {error}</p>}

      <button
        onClick={handleCancelar}
        disabled={loading}
        className="mt-4 text-gray-500 hover:text-red-600 text-sm underline"
      >
        Cancelar pagamento
      </button>
    </div>
  );
}

// ── página principal ──────────────────────────────────────────────────────────

type Tab = "novo" | "preparados" | "aprovados" | "historico" | "categorizacao" | "audit";

const CATEGORIAS_VALIDAS = [
  "salario", "vale_transporte", "vale_alimentacao", "vt_va_combinado",
  "diaria_avulsa", "adiantamento", "reembolso", "fgts", "inss", "outros",
] as const;
type Categoria = typeof CATEGORIAS_VALIDAS[number];

const CATEGORIA_LABEL: Record<Categoria, string> = {
  salario: "Salário", vale_transporte: "Vale Transporte", vale_alimentacao: "Vale Alimentação",
  vt_va_combinado: "VT+VA", diaria_avulsa: "Diária", adiantamento: "Adiantamento",
  reembolso: "Reembolso", fgts: "FGTS", inss: "INSS", outros: "Outros",
};

const CATEGORIAS_KIT: Set<Categoria> = new Set(["salario", "vale_transporte", "vale_alimentacao", "vt_va_combinado"]);

interface CatTx {
  id: string;
  data: string;
  valor: number;
  beneficiario: string | null;
  descricao: string | null;
  categoria: Categoria | null;
  document_type: string | null;
  observacao: string | null;
  incluir_no_kit: boolean | null;
  sugerido_por_ia: boolean | null;
  confianca_sugestao: number | null;
}

interface StatsCategoria {
  categoria: string;
  incluir_no_kit: boolean;
  qtd: number;
  total_valor: number;
}

const API_CAT = "/api/v1/financeiro/inter";

export default function PagamentosPage() {
  const [tab, setTab] = useState<Tab>("preparados");
  const [payments, setPayments] = useState<Payment[]>([]);
  const [saldo, setSaldo] = useState<SaldoLimite | null>(null);
  const [loading, setLoading] = useState(false);
  const [selectedPayment, setSelectedPayment] = useState<Payment | null>(null);
  const [auditLog, setAuditLog] = useState<unknown[]>([]);
  const [auditLoading, setAuditLoading] = useState(false);
  const [auditError, setAuditError] = useState("");
  const [catNome, setCatNome] = useState("");
  const [catNomeBusca, setCatNomeBusca] = useState("");
  const [catMes, setCatMes] = useState(() => {
    const d = new Date();
    return `${String(d.getMonth() + 1).padStart(2, "0")}.${d.getFullYear()}`;
  });
  const [catObs, setCatObs] = useState<Record<string, string>>({});
  const qc = useQueryClient();
  const [isJordan, setIsJordan] = useState(false);

  useEffect(() => {
    try {
      const token = localStorage.getItem("access_token") || "";
      if (token) {
        const payload = JSON.parse(atob(token.split(".")[1] ?? ""));
        const email: string = payload.email || payload.sub || "";
        setIsJordan(email === "jjesus@conectamais.pro" || email === "jordansjesus@gmail.com");
      }
    } catch { /* JWT inválido — não é Jordan */ }
  }, []);

  const fetchPayments = useCallback(async (statusFilter?: string) => {
    setLoading(true);
    try {
      const qs = statusFilter ? `?status_filter=${statusFilter}` : "";
      const data = await apiFetch(`${API}${qs}`);
      setPayments(data.payments || []);
    } catch {
      setPayments([]);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchSaldo = useCallback(async () => {
    try {
      const data = await apiFetch(`${API}/saldo-limite`);
      setSaldo(data);
    } catch {
      setSaldo(null);
    }
  }, []);

  const fetchAudit = useCallback(async () => {
    setAuditLoading(true);
    setAuditError("");
    try {
      const data = await apiFetch(`${API}/audit?limit=100`);
      setAuditLog(Array.isArray(data) ? data : []);
    } catch (e: unknown) {
      setAuditError(e instanceof Error ? e.message : "Erro ao carregar audit log");
      setAuditLog([]);
    } finally {
      setAuditLoading(false);
    }
  }, []);

  const { data: catStatsRaw, isLoading: catStatsLoading, error: catStatsError } = useQuery({
    queryKey: ["inter-cat-stats", catMes],
    queryFn: () => apiFetch(`${API_CAT}/categorias/stats?mes_ref=${catMes}`) as Promise<{ por_categoria: StatsCategoria[] }>,
    enabled: tab === "categorizacao",
    staleTime: 30_000,
  });
  const catStats: StatsCategoria[] = catStatsRaw?.por_categoria ?? [];

  const { data: catTxsRaw, isLoading: catTxsLoading, error: catTxsError } = useQuery({
    queryKey: ["inter-cat-txs", catNomeBusca, catMes],
    queryFn: () => apiFetch(`${API_CAT}/colaborador/${encodeURIComponent(catNomeBusca.trim())}/categorias?mes_ref=${catMes}`) as Promise<CatTx[]>,
    enabled: tab === "categorizacao" && catNomeBusca.trim().length > 0,
    staleTime: 30_000,
  });
  const catTxs: CatTx[] = Array.isArray(catTxsRaw) ? catTxsRaw : [];
  const catLoading = catStatsLoading || catTxsLoading;
  const catError = catStatsError instanceof Error ? catStatsError.message
    : catTxsError instanceof Error ? catTxsError.message : "";

  const autoCatMutation = useMutation({
    mutationFn: (nome: string) => apiFetch(
      `${API_CAT}/colaborador/${encodeURIComponent(nome)}/auto-categorizar?mes_ref=${catMes}`,
      { method: "POST" },
    ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["inter-cat-txs", catNomeBusca, catMes] });
    },
  });

  const autoProcessarMutation = useMutation({
    mutationFn: () => apiFetch(
      `${API_CAT}/categorias/auto-processar${catMes ? `?mes_ref=${catMes}` : ""}`,
      { method: "POST" },
    ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["inter-cat-txs", catNomeBusca, catMes] });
      void qc.invalidateQueries({ queryKey: ["inter-cat-stats", catMes] });
    },
  });

  const categorizarMutation = useMutation({
    mutationFn: ({ id, categoria, observacao }: { id: string; categoria: Categoria; observacao?: string }) =>
      apiFetch(`${API_CAT}/transacoes/${id}/categorizar`, {
        method: "POST",
        body: JSON.stringify({ categoria, observacao: observacao ?? null }),
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["inter-cat-txs", catNomeBusca, catMes] });
    },
  });

  const handleAutoCat = () => {
    if (catNomeBusca.trim()) autoCatMutation.mutate(catNomeBusca.trim());
  };

  const handleCategorizar = (transactionId: string, categoria: Categoria, observacao?: string) => {
    categorizarMutation.mutate({ id: transactionId, categoria, observacao });
  };

  useEffect(() => {
    fetchSaldo();
    const interval = setInterval(fetchSaldo, 60_000);
    if (tab === "preparados") fetchPayments("preparado");
    else if (tab === "aprovados") fetchPayments("aprovado");
    else if (tab === "historico") fetchPayments();
    else if (tab === "audit") fetchAudit();
    else if (tab === "novo") setPayments([]);
    return () => clearInterval(interval);
  }, [tab, fetchPayments, fetchSaldo, fetchAudit]);

  const TABS: { key: Tab; label: ReactNode; red?: boolean }[] = [
    { key: "novo", label: "Novo Pagamento" },
    { key: "preparados", label: "Aguardando Aprovação" },
    { key: "aprovados", label: "Aguardando Execução" },
    { key: "historico", label: "Histórico" },
    { key: "categorizacao", label: "Categorização" },
    ...(isJordan
      ? [{ key: "audit" as Tab, label: <span className="flex items-center gap-1"><Lock className="w-3 h-3" />Audit Log</span>, red: true }]
      : []),
  ];

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div style={{ background: "linear-gradient(135deg, #0A2540 0%, #1a3a5c 100%)" }}
        className="px-6 py-8 text-white">
        <h1 className="font-display text-2xl font-semibold mb-1">Pagamentos Inter</h1>
        <p className="text-blue-200 text-sm">Módulo D7 — Operações de escrita com 2FA obrigatório</p>
      </div>

      {/* Saldo cards */}
      <div className="px-6 grid grid-cols-1 md:grid-cols-3 gap-4 mb-6 mt-6">
        {/* Card 1: Saldo Inter */}
        <div style={{ background: "linear-gradient(135deg, #0A2540 0%, #1E3A5F 100%)" }}
          className="rounded-xl p-5 text-white flex items-center gap-4 shadow">
          <div className="bg-white/10 p-3 rounded-lg">
            <Wallet className="w-6 h-6 text-white" />
          </div>
          <div>
            <p className="text-xs text-blue-300 uppercase tracking-wide">Saldo Inter</p>
            <p className="font-data text-xl font-semibold tabular-nums mt-0.5">{saldo ? fmt(saldo.saldo_inter) : "—"}</p>
            <p className="text-xs opacity-70 mt-1">Conta 370990072-2</p>
          </div>
        </div>

        {/* Card 2: Consumido Hoje */}
        <div className="bg-white rounded-xl p-5 flex items-center gap-4 shadow-sm border border-gray-100">
          <div className="bg-orange-100 p-3 rounded-lg">
            <TrendingDown className="w-6 h-6 text-[#FF6B35]" />
          </div>
          <div>
            <p className="text-xs text-gray-500 uppercase tracking-wide">Consumido Hoje</p>
            <p className="font-data text-xl font-semibold tabular-nums text-[#FF6B35] mt-0.5">{saldo ? fmt(saldo.consumido_hoje) : "—"}</p>
            <p className="text-xs text-gray-400 mt-0.5">Limite: {saldo ? fmt(saldo.limite_diario) : "—"}</p>
          </div>
        </div>

        {/* Card 3: Limite Restante */}
        <div className="bg-white rounded-xl p-5 flex items-center gap-4 shadow-sm border border-gray-100">
          <div className="bg-green-100 p-3 rounded-lg">
            <ShieldCheck className="w-6 h-6 text-green-600" />
          </div>
          <div>
            <p className="text-xs text-gray-500 uppercase tracking-wide">Limite Restante</p>
            <p className="font-data text-xl font-semibold tabular-nums text-green-600 mt-0.5">{saldo ? fmt(saldo.limite_restante) : "—"}</p>
            <p className="text-xs text-gray-400 mt-1">disponível pra hoje</p>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b bg-white px-6">
        <div className="flex gap-6">
          {TABS.map((t) => (
            <button
              key={t.key}
              onClick={() => { setTab(t.key); setSelectedPayment(null); }}
              className={`py-3 text-sm font-medium border-b-2 transition-colors ${
                tab === t.key
                  ? t.red
                    ? "border-red-600 text-red-700"
                    : "border-[#FF6B35] text-[#FF6B35]"
                  : t.red
                    ? "border-transparent text-red-600 hover:text-red-700"
                    : "border-transparent text-gray-500 hover:text-gray-700"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {/* Conteúdo */}
      <div className="p-6 max-w-5xl mx-auto">
        {tab === "novo" && (
          <NovoPagamentoForm saldo={saldo} onPrepared={() => { setTab("preparados"); fetchSaldo(); }} />
        )}

        {(tab === "preparados" || tab === "aprovados" || tab === "historico") && (
          <div className="space-y-4">
            {selectedPayment && tab === "preparados" && (
              <AprovacaoPagamento
                payment={selectedPayment}
                onAction={() => { setSelectedPayment(null); fetchPayments("preparado"); fetchSaldo(); }}
              />
            )}
            {loading ? (
              <div className="text-center py-12 text-gray-500">Carregando...</div>
            ) : payments.length === 0 ? (
              <div className="text-center py-12 text-gray-400">Nenhum pagamento encontrado</div>
            ) : (
              <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50 border-b">
                    <tr>
                      <th className="px-4 py-3 text-left text-gray-600 font-medium">Tipo</th>
                      <th className="px-4 py-3 text-right text-gray-600 font-medium">Valor</th>
                      <th className="px-4 py-3 text-left text-gray-600 font-medium">Data</th>
                      <th className="px-4 py-3 text-left text-gray-600 font-medium">Status</th>
                      <th className="px-4 py-3 text-left text-gray-600 font-medium">Inter ID</th>
                      <th className="px-4 py-3"></th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50">
                    {payments.map((p) => (
                      <tr key={p.id} className="hover:bg-gray-50 transition-colors">
                        <td className="px-4 py-3 font-medium">{TYPE_LABEL[p.payment_type]}</td>
                        <td className="px-4 py-3 text-right font-mono">{fmt(p.valor)}</td>
                        <td className="px-4 py-3">{p.data_pagamento}</td>
                        <td className="px-4 py-3"><StatusBadge status={p.status} /></td>
                        <td className="px-4 py-3 text-xs text-gray-400 font-mono">{p.inter_payment_id || "—"}</td>
                        <td className="px-4 py-3">
                          {p.status === "preparado" && isJordan && (
                            <button
                              onClick={() => setSelectedPayment(p)}
                              className="text-xs bg-[#FF6B35] text-white px-3 py-1 rounded-full hover:bg-orange-600"
                            >
                              Aprovar
                            </button>
                          )}
                          {p.status === "preparado" && !isJordan && (
                            <span className="text-xs text-gray-400">Aguardando Jordan</span>
                          )}
                          {p.status === "aprovado" && (
                            <button
                              onClick={async () => {
                                try {
                                  await apiFetch(`${API}/${p.id}/executar`, { method: "POST" });
                                  fetchPayments("aprovado");
                                } catch (e: unknown) {
                                  alert(e instanceof Error ? e.message : "Erro");
                                }
                              }}
                              className="text-xs bg-blue-600 text-white px-3 py-1 rounded-full hover:bg-blue-700"
                            >
                              Executar
                            </button>
                          )}
                          {p.inter_payment_id && (
                            <button
                              onClick={async () => {
                                try {
                                  const token = localStorage.getItem("access_token") || "";
                                  const res = await fetch(`${API}/${p.id}/comprovante`, { headers: { Authorization: `Bearer ${token}` } });
                                  if (!res.ok) { alert("Comprovante indisponível: pagamento ainda não concluído no Inter."); return; }
                                  const url = URL.createObjectURL(await res.blob());
                                  window.open(url, "_blank");
                                } catch { alert("Erro ao gerar comprovante."); }
                              }}
                              className="text-xs border border-gray-300 text-gray-700 px-3 py-1 rounded-full hover:bg-gray-100 ml-1"
                            >
                              Comprovante
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {tab === "categorizacao" && (
          <div className="space-y-4">
            {/* Filtros */}
            <div className="bg-white rounded-xl p-4 shadow-sm border border-gray-100 flex flex-wrap gap-3 items-end">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Colaborador</label>
                <input
                  className="border rounded-lg px-3 py-2 text-sm w-56"
                  placeholder="Nome do colaborador"
                  value={catNome}
                  onChange={(e) => setCatNome(e.target.value)}
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Mês (MM.AAAA)</label>
                <input
                  className="border rounded-lg px-3 py-2 text-sm w-32"
                  placeholder="04.2026"
                  value={catMes}
                  onChange={(e) => setCatMes(e.target.value)}
                />
              </div>
              <button
                onClick={() => setCatNomeBusca(catNome)}
                disabled={catLoading || !catNome.trim()}
                className="bg-[#0A2540] text-white px-4 py-2 rounded-lg text-sm hover:bg-[#1a3a5c] disabled:opacity-50"
              >
                Buscar
              </button>
              <button
                onClick={() => { setCatNomeBusca(catNome); handleAutoCat(); }}
                disabled={catLoading || !catNome.trim() || autoCatMutation.isPending}
                className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm hover:bg-blue-700 disabled:opacity-50"
              >
                {autoCatMutation.isPending ? "Processando..." : "Auto-Categorizar"}
              </button>
              <button
                onClick={() => autoProcessarMutation.mutate()}
                disabled={autoProcessarMutation.isPending}
                className="bg-orange-600 text-white px-4 py-2 rounded-lg text-sm hover:bg-orange-700 disabled:opacity-50"
              >
                {autoProcessarMutation.isPending ? "Processando..." : "Auto-Categorizar Todos"}
              </button>
              <button
                onClick={() => void qc.invalidateQueries({ queryKey: ["inter-cat-stats", catMes] })}
                disabled={catLoading}
                className="border border-gray-300 px-4 py-2 rounded-lg text-sm text-gray-600 hover:bg-gray-50 disabled:opacity-50"
              >
                Atualizar Stats
              </button>
            </div>

            {autoProcessarMutation.isSuccess && autoProcessarMutation.data && (
              <p className="text-sm text-green-600 mt-2">
                <CheckCircle2 className="w-4 h-4 inline" /> {(autoProcessarMutation.data as { categorizadas: number }).categorizadas} transações categorizadas automaticamente
              </p>
            )}

            {catError && (
              <div className="bg-red-50 text-red-700 text-sm rounded-xl px-4 py-3 border border-red-100">
                {catError}
              </div>
            )}

            {/* Stats do mês */}
            {catStats.length > 0 && catTxs.length === 0 && (
              <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-x-auto">
                <div className="px-4 py-3 border-b">
                  <h3 className="font-semibold text-[#0A2540] text-sm">Estatísticas — {catMes}</h3>
                </div>
                <table className="w-full text-sm">
                  <thead className="bg-gray-50 border-b">
                    <tr>
                      <th className="px-4 py-3 text-left text-gray-600 font-medium">Categoria</th>
                      <th className="px-4 py-3 text-left text-gray-600 font-medium">Kit?</th>
                      <th className="px-4 py-3 text-right text-gray-600 font-medium">Qtd</th>
                      <th className="px-4 py-3 text-right text-gray-600 font-medium">Total</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50">
                    {catStats.map((s, i) => (
                      <tr key={i} className="hover:bg-gray-50">
                        <td className="px-4 py-3 font-medium text-[#0A2540]">
                          {CATEGORIA_LABEL[s.categoria as Categoria] || s.categoria}
                        </td>
                        <td className="px-4 py-3">
                          {s.incluir_no_kit
                            ? <span className="bg-green-100 text-green-800 text-xs px-2 py-0.5 rounded-full font-medium">Kit</span>
                            : <span className="bg-gray-100 text-gray-500 text-xs px-2 py-0.5 rounded-full">Fora</span>}
                        </td>
                        <td className="px-4 py-3 text-right text-gray-600">{s.qtd}</td>
                        <td className="px-4 py-3 text-right font-medium text-[#0A2540]">{fmt(s.total_valor)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* Transações do colaborador */}
            {catTxs.length > 0 && (() => {
              const kitTxs = catTxs.filter(tx => tx.incluir_no_kit);
              const totalKit = kitTxs.reduce((s, tx) => s + tx.valor, 0);
              const porCat: Partial<Record<Categoria, number>> = {};
              kitTxs.forEach(tx => {
                if (tx.categoria) porCat[tx.categoria as Categoria] = (porCat[tx.categoria as Categoria] ?? 0) + tx.valor;
              });
              return (
                <>
                  {/* Resumo topo */}
                  <div className="bg-green-50 border border-green-200 rounded-xl px-4 py-3 flex flex-wrap gap-4 items-center text-sm">
                    <span className="font-semibold text-green-800">Total Kit: {fmt(totalKit)}</span>
                    {Object.entries(porCat).map(([cat, val]) => (
                      <span key={cat} className="text-green-700">{CATEGORIA_LABEL[cat as Categoria]}: {fmt(val ?? 0)}</span>
                    ))}
                    <span className="ml-auto text-gray-500 text-xs">{catTxs.length} transações ({kitTxs.length} no kit)</span>
                  </div>

                  <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-x-auto">
                    <div className="px-4 py-3 border-b flex justify-between items-center">
                      <h3 className="font-semibold text-[#0A2540] text-sm">{catNome} — {catMes}</h3>
                      <span className="text-xs text-gray-500">{catTxs.length} transações</span>
                    </div>
                    <table className="w-full text-sm">
                      <thead className="bg-gray-50 border-b">
                        <tr>
                          <th className="px-4 py-3 text-left text-gray-600 font-medium">Data</th>
                          <th className="px-4 py-3 text-left text-gray-600 font-medium">Beneficiário</th>
                          <th className="px-4 py-3 text-right text-gray-600 font-medium">Valor</th>
                          <th className="px-4 py-3 text-left text-gray-600 font-medium">Categoria</th>
                          <th className="px-4 py-3 text-left text-gray-600 font-medium">Observação</th>
                          <th className="px-4 py-3 text-left text-gray-600 font-medium">Badges</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-50">
                        {catTxs.map((tx) => (
                          <tr key={tx.id} className="hover:bg-gray-50">
                            <td className="px-4 py-3 text-xs text-gray-500 whitespace-nowrap">{tx.data || "—"}</td>
                            <td className="px-4 py-3 text-xs text-gray-700 max-w-xs truncate">
                              {tx.beneficiario || tx.descricao || "—"}
                            </td>
                            <td className="px-4 py-3 text-right font-medium text-[#0A2540] whitespace-nowrap">{fmt(tx.valor)}</td>
                            <td className="px-4 py-3">
                              <select
                                value={tx.categoria || ""}
                                onChange={(e) => {
                                  if (e.target.value) void handleCategorizar(tx.id, e.target.value as Categoria, catObs[tx.id]);
                                }}
                                className="border rounded px-2 py-1 text-xs text-gray-700"
                              >
                                <option value="">— sem categoria —</option>
                                {CATEGORIAS_VALIDAS.map((c) => (
                                  <option key={c} value={c}>{CATEGORIA_LABEL[c]}</option>
                                ))}
                              </select>
                            </td>
                            <td className="px-4 py-3">
                              <div className="flex gap-1 items-center">
                                <input
                                  className="border rounded px-2 py-1 text-xs text-gray-700 w-32"
                                  placeholder="Observação"
                                  value={catObs[tx.id] ?? tx.observacao ?? ""}
                                  onChange={(e) => setCatObs(prev => ({ ...prev, [tx.id]: e.target.value }))}
                                />
                                {catObs[tx.id] !== undefined && tx.categoria && (
                                  <button
                                    onClick={() => void handleCategorizar(tx.id, tx.categoria as Categoria, catObs[tx.id])}
                                    className="text-xs bg-[#0A2540] text-white px-2 py-1 rounded hover:bg-[#1a3a5c]"
                                  >
                                    Salvar
                                  </button>
                                )}
                              </div>
                            </td>
                            <td className="px-4 py-3">
                              <div className="flex gap-1 flex-wrap">
                                {tx.sugerido_por_ia && (
                                  <span className="bg-yellow-100 text-yellow-700 text-xs px-1.5 py-0.5 rounded-full">IA{tx.confianca_sugestao !== null ? ` ${Math.round((tx.confianca_sugestao ?? 0) * 100)}%` : ""}</span>
                                )}
                                {tx.incluir_no_kit
                                  ? <span className="bg-green-100 text-green-700 text-xs px-1.5 py-0.5 rounded-full inline-flex items-center gap-1"><CheckCircle2 className="w-3 h-3" /> Kit</span>
                                  : tx.categoria && <span className="bg-gray-100 text-gray-500 text-xs px-1.5 py-0.5 rounded-full">✗ Fora</span>}
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              );
            })()}

            {catLoading && (
              <div className="bg-white rounded-xl p-8 text-center text-gray-400 shadow-sm border border-gray-100">
                Carregando...
              </div>
            )}
          </div>
        )}

        {tab === "audit" && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="font-semibold text-[#0A2540]">Audit Log Global</h3>
                <p className="text-xs text-gray-500 mt-0.5">Todas as transições de pagamento — acesso restrito a Jordan</p>
              </div>
              <button
                onClick={fetchAudit}
                className="text-xs bg-[#0A2540] text-white px-3 py-1.5 rounded-lg hover:bg-[#1a3a5c] transition-colors"
              >
                Atualizar
              </button>
            </div>
            {auditLoading ? (
              <div className="bg-white rounded-xl p-8 text-center text-gray-400 shadow-sm border border-gray-100">
                Carregando audit log...
              </div>
            ) : auditError ? (
              <div className="bg-white rounded-xl p-8 text-center text-red-600 shadow-sm border border-gray-100">
                Erro: {auditError}
              </div>
            ) : auditLog.length === 0 ? (
              <div className="bg-white rounded-xl p-8 text-center text-gray-400 shadow-sm border border-gray-100">
                Nenhum registro de auditoria encontrado — execute o primeiro pagamento.
              </div>
            ) : (
              <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50 border-b">
                    <tr>
                      <th className="px-4 py-3 text-left text-gray-600 font-medium">Quando</th>
                      <th className="px-4 py-3 text-left text-gray-600 font-medium">Usuário</th>
                      <th className="px-4 py-3 text-left text-gray-600 font-medium">Pagamento</th>
                      <th className="px-4 py-3 text-left text-gray-600 font-medium">Transição</th>
                      <th className="px-4 py-3 text-left text-gray-600 font-medium">IP</th>
                      <th className="px-4 py-3 text-left text-gray-600 font-medium">Motivo</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50">
                    {(auditLog as Array<{
                      payment_id?: string; user_email?: string; payment_type?: string;
                      valor?: number; status_from?: string; status_to: string;
                      ip_address?: string; motivo?: string; created_at: string;
                    }>).map((entry, i) => (
                      <tr key={i} className="hover:bg-gray-50 transition-colors">
                        <td className="px-4 py-3 text-xs text-gray-400 whitespace-nowrap">
                          {new Date(entry.created_at).toLocaleString("pt-BR")}
                        </td>
                        <td className="px-4 py-3 text-xs text-gray-600">{entry.user_email || "—"}</td>
                        <td className="px-4 py-3 text-xs">
                          {entry.payment_type && (
                            <span className="font-medium text-[#0A2540]">{TYPE_LABEL[entry.payment_type as PaymentType] || entry.payment_type}</span>
                          )}
                          {entry.valor != null && (
                            <span className="text-gray-400 ml-1">{fmt(entry.valor)}</span>
                          )}
                          {!entry.payment_type && <span className="text-gray-300">—</span>}
                        </td>
                        <td className="px-4 py-3">
                          <span className={`text-xs px-1.5 py-0.5 rounded ${STATUS_COLOR[(entry.status_from || "") as PaymentStatus] || "bg-gray-100 text-gray-500"}`}>
                            {entry.status_from || "—"}
                          </span>
                          <span className="text-gray-300 mx-1">→</span>
                          <span className={`text-xs px-1.5 py-0.5 rounded ${STATUS_COLOR[entry.status_to as PaymentStatus] || "bg-gray-100 text-gray-500"}`}>
                            {entry.status_to}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-xs text-gray-400 font-mono">{entry.ip_address || "—"}</td>
                        <td className="px-4 py-3 text-xs text-gray-600">{entry.motivo || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
