import Link from "next/link"

/**
 * Termos de Uso — Conecta PRO
 * Criado: fix Skill-11 Verif.1 — link no rodapé da tela de login
 */
export const metadata = {
  title: "Termos de Uso — Conecta PRO",
}

export default function TermosPage() {
  return (
    <main className="min-h-screen bg-gray-50 py-12 px-4">
      <div className="max-w-3xl mx-auto bg-white rounded-2xl shadow-sm p-8">
        <h1 className="font-display text-2xl font-bold text-gray-900 mb-2">Termos de Uso</h1>
        <p className="text-sm text-gray-500 mb-8">Última atualização: abril de 2026</p>

        <section className="space-y-6 text-gray-700 text-sm leading-relaxed">
          <div>
            <h2 className="font-semibold text-base text-gray-900 mb-2">1. Aceitação</h2>
            <p>Ao utilizar o Conecta PRO, você concorda com estes termos. O sistema é de uso exclusivo das empresas clientes do Grupo Conecta Mais — CONECTAMAIS ELETRONICA LTDA (CNPJ 35.710.481/0001-03) e CONECTAMAIS PATRIMONIAL LTDA (CNPJ 66.014.833/0001-10).</p>
          </div>
          <div>
            <h2 className="font-semibold text-base text-gray-900 mb-2">2. Responsabilidades do usuário</h2>
            <p>O usuário é responsável pela confidencialidade de suas credenciais e pelo uso adequado das funcionalidades contratadas, em conformidade com a legislação brasileira vigente.</p>
          </div>
          <div>
            <h2 className="font-semibold text-base text-gray-900 mb-2">3. Disponibilidade</h2>
            <p>O sistema opera com SLA de 99,5% de disponibilidade mensal. Manutenções programadas são comunicadas com antecedência mínima de 24 horas.</p>
          </div>
          <div>
            <h2 className="font-semibold text-base text-gray-900 mb-2">4. Propriedade intelectual</h2>
            <p>O Conecta PRO é software proprietário. É vedada a reprodução, engenharia reversa ou redistribuição sem autorização expressa da Conecta Mais.</p>
          </div>
          <div>
            <h2 className="font-semibold text-base text-gray-900 mb-2">5. Contato</h2>
            <p>Dúvidas: <strong>suporte@conectamais.pro</strong> | Jurídico: <strong>juridico@conectamais.pro</strong></p>
          </div>
        </section>

        <div className="mt-10 pt-6 border-t border-gray-100 flex gap-4">
          <Link href="/login" className="text-sm text-primary hover:underline">← Voltar ao login</Link>
          <Link href="/privacidade" className="text-sm text-gray-500 hover:underline">Política de Privacidade</Link>
        </div>
      </div>
    </main>
  )
}
