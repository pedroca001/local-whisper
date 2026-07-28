# LocalWhisper — Visão Geral do Projeto

## O que é

LocalWhisper é um **aplicativo de ditado offline para Windows** que transcreve fala em texto usando os modelos Whisper e Parakeet rodando localmente, com aceleração por GPU NVIDIA. Tudo funciona sem enviar áudio para nenhum servidor externo.

---

## Como funciona

### Fluxo principal

1. O usuário pressiona `Ctrl+Space` em qualquer janela do Windows.
2. O microfone começa a gravar.
3. Um **overlay** aparece na parte superior da tela mostrando o microfone em uso e os botões Stop e Cancel.
4. Ao pressionar `Ctrl+Space` novamente (ou Stop):
   - Se o cursor estiver em uma caixa de texto → o texto transcrito é digitado diretamente ali.
   - Se não houver caixa de texto focada → o texto aparece no overlay para ser copiado manualmente.
5. O texto é salvo no histórico do app.

### Injeção de texto

- Usa `EM_REPLACESEL` em controles Win32/RichEdit (incluindo Notepad moderno)
  para inserir no cursor/seleção sem tocar no clipboard.
- Usa `SendInput` + `KEYEVENTF_UNICODE` como fallback nativo.
- Usa clipboard protegido + `Ctrl+V` cadenciado apenas em alvos modernos
  (Chromium/Electron/editores web) que precisam de paste; o conteúdo temporário
  é marcado para não entrar no histórico/cloud clipboard e o clipboard original
  é restaurado.
- Reconhece campos de texto comuns e editores modernos: ProseMirror, Monaco, CodeMirror, Quill, contenteditable.

---

## Funcionalidades

| Funcionalidade | Descrição |
|---|---|
| **Hotkey global** | `Ctrl+Space` inicia/para a gravação em qualquer janela |
| **Injeção de texto** | Digita o texto transcrito no campo de texto focado |
| **Overlay** | Aparece quando não há campo de texto; exibe resultado copiável |
| **Bandeja do sistema (tray)** | Menu com: Configurações, Gravar manualmente, Sair |
| **Copiar última entrada** | Primeira opção do tray; copia a última transcrição para o clipboard |
| **Interface de configurações** | Janela PySide6 com as páginas abaixo |
| **Histórico** | Busca, favoritos, métricas, retenção configurável e exportação |
| **Modo privado** | Não persiste a transcrição nem o espelho `.txt` |
| **Perfis de escrita** | Presets e perfis customizados com ativação automática por app |
| **Push-to-talk** | Alternativa ao hotkey de toggle |
| **Transcrição de arquivo** | Fila/lote de mp3, mp4, wav, mkv e outros formatos |
| **Identificação de falantes** | Via pyannote.audio — etiqueta `[Speaker N]` no texto |
| **Legendas** | Exportação TXT, JSON, SRT e VTT |
| **Diagnóstico** | Página e CLI para dependências, ffmpeg, banco e CUDA |
| **Inicialização automática** | Pode ser configurado para iniciar com o Windows |
| **Gerenciador de modelos** | Instala/desinstala modelos e permite escolher a pasta de cache |
| **Correções de vocabulário** | Regras locais para corrigir termos técnicos após a transcrição |

### Páginas da interface de configurações

- **Home** — visão geral e status
- **Modes** — escolha do modelo, dispositivo (Auto/CUDA/CPU) e precisão (Float16, Int8 Float16, Int8)
- **Transcribe File** — fila de mídia, cancelamento, lote, diarização e legendas
- **Vocabulary** — vocabulário personalizado para melhorar o reconhecimento de termos específicos
- **Configuration** — configurações gerais, token do HuggingFace
- **Sound** — configurações de áudio e microfone
- **History** — visualização do histórico de transcrições
- **Diagnostics** — saúde da instalação e relatório redigido para suporte

---

## Modelos disponíveis

| Modelo | Descrição |
|---|---|
| `whisper-turbo` | Padrão — rápido e eficiente |
| `whisper-ultra` | Maior qualidade (`large-v3`) |
| `parakeet-v3` | Opcional — via NeMo, carregamento tardio |

---

## Estrutura de arquivos

```
run.py                          # Ponto de entrada; redirecionamento de logs + argparse
install.ps1                     # Instalador automático (idempotente)
uninstall.ps1                   # Remove apenas os atalhos
pyproject.toml                  # Instalação editável + extras: parakeet, diarize, dev
localwhisper/
  app.py                        # QApplication, bandeja, ligação do hotkey
  audio.py                      # Gravador sounddevice, SAMPLE_RATE=16000
  hotkey.py                     # Hotkey global via Win32 RegisterHotKey
  injector.py                   # Inserção Win32 direta + clipboard protegido + Unicode
  focus.py                      # Detecta se a janela focada tem campo de texto
  config.py                     # Config atômica + migração de schema
  secret_store.py               # Segredos protegidos por Windows DPAPI
  session.py                    # Máquina de estados das sessões de ditado
  text_processing.py            # Comandos e limpeza local conservadora
  doctor.py                     # Diagnóstico somente leitura
  storage.py                    # Histórico SQLite + espelho .txt
  gpu.py                        # Detecção NVML + registro do diretório CUDA
  autostart.py                  # Toggle de HKCU\...\Run (inicialização automática)
  transcriber/
    base.py                     # Classe abstrata ASREngine
    registry.py                 # list_models / get_engine
    faster_whisper_engine.py    # Engines baseados em ctranslate2
    parakeet_engine.py          # Import tardio NeMo (opcional)
    diarization.py              # Wrapper do pipeline pyannote.audio
    file_transcriber.py         # ffmpeg → ASR → diarize → resultado final
  ui/
    settings_window.py          # Barra lateral + troca de páginas
    style.qss                   # Stylesheet Qt
    icons.py                    # Ícones SVG
    pages/                      # home, modes, transcribe_file, vocabulary,
                                # configuration, sound, history
    widgets/                    # card, waveform, toggle_switch
  resources/icons/              # Ícones do app e da bandeja
tests/                          # pytest, sem dependências de GUI
```

---

## Instalação

### Recomendada (fonte via GitHub)

```powershell
git clone https://github.com/pedroca001/local-whisper.git
cd local-whisper
.\install.ps1
```

Para source em pasta sincronizada, mantenha a venv fora do repo:

```powershell
.\install.ps1 -VenvPath "$env:LOCALAPPDATA\LocalWhisper\venv"
```

O `install.ps1` é idempotente e realiza automaticamente:

1. Verifica Python 3.10–3.12.
2. Cria o `.venv` se não existir, ou usa `-VenvPath` quando informado.
3. Detecta GPU NVIDIA via `nvidia-smi` e escolhe o índice PyTorch correto:
   - RTX 50xx / Blackwell → `cu128`
   - Outras NVIDIA → `cu121`
   - Sem NVIDIA → `cpu`
4. Instala torch + torchaudio se necessário.
5. `pip install -e .[diarize]` — instalação editável com diarização.
6. Smoke test informativo.
7. Cria atalho `LocalWhisper.lnk` na Área de Trabalho e na pasta de Inicialização do Windows.

### Comandos úteis

```powershell
# Rodar com console (para depuração)
.\.venv\Scripts\python.exe run.py

# Rodar em modo silencioso (produção)
.\.venv\Scripts\pythonw.exe run.py

# Ver log de erros
Get-Content "$env:LOCALAPPDATA\LocalWhisper\app.log.err" -Tail 80

# Teste CLI (sem interface, sem bandeja)
.\.venv\Scripts\python.exe run.py record --duration 5 --model whisper-turbo

# Arquivo/lote e diagnóstico
.\.venv\Scripts\python.exe run.py transcribe .\reuniao.mp4 --format srt -o .\reuniao.srt
.\.venv\Scripts\python.exe run.py doctor --json

# Listar modelos disponíveis
.\.venv\Scripts\python.exe run.py --list-models

# Rodar testes
.\.venv\Scripts\python.exe -m pytest tests/
```

---

## Arquivos gerados pelo app

| Arquivo/Pasta | Conteúdo |
|---|---|
| `%APPDATA%\LocalWhisper\config.json` | Configurações do usuário |
| `%APPDATA%\LocalWhisper\history.db` | Banco de dados SQLite do histórico |
| `%LOCALAPPDATA%\LocalWhisper\app.log` | Log principal |
| `%LOCALAPPDATA%\LocalWhisper\app.log.err` | Log de erros |
| `%LOCALAPPDATA%\LocalWhisper\venv` | Runtime Python opcional fora do source |
| `%LOCALAPPDATA%\LocalWhisper\models` | Cache dos modelos Whisper |
| `Config.models_dir` | Pasta configurável para instalação/cache dos modelos |
| `%USERPROFILE%\.cache\huggingface` | Pesos do pyannote (~70 MB) |
| `%USERPROFILE%\Documents\LocalWhisper` | Transcrições visíveis ao usuário (configurável) |

---

## Requisitos para diarização (identificação de falantes)

A funcionalidade de identificação de falantes usa o modelo `pyannote/speaker-diarization-3.1`, que é restrito. Para usá-la:

1. Aceite os termos em: https://huggingface.co/pyannote/speaker-diarization-3.1
2. Gere um token em: https://huggingface.co/settings/tokens
3. Cole o token em: Configurações → Configuration → HuggingFace token

Sem o token, a transcrição de arquivos continua funcionando — só as etiquetas de falante são omitidas.

---

## Distribuição

A distribuição é feita exclusivamente via **instalação por código-fonte**. O build em `.exe` (PyInstaller + Inno Setup) ainda existe mas **não suporta diarização**, pois `torch`/`torchaudio` são excluídos do bundle para mantê-lo pequeno. O caminho recomendado é o clone do repositório.
