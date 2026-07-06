'use client';

import { useState } from 'react';
import type { CompletudeKit, MotivoFaltante } from '@/types/kit-completude';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { customInstance } from '@/lib/api-client';
import { CheckCircle2 } from 'lucide-react';

const MOTIVO_LABELS: Record<MotivoFaltante, string> = {
  nao_encontrado_onvio: 'Não sincronizado do Onvio',
  aguarda_fase_1_cnd: 'Aguarda busca automática CND (FASE 1)',
  aguarda_fase_2_banco: 'Aguarda integração bancária (FASE 2)',
  nao_sincronizado: 'Não sincronizado',
};

interface EnvioResult {
  sucesso: boolean;
  email_enviado: string;
  drive_link: string | null;
  sent_at: string;
}

interface KitDetalheModalProps {
  kit: CompletudeKit | null;
  open: boolean;
  onClose: () => void;
  onEnviado?: (condominioId: string, result: EnvioResult) => void;
  sentResult?: EnvioResult | null;
}

export function KitDetalheModal({ kit, open, onClose, onEnviado, sentResult }: KitDetalheModalProps) {
  const [showConfirm, setShowConfirm] = useState(false);
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);

  if (!kit) return null;

  const pct = kit.metricas.pct_completude_confirmada;
  const canSend = pct >= 100;
  const alreadySent = !!sentResult;

  async function handleEnviar() {
    if (!canSend || sending) return;
    setSending(true);
    setSendError(null);
    try {
      // Parse mes_ref (MM.YYYY) → month + year for GED kits lookup
      const [mm, yyyy] = kit!.mes_ref.split('.');
      const month = parseInt(mm, 10);
      const year = parseInt(yyyy, 10);

      // Step 1: find kit_id via GED kits list
      const listResp = await customInstance<{ items: Array<{ id: string }> }>({
        url: '/api/v1/ged/kits',
        method: 'GET',
        params: { client_id: kit!.condominio_id, month, year, limit: 1 },
      });
      const items = listResp?.items ?? [];
      if (items.length === 0) {
        setSendError('Kit não cadastrado no GED para este mês. Monte o kit primeiro.');
        return;
      }
      const kitId = items[0].id;

      // Step 2: send via unified endpoint
      const result = await customInstance<EnvioResult>({
        url: `/api/v1/ged/kits/${kitId}/enviar`,
        method: 'POST',
      });
      setShowConfirm(false);
      onEnviado?.(kit!.condominio_id, result);
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        'Erro ao enviar kit. Tente novamente.';
      setSendError(msg);
    } finally {
      setSending(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-3xl max-h-[80vh] overflow-y-auto bg-[hsl(var(--card))] text-[hsl(var(--foreground))]">
        <DialogHeader>
          <DialogTitle>
            {kit.condominio_nome} — {kit.mes_ref}
          </DialogTitle>
        </DialogHeader>

        <div className="mb-3 flex flex-wrap items-center gap-3 text-sm text-[hsl(var(--muted-foreground))]">
          <span>Esperado: <strong>{kit.metricas.total_esperado}</strong></span>
          <span>Presentes: <strong>{kit.metricas.total_presente_confirmado}</strong></span>
          <span>Faltantes: <strong>{kit.metricas.total_faltante}</strong></span>
          <span>Completude: <strong>{pct.toFixed(1)}%</strong></span>

          {alreadySent ? (
            <Badge className="ml-auto bg-emerald-500 text-white inline-flex items-center gap-1">
              <CheckCircle2 className="h-3 w-3" /> Enviado em {new Date(sentResult!.sent_at).toLocaleDateString('pt-BR')}
            </Badge>
          ) : (
            <div className="ml-auto flex items-center gap-2">
              {!showConfirm ? (
                <Button
                  size="sm"
                  disabled={!canSend}
                  title={canSend ? 'Enviar via GDrive + Email' : 'Kit incompleto'}
                  onClick={() => { setSendError(null); setShowConfirm(true); }}
                  className={canSend ? 'bg-blue-600 hover:bg-blue-700 text-white' : ''}
                  variant={canSend ? 'default' : 'secondary'}
                >
                  Enviar Kit
                </Button>
              ) : (
                <div className="flex items-center gap-2">
                  <span className="text-xs text-[hsl(var(--muted-foreground))]">Confirmar envio?</span>
                  <Button
                    size="sm"
                    onClick={handleEnviar}
                    disabled={sending}
                    className="bg-emerald-500 hover:bg-emerald-600 text-white"
                  >
                    {sending ? 'Enviando…' : 'Sim, enviar'}
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={sending}
                    onClick={() => setShowConfirm(false)}
                  >
                    Cancelar
                  </Button>
                </div>
              )}
            </div>
          )}
        </div>

        {sendError && (
          <div className="mb-3 rounded border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-500">
            {sendError}
          </div>
        )}

        {alreadySent && sentResult?.drive_link && (
          <div className="mb-3 rounded border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-500">
            Kit enviado para <strong>{sentResult.email_enviado}</strong>.{' '}
            <a
              href={sentResult.drive_link}
              target="_blank"
              rel="noopener noreferrer"
              className="underline"
            >
              Ver no Drive
            </a>
          </div>
        )}

        <Tabs defaultValue="presentes">
          <TabsList>
            <TabsTrigger value="presentes">
              Docs Presentes ({kit.docs_presentes.length})
            </TabsTrigger>
            <TabsTrigger value="faltantes">
              Docs Faltantes ({kit.docs_faltantes.length})
            </TabsTrigger>
          </TabsList>

          <TabsContent value="presentes">
            {kit.docs_presentes.length === 0 ? (
              <p className="py-6 text-center text-sm text-[hsl(var(--muted-foreground))]">Nenhum documento presente.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-[hsl(var(--secondary))]">
                    <tr>
                      <th className="p-2 text-left font-medium">Tipo</th>
                      <th className="p-2 text-left font-medium">Escopo</th>
                      <th className="p-2 text-left font-medium">Arquivo</th>
                      <th className="p-2 text-left font-medium">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {kit.docs_presentes.map((d) => (
                      <tr key={d.onvio_document_id} className="border-t border-[hsl(var(--border))]">
                        <td className="p-2">{d.tipo_documento}</td>
                        <td className="p-2 text-[hsl(var(--muted-foreground))]">{d.escopo}</td>
                        <td className="p-2 max-w-xs truncate text-[hsl(var(--foreground))]">{d.nome_arquivo}</td>
                        <td className="p-2">
                          {d.revisao_pendente ? (
                            <Badge className="bg-amber-500/10 text-amber-500 border-amber-500/30">
                              Revisão
                            </Badge>
                          ) : (
                            <Badge className="bg-emerald-500/10 text-emerald-500 border-emerald-500/30">
                              OK
                            </Badge>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </TabsContent>

          <TabsContent value="faltantes">
            {kit.docs_faltantes.length === 0 ? (
              <p className="py-6 text-center text-sm text-[hsl(var(--muted-foreground))]">
                Todos os documentos estão presentes.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-[hsl(var(--secondary))]">
                    <tr>
                      <th className="p-2 text-left font-medium">Tipo</th>
                      <th className="p-2 text-left font-medium">Escopo</th>
                      <th className="p-2 text-left font-medium">Motivo</th>
                    </tr>
                  </thead>
                  <tbody>
                    {kit.docs_faltantes.map((d, i) => (
                      <tr key={`${d.tipo_documento}-${i}`} className="border-t border-[hsl(var(--border))]">
                        <td className="p-2">{d.tipo_documento}</td>
                        <td className="p-2 text-[hsl(var(--muted-foreground))]">{d.escopo}</td>
                        <td className="p-2 text-[hsl(var(--muted-foreground))]">{MOTIVO_LABELS[d.motivo]}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}
