# Changelog

## 0.2.0

- Novo onboarding com escolhas de idioma, ativação, streaming e privacidade.
- Perfis de escrita editáveis e duplicáveis, com ativação automática por app.
- Toggle e push-to-talk; ações inserir, inserir e enviar, clipboard e histórico.
- Comandos falados, limpeza de hesitações e formatação local conservadora.
- Estado explícito de sessão para evitar gravações/finalizações sobrepostas.
- Streaming com consenso de hipóteses, recuperação de divergência e cadência
  adaptativa; corrige inferência disparada a cada bloco de 30 ms.
- Carregamento do modelo fora da thread da interface e descarregamento por
  inatividade configurável.
- Fila de arquivos com modelo reutilizado, cancelamento e exportação em lote
  para TXT, SRT, VTT e JSON.
- Histórico com favoritos, busca, métricas, retenção e exportação.
- Modo privado e token HuggingFace protegido pelo Windows DPAPI.
- Página Diagnostics e comandos CLI para arquivos, histórico e suporte.
- Instância única, logs rotativos, configuração atômica e migração de schema.
- CI Windows em Python 3.10, 3.11 e 3.12, Ruff e suíte de regressão.

## 0.1.1

- Corrige restauração do clipboard para formatos Win32 que não usam `HGLOBAL`.
