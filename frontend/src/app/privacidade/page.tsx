import Link from "next/link"

/**
 * Política de Privacidade — Conecta PRO
 * Criado: fix Skill-11 Verif.1 — link no rodapé da tela de login
 */
export const metadata = {
  title: "Política de Privacidade — Conecta PRO",
}

export default function PrivacidadePage() {
  return (
    <main className="min-h-screen bg-gray-50 py-12 px-4">
      <div className="max-w-3xl mx-auto bg-white rounded-2xl shadow-sm p-8">
        <h1 className="font-display text-2xl font-bold text-gray-900 mb-2">Política de Privacidade</h1>
        <p className="text-sm text-gray-500 mb-8">Última atualização: abril de 2026</p>

        <section className="space-y-6 text-gray-700 text-sm leading-relaxed">
          <div>
            <h2 className="font-semibold text-base text-gray-900 mb-2">1. Dados coletados</h2>
            <p>A Conecta Mais coleta dados necessários para a prestação dos serviços de ERP, incluindo nome, CPF, e-mail e dados funcionais conforme a LGPD (Lei nº 13.709/2018).</p>
          </div>
          <div>
            <h2 className="font-semibold text-base text-gray-900 mb-2">2. Uso dos dados</h2>
            <p>Os dados são utilizados exclusivamente para operação do sistema Conecta PRO, gestão de folha, DP e módulos contratados. Não são compartilhados com terceiros sem consentimento.</p>
          </div>
          <div>
            <h2 className="font-semibold text-base text-gray-900 mb-2">3. Seus direitos</h2>
            <p>Você pode solicitar acesso, correção ou exclusão dos seus dados a qualquer momento pelo e-mail <strong>privacidade@conectamais.pro</strong>.</p>
          </div>
          <div>
            <h2 className="font-semibold text-base text-gray-900 mb-2">4. Segurança</h2>
            <p>Utilizamos criptografia TLS, autenticação JWT e controles de acesso por perfil. Os servidores estão hospedados em ambiente seguro com backups diários.</p>
          </div>
        </section>

        <div className="mt-10 pt-6 border-t border-gray-100 flex gap-4">
          <Link href="/login" className="text-sm text-primary hover:underline">← Voltar ao login</Link>
          <Link href="/termos" className="text-sm text-gray-500 hover:underline">Termos de Uso</Link>
        </div>
      </div>
    </main>
  )
}
