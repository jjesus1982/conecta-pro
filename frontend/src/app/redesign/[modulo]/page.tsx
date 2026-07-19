import ModuleView from '@/components/redesign/ModuleView';

export default async function ModuloPage({ params }: { params: Promise<{ modulo: string }> }) {
  const { modulo } = await params;
  return <ModuleView slug={modulo} />;
}
