# LocalWhisper

App de ditado offline para Windows que roda na sua RTX 5070, com hotkey global, overlay
estilo macOS e injeção de texto direto na janela focada.

- **Hotkey global**: `Ctrl+Space` (configurável)
- **Modelos suportados**: Whisper Turbo (`large-v3-turbo`), Parakeet v3 Multilingual, Whisper Ultra (`large-v3`)
- **Streaming ao vivo** (palavras aparecem conforme você fala) **ou final-dump** (texto inteiro ao parar)
- **System tray** com menu Settings / Record manually / Quit
- **History** dos últimos 7 dias com busca, espelhado em arquivos `.txt` por dia

## Requisitos

- Windows 10/11
- Python 3.10–3.12
- NVIDIA RTX 5070 (ou qualquer GPU NVIDIA com 6GB+; CPU também funciona, mais lento)
- Driver NVIDIA recente com suporte a CUDA 12.8

## Instalação

```bash
# 1) Crie um venv
python -m venv .venv
.venv\Scripts\activate

# 2) Instale o PyTorch para sua GPU (Blackwell sm_120 precisa de cu128)
pip install --index-url https://download.pytorch.org/whl/cu128 torch torchaudio

# 3) Instale o app
pip install -e .

# 4) (Opcional) Para usar Parakeet v3:
pip install "nemo_toolkit[asr]>=2.0.0"
```

## Uso

```bash
# Rodar o app completo (tray + hotkey + UI)
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
