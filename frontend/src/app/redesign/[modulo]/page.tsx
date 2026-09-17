import { Suspense } from 'react';
import ModuleView from '@/components/redesign/ModuleView';

export default async function ModuloPage({ params }: { params: Promise<{ modulo: string }> }) {
  const { modulo } = await params;
  // Suspense obrigatório: o ModuleView lê `?t=` por `useSearchParams` — sem a fronteira, o
  // build do Next falha ("should be wrapped in a suspense boundary") e a página inteira vira
  // renderização dinâmica.
  return (
    <Suspense fallback={null}>
      <ModuleView slug={modulo} />
    </Suspense>
  );
}
