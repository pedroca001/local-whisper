# LocalWhisper

App de ditado offline para Windows que roda na sua RTX 5070, com hotkey global, overlay
estilo macOS e injeção de texto direto na janela focada.

- **Hotkey global**: `Ctrl+Space` (configurável)
- **Modelos suportados**: Whisper Turbo (`large-v3-turbo`), Parakeet v3 Multilingual, Whisper Ultra (`large-v3`)
- **Streaming ao vivo** (palavras aparecem conforme você fala) **ou final-dump** (texto inteiro ao parar)
- **System tray** com menu Settings / Record manually / Quit
- **History** dos últimos 7 dias com busca, espelhado em arquivos `.txt` por dia
- **Transcribe File**: transcreve arquivos de áudio/vídeo (mp3, mp4, wav, mkv...) com identificação de falantes (diarização) via pyannote

## Requisitos

- Windows 10/11
- Python 3.10–3.12
- NVIDIA RTX 5070 (ou qualquer GPU NVIDIA com 6GB+; CPU também funciona, mais lento)
- Driver NVIDIA recente com suporte a CUDA 12.8

## Instalação rápida (recomendada)

Pré-requisitos: **Python 3.10–3.12** e **Git** instalados, e (opcional) driver NVIDIA recente.

```powershell
git clone https://github.com/pedroca001/local-whisper.git
cd local-whisper
.\install.ps1
```

O `install.ps1` é idempotente e faz tudo sozinho:

- Cria `.venv` se não existir.
- Detecta GPU NVIDIA e instala o PyTorch certo (cu128 pra RTX 50xx, cu121 pra 30xx/40xx, CPU caso não tenha).
- Instala o app em modo editable + extra `diarize` (identificação de falantes).
- Cria atalho **LocalWhisper** no Desktop.
- Adiciona à pasta **Startup** do Windows.

Flags úteis:

```powershell
.\install.ps1 -NoStartup     # não adicionar na inicialização
.\install.ps1 -NoShortcut    # não criar atalho no Desktop
.\install.ps1 -ForceCpu      # forçar PyTorch CPU mesmo com GPU
.\install.ps1 -CudaIndex https://download.pytorch.org/whl/cu118   # índice manual
```

> Se o PowerShell bloquear o script, abra um terminal como administrador uma vez e rode
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`. Ou rode o instalador com
> `powershell -ExecutionPolicy Bypass -File .\install.ps1`.

### Atualizar para a versão mais nova

```powershell
cd C:\caminho\para\local-whisper
git pull
.\install.ps1   # reaplica deps caso o pyproject tenha mudado
```

Como o app é instalado em modo editable (`pip install -e .`), na maioria dos `git pull`
basta fechar e reabrir o LocalWhisper — só precisa rerodar o instalador se as
dependências mudarem.

### Remover atalhos

```powershell
.\uninstall.ps1
```

Não apaga o source nem o `.venv` — só os atalhos do Desktop e da inicialização.

### Instalação manual (passo a passo)

Se preferir não usar o script:

```powershell
git clone https://github.com/pedroca001/local-whisper.git
cd local-whisper
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# PyTorch — escolha conforme sua GPU:
pip install --index-url https://download.pytorch.org/whl/cu128 torch torchaudio   # RTX 50xx
# pip install --index-url https://download.pytorch.org/whl/cu121 torch torchaudio # RTX 30xx/40xx
# pip install torch torchaudio                                                    # CPU only

pip install -e ".[diarize]"   # ou só pip install -e . se não quiser diarização
```

Pra rodar sem janela de console:
`.\.venv\Scripts\pythonw.exe run.py`

### Habilitar diarização (opcional)

Pra usar "Identify speakers" em **Transcribe File**:

1. Aceite os termos do modelo (logado no HuggingFace):
   <https://huggingface.co/pyannote/speaker-diarization-3.1>
2. Gere um token grátis tipo *Read*: <https://huggingface.co/settings/tokens>
3. No app: **Settings → Configuration → HuggingFace token** → cole o token.

A diarização roda 100% local depois do download inicial (~70 MB).

## Uso

```powershell
# Rodar o app completo (tray + hotkey + UI) — sem janela de console:
.\.venv\Scripts\pythonw.exe run.py

# Ou normal (com console pra ver logs):
python run.py

# Testar a transcrição via CLI (gravação de 5s)
python run.py --cli --duration 5 --model whisper-turbo
python run.py --cli --duration 5 --model parakeet-v3
python run.py --cli --duration 5 --model whisper-ultra

# Listar modelos
python run.py --list-models
```

## Verificação rápida

```bash
# CUDA OK?
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"

# faster-whisper carrega na GPU?
python -c "from faster_whisper import WhisperModel; m = WhisperModel('large-v3-turbo', device='cuda', compute_type='float16'); print('OK')"
```

## Onde os arquivos vivem

- Config: `%APPDATA%\LocalWhisper\config.json`
- Histórico (SQLite): `%APPDATA%\LocalWhisper\history.db`
- Modelos baixados: `%LOCALAPPDATA%\LocalWhisper\models`
- Transcrições `.txt`: pasta configurável em **Settings → Configuration → Save folder**
  (default: `%USERPROFILE%\Documents\LocalWhisper`)

## Como funciona

1. Você aperta `Ctrl+Space` em qualquer lugar do Windows.
2. O áudio do microfone selecionado começa a ser capturado (`sounddevice`, 16kHz mono).
3. Se o foco está em um campo de texto, o texto vai sendo digitado lá via `SendInput`
   com `KEYEVENTF_UNICODE` (acentos PT-BR funcionam corretamente).
4. Se o foco está no Desktop / Taskbar, um overlay preto aparece no topo central
   mostrando que está gravando. O texto vai para o histórico.
5. `Ctrl+Space` de novo → o engine finaliza e (em final-dump mode) injeta o resultado.

## Empacotamento (.exe)

```bash
pip install pyinstaller
pyinstaller --onedir --windowed --name LocalWhisper --icon icons/icon.ico --add-data "icons;icons" run.py
```

O modelo Whisper é baixado on-demand no primeiro uso para `%LOCALAPPDATA%\LocalWhisper\models`,
não embarcado no .exe.

## Testes

```bash
pip install pytest
pytest tests/
```
