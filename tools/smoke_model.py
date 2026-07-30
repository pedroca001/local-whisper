"""Load and warm up a real speech model without recording microphone audio."""
from __future__ import annotations

import argparse
import json
import time

from localwhisper import gpu
from localwhisper.transcriber import get_engine


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("models_dir")
    parser.add_argument("--model", default="whisper-turbo")
    args = parser.parse_args()

    gpu.setup()
    engine = get_engine(args.model, "cuda", "float16", args.models_dir)
    started = time.monotonic()
    engine.load()
    elapsed = time.monotonic() - started
    result = {
        "model": args.model,
        "loaded": engine.is_loaded(),
        "device": getattr(engine, "_device", "unknown"),
        "load_seconds": round(elapsed, 2),
    }
    engine.unload()
    print(json.dumps(result, indent=2))
    return 0 if result["loaded"] and result["device"] == "cuda" else 1


if __name__ == "__main__":
    raise SystemExit(main())
