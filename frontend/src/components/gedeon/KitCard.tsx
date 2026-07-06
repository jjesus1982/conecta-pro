'use client';

import type { CompletudeKit, TipoServico } from '@/types/kit-completude';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { CheckCircle2 } from 'lucide-react';

interface KitCardProps {
  kit: CompletudeKit;
  onClick: () => void;
  enviado?: boolean;
}

function getCardClasses(pct: number, tipo: TipoServico): string {
  if (tipo === 'administrativo') return 'border-[hsl(var(--border))] bg-[hsl(var(--secondary))]';
  if (pct >= 100) return 'border-emerald-500 bg-emerald-500/10';
  if (pct >= 80) return 'border-blue-500 bg-blue-500/10';
  if (pct >= 50) return 'border-amber-500 bg-amber-500/10';
  return 'border-red-500 bg-red-500/10';
}

const TIPO_LABELS: Record<TipoServico, string> = {
  kit_mensal: 'Kit Mensal',
  portaria_remota: 'Port. Remota',
  portaria_autonoma: 'Port. Autônoma',
  manutencao_cftv: 'Manutenção CFTV',
  administrativo: 'Administrativo',
};

export function KitCard({ kit, onClick, enviado = false }: KitCardProps) {
  const { condominio_nome, tipo_servico, metricas } = kit;
  const isAdmin = tipo_servico === 'administrativo';
  const pct = metricas.pct_completude_confirmada;
  const cls = getCardClasses(pct, tipo_servico);

  return (
    <Card
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(e) => e.key === 'Enter' && onClick()}
      className={`cursor-pointer border-2 p-4 transition hover:shadow-md ${cls}`}
      data-testid="kit-card"
    >
      <div className="flex items-start justify-between gap-2">
        <h3 className="font-bold text-[hsl(var(--foreground))] leading-tight">{condominio_nome}</h3>
        <div className="flex shrink-0 flex-col items-end gap-1">
          <Badge variant="outline" className="text-xs">
            {TIPO_LABELS[tipo_servico]}
          </Badge>
          {enviado && (
            <Badge className="bg-emerald-500 text-white text-xs inline-flex items-center gap-1">
              <CheckCircle2 className="h-3 w-3" /> Enviado
            </Badge>
          )}
        </div>
      </div>

      {isAdmin ? (
        <div className="mt-4">
          <Badge className="bg-[hsl(var(--muted))] text-[hsl(var(--muted-foreground))]">SEM KIT</Badge>
          <p className="mt-2 text-xs text-[hsl(var(--muted-foreground))]">Escritório não possui kit documental</p>
        </div>
      ) : (
        <>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">{pct.toFixed(1)}%</span>
            <span className="text-sm text-[hsl(var(--muted-foreground))]">confirmado</span>
          </div>
          <Progress value={pct} className="mt-2 h-2" />
          <p className="mt-2 text-sm text-[hsl(var(--muted-foreground))]">
            {metricas.total_presente_confirmado} / {metricas.total_esperado} docs
          </p>
          {metricas.total_presente_pendente_revisao > 0 && (
            <Badge className="mt-2 bg-amber-500 text-white text-xs">
              {metricas.total_presente_pendente_revisao} em revisão
            </Badge>
          )}
        </>
      )}
    </Card>
  );
}
