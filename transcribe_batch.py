import sys
import os
from faster_whisper import WhisperModel

models_dir = os.path.join(os.environ.get("LOCALAPPDATA", ""), "LocalWhisper", "models")
model = WhisperModel("large-v3-turbo", device="cuda", compute_type="float16", download_root=models_dir)

for path in sys.argv[1:]:
    print(f"\n=== FILE: {path} ===")
    segments, info = model.transcribe(path, language="en")
    print(f"Language: {info.language}, Duration: {info.duration:.1f}s")
    for s in segments:
        print(f"[{s.start:.1f}-{s.end:.1f}] {s.text}")
    print(f"=== END ===")
