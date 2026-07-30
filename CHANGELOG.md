# Changelog

## 0.2.0

- Novo onboarding com escolhas de idioma, ativação, streaming e privacidade.
- Perfis de escrita editáveis e duplicáveis, com ativação automática por app.
- Toggle e push-to-talk; ações inserir, inserir e enviar, clipboard e histórico.
- A ação global de saída agora é herdada pelos perfis por padrão; overrides de
  perfil continuam disponíveis e streaming respeita modos clipboard/histórico.
- `Insert and press Enter` só envia Enter se a janela editável capturada ainda
  for exatamente a janela ativa e o resultado não exigir recuperação.
- Comandos falados, limpeza de hesitações e formatação local conservadora.
- Estado explícito de sessão para evitar gravações/finalizações sobrepostas.
- Streaming com consenso de hipóteses, recuperação de divergência e cadência
  adaptativa; corrige inferência disparada a cada bloco de 30 ms.
- Carregamento do modelo fora da thread da interface e descarregamento por
  inatividade configurável.
- Fila de arquivos com modelo reutilizado, cancelamento e exportação em lote
  para TXT, SRT, VTT e JSON.
- Exports em lote desambiguam nomes repetidos e nunca sobrescrevem arquivos
  existentes silenciosamente.
- Histórico com favoritos, busca, métricas, retenção e exportação.
- History virtualizado com carregamento sob demanda, sem materializar centenas
  de células na thread da interface e sem aplicar resultados de filtros antigos.
- Modo privado e token HuggingFace protegido pelo Windows DPAPI.
- Relatórios de diagnóstico redigem o diretório do usuário antes de copiar ou
  salvar informações de suporte.
- Página Diagnostics e comandos CLI para arquivos, histórico e suporte.
- Instância única, logs rotativos, configuração atômica e migração de schema.
- CI Windows em Python 3.10, 3.11 e 3.12, Ruff e suíte de regressão.
- Encerramento seguro cancela e aguarda workers de arquivo, History e
  Diagnostics; durante a finalização do ditado, adia a saída até salvar o
  resultado antes de destruir a aplicação.
- Metadados de release e instalador versionado alinhados em `0.2.0`.

## 0.1.1

- Corrige restauração do clipboard para formatos Win32 que não usam `HGLOBAL`.
