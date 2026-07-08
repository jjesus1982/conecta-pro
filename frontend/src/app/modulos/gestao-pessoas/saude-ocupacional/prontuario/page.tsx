'use client';

/**
 * Prontuário SST 360 — página índice.
 * Busca o funcionário (EmployeeSelect compartilhado) e abre o dossiê completo.
 */

import { useRouter } from 'next/navigation';
import { HeartPulse, SearchCheck } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { EmployeeSelect } from '@/components/sst/EmployeeSelect';

export default function ProntuarioIndexPage() {
  const router = useRouter();

  return (
    <div className="space-y-6 pb-28">
      <div>
        <h1 className="font-display flex items-center gap-2 text-2xl font-bold text-[hsl(var(--foreground))]">
          <HeartPulse className="h-6 w-6" />
          Prontuário SST 360
        </h1>
        <p className="text-muted-foreground">
          Dossiê completo de saúde ocupacional por funcionário — ASOs, EPIs, riscos,
          treinamentos, afastamentos e CATs em uma página
        </p>
      </div>

      <Card className="max-w-2xl">
        <CardHeader>
          <CardTitle className="font-display flex items-center gap-2 text-base">
            <SearchCheck className="h-4 w-4" /> Abrir prontuário
          </CardTitle>
          <CardDescription>
            Busque por nome, cargo, matrícula ou CPF — a seleção abre o dossiê do funcionário.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <EmployeeSelect
            value=""
            onChange={(employeeId) => {
              if (employeeId) {
                router.push(
                  `/modulos/gestao-pessoas/saude-ocupacional/prontuario/${employeeId}`
                );
              }
            }}
            placeholder="Buscar funcionário para abrir o prontuário..."
          />
          <p className="mt-3 text-xs text-muted-foreground">
            Também acessível pelos nomes clicáveis nas telas de Compliance NR-1 e Exames/ASOs.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
