# LocalWhisper

App de ditado offline para Windows com hotkey global, perfis por aplicativo,
streaming estável e injeção de texto direto na janela focada. O áudio e o texto
ficam no computador.

- **Hotkey global**: `Ctrl+Space` (configurável)
- **Toggle ou push-to-talk**: pressione para iniciar/parar ou segure enquanto fala
- **Modelos suportados**: Whisper Turbo (`large-v3-turbo`), Parakeet v3 Multilingual, Whisper Ultra (`large-v3`)
- **Streaming ao vivo estável** com consenso entre hipóteses, recuperação segura e cadência adaptativa
- **Perfis de escrita**: Natural, Verbatim, AI Prompt, Email, Chat e perfis personalizados
- **Ativação por app**: um perfil pode entrar automaticamente no Outlook, Slack, Codex, navegador etc.
- **Ações de saída**: inserir, inserir e enviar, copiar ou salvar apenas no
  histórico; perfis herdam a ação global por padrão e podem substituí-la
- **Comandos falados** e limpeza local de hesitações, sem depender de API externa
- **System tray** com menu Settings / Record manually / Quit
- **Copy last entry no tray**: clique direito no ícone e copie a última transcrição mesmo se o overlay não aparecer
- **History** pesquisável com favoritos, métricas, retenção configurável e exportação Markdown/JSON
- **Modo privado**: dita sem gravar no histórico
- **Transcribe File**: fila de áudio/vídeo, processamento em lote, cancelamento real, diarização e exportação TXT/SRT/VTT/JSON
- **Model manager**: instala/desinstala modelos e permite escolher a pasta de cache
- **Correções de vocabulário**: regras locais do tipo `cloud -> CLAUDE`
- **Onboarding e Diagnostics**: primeira configuração guiada e relatório de suporte sem segredos
- **CLI completa**: gravação, arquivos, lotes, histórico, estatísticas e diagnóstico

No modo `Insert and press Enter`, o Enter só é enviado se a mesma janela
editável capturada continuar ativa. Streaming nunca injeta deltas quando a ação
efetiva é `Copy to clipboard` ou `Save to history only`.

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

For synced source folders, keep the heavy Python runtime outside the synced repo:

```powershell
.\install.ps1 -VenvPath "$env:LOCALAPPDATA\LocalWhisper\venv"
```

### Instruções para LLMs/agentes instalarem a partir do link

Se o usuário pedir para instalar o LocalWhisper e fornecer apenas este repositório,
trate este README como a fonte de verdade e siga este fluxo no Windows:

```powershell
# 1) Escolha uma pasta local para o source.
mkdir "$env:USERPROFILE\Projects" -ErrorAction SilentlyContinue
cd "$env:USERPROFILE\Projects"

# 2) Clone o repositório, ou atualize se ele já existir.
if (Test-Path .\LocalWhisper\.git) {
    cd .\LocalWhisper
    git pull
} else {
    git clone https://github.com/pedroca001/local-whisper.git LocalWhisper
    cd .\LocalWhisper
}

# 3) Rode o instalador oficial.
powershell -ExecutionPolicy Bypass -File .\install.ps1

# Se o source estiver em pasta sincronizada, mantenha a venv fora dela.
powershell -ExecutionPolicy Bypass -File .\install.ps1 -VenvPath "$env:LOCALAPPDATA\LocalWhisper\venv"
```

O instalador oficial `install.ps1` deve ser preferido a comandos manuais. Ele:

- valida Python 3.10, 3.11 ou 3.12;
- cria/reusa `.venv` ou o caminho passado em `-VenvPath`;
- detecta NVIDIA via `nvidia-smi`;
- instala PyTorch com CUDA `cu128` quando houver GPU NVIDIA e CPU quando não houver;
- instala o pacote em modo editable com `pip install -e .[diarize]`;
- cria o atalho `LocalWhisper.lnk` na Área de Trabalho;
- cria o atalho de inicialização em `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup`;
- roda um smoke test de imports.
- executa diagnóstico de configuração, banco, ffmpeg, dependências e CUDA;

Depois de instalar, valide assim:

```powershell
# O app deve listar os modelos.
.\.venv\Scripts\python.exe run.py --list-models

# Os testes sem GUI devem passar.
.\.venv\Scripts\python.exe -m pytest tests/

# O atalho do Desktop deve apontar para pythonw.exe run.py.
$ws = New-Object -ComObject WScript.Shell
$lnk = $ws.CreateShortcut("$env:USERPROFILE\Desktop\LocalWhisper.lnk")
$lnk | Format-List Target*, Arguments, WorkingDirectory, IconLocation
```

Para abrir o app depois da instalação:

```powershell
& ".\.venv\Scripts\pythonw.exe" ".\run.py"
```

Ou use o atalho **LocalWhisper** criado na Área de Trabalho.

Notas importantes para agentes:

- Não instale dependências globais; use a `.venv` criada pelo `install.ps1`.
- Se o source estiver em Google Drive/Dropbox/OneDrive, use `-VenvPath "$env:LOCALAPPDATA\LocalWhisper\venv"`.
- Não troque o fluxo para `.exe`; a instalação suportada é source install.
- Não mova o bloco inicial de redirect de logs em `run.py`.
- Em Windows PowerShell 5.1, evite redirecionar stderr de comandos nativos com
  `2>$null` sob `$ErrorActionPreference = "Stop"`.
- Se o usuário quiser não iniciar com o Windows, rode `.\install.ps1 -NoStartup`.
- Se o usuário quiser apenas o app sem atalho de Desktop, rode `.\install.ps1 -NoShortcut`.
- Logs ficam em `%LOCALAPPDATA%\LocalWhisper\app.log` e
  `%LOCALAPPDATA%\LocalWhisper\app.log.err`.
- Relatórios copiados/salvos pela página Diagnostics substituem o diretório
  pessoal por `%USERPROFILE%`.

O `install.ps1` é idempotente e faz tudo sozinho:

- Cria `.venv` se não existir, ou usa `-VenvPath` quando informado.
- Detecta GPU NVIDIA e instala o PyTorch certo (`cu128` para NVIDIA recente, CPU caso não tenha).
- Instala o app em modo editable + extra `diarize` (identificação de falantes).
- Cria atalho **LocalWhisper** no Desktop.
- Adiciona à pasta **Startup** do Windows.

Flags úteis:

```powershell
.\install.ps1 -NoStartup     # não adicionar na inicialização
.\install.ps1 -NoShortcut    # não criar atalho no Desktop
.\install.ps1 -ForceCpu      # forçar PyTorch CPU mesmo com GPU
.\install.ps1 -CudaIndex https://download.pytorch.org/whl/cu128   # índice manual
.\install.ps1 -VenvPath "$env:LOCALAPPDATA\LocalWhisper\venv"      # venv fora do source
.\install.ps1 -VenvPath "$env:LOCALAPPDATA\LocalWhisper\venv" -Check   # diagnóstico sem reinstalar
.\install.ps1 -VenvPath "$env:LOCALAPPDATA\LocalWhisper\venv" -Repair  # repara pacote e atalhos
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

Não apaga o source nem a venv — só os atalhos do Desktop e da inicialização.

### Instalação manual (passo a passo)

Se preferir não usar o script:

```powershell
git clone https://github.com/pedroca001/local-whisper.git
cd local-whisper
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# PyTorch — escolha conforme seu hardware:
pip install --index-url https://download.pytorch.org/whl/cu128 torch torchaudio   # NVIDIA recente
# pip install --index-url https://download.pytorch.org/whl/cpu torch torchaudio   # CPU only

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

# Gravar 5 segundos e imprimir o texto
python run.py record --duration 5 --model whisper-turbo

# Transcrever um arquivo
python run.py transcribe reuniao.mp4 --format txt -o reuniao.txt

# Transcrever um lote reutilizando o modelo; -o vira a pasta de saída
python run.py transcribe aula-1.mp4 aula-2.mp4 --format srt -o .\legendas

# Histórico e estatísticas
python run.py history list --days 30 --query projeto
python run.py history stats --days 30 --json
python run.py history export historico.md --days 90

# Listar modelos
python run.py models

# Diagnóstico legível ou JSON
python run.py doctor
python run.py doctor --json
```

Os switches antigos `--cli`, `--list-models` e `--doctor` continuam aceitos.
Em lotes, nomes-base repetidos ou já existentes recebem sufixos como `-2` e
`-3`; nenhum export anterior é sobrescrito silenciosamente.

## Verificação rápida

```bash
# CUDA OK?
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"

# faster-whisper carrega na GPU?
python -c "from faster_whisper import WhisperModel; m = WhisperModel('large-v3-turbo', device='cuda', compute_type='float16'); print('OK')"
```

## Onde os arquivos vivem

- Config: `%APPDATA%\LocalWhisper\config.json`
- Segredos: `%LOCALAPPDATA%\LocalWhisper\secrets.json` (criptografados com Windows DPAPI)
- Histórico (SQLite): `%APPDATA%\LocalWhisper\history.db`
- Runtime Python opcional: `%LOCALAPPDATA%\LocalWhisper\venv`
- Modelos baixados: `%LOCALAPPDATA%\LocalWhisper\models`
- Pasta de modelos configurável: **Settings → Modes → Installed models**
- Transcrições `.txt`: pasta configurável em **Settings → Configuration → Save folder**
  (default: `%USERPROFILE%\Documents\LocalWhisper`)

## Como funciona

1. Você aperta `Ctrl+Space` em qualquer lugar do Windows.
2. O áudio do microfone selecionado começa a ser capturado (`sounddevice`, 16kHz mono).
3. Se o foco está em um campo de texto, o app escolhe a inserção mais limpa:
   `EM_REPLACESEL` para controles Win32/RichEdit (ex.: Notepad), `SendInput`
   Unicode como fallback nativo, e clipboard protegido + `Ctrl+V` apenas para
   alvos modernos como Chromium/Electron/editores web. O clipboard temporário é
   marcado para não entrar no histórico/cloud clipboard e o clipboard original é
   restaurado depois.
4. Se o foco está no Desktop / Taskbar, um overlay preto aparece no topo central
   mostrando que está gravando. O texto vai para o histórico.
5. `Ctrl+Space` de novo → o engine finaliza e (em final-dump mode) injeta o resultado.

O streaming nunca sobrescreve texto que já foi inserido. Ele só confirma
prefixos estáveis entre hipóteses consecutivas; se o resultado final divergir,
o texto completo aparece no overlay para recuperação, em vez de anexar um
sufixo incorreto.

Gravações silenciosas são descartadas antes de chamar o modelo, evitando frases
inventadas como "E aí" quando o microfone capturou pouco ou nenhum áudio.

## Empacotamento secundário (.exe)

```powershell
.\build.ps1 -VenvPath "$env:LOCALAPPDATA\LocalWhisper\venv"
```

O instalador Inno Setup gerado usa o nome
`dist\LocalWhisper-Setup-<versão>.exe`. Esse bundle é uma distribuição
secundária, limitada aos modelos Whisper: Parakeet e diarização não são
incluídos. A release suportada continua sendo o source archive do GitHub com
`install.ps1`. Os modelos Whisper são baixados sob demanda para
`%LOCALAPPDATA%\LocalWhisper\models`.

## Testes

```bash
pip install pytest
pytest tests/
```
