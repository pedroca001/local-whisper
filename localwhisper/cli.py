"""Command-line interface for LocalWhisper.

The desktop app remains the default. Subcommands expose useful local workflows
without starting Qt, which makes diagnostics and automation easy to script.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from . import __version__


def _record(args: argparse.Namespace) -> int:
    from .audio import SAMPLE_RATE, Recorder
    from .config import Config
    from .transcriber import get_engine

    cfg = Config.load()
    model = args.model or cfg.model
    engine = get_engine(model, cfg.compute_device, cfg.compute_type, cfg.models_dir)
    print(f"Loading {model}...")
    started = time.monotonic()
    engine.load()
    print(f"Model ready in {time.monotonic() - started:.1f}s.")

    recorder = Recorder(device=args.device)
    print(f"Recording for {args.duration:.1f}s. Speak now.")
    recorder.start()
    deadline = time.monotonic() + args.duration
    try:
        while time.monotonic() < deadline:
            time.sleep(0.05)
    except KeyboardInterrupt:
        pass
    audio = recorder.stop()
    print(f"Captured {audio.size / SAMPLE_RATE:.2f}s.")
    started = time.monotonic()
    text = engine.transcribe_full(audio, language=args.language or cfg.language)
    elapsed = time.monotonic() - started
    duration = audio.size / SAMPLE_RATE
    print(f"\n{text.strip()}\n")
    print(f"Transcribed in {elapsed:.2f}s ({duration / max(elapsed, 1e-6):.1f}x real-time).")
    engine.unload()
    return 0


def _models(_args: argparse.Namespace) -> int:
    from .transcriber import list_models

    for model in list_models():
        print(f"{model['key']:14s} {model['display_name']}")
        print(f"{'':14s} {model['subtitle']}")
        print(
            f"{'':14s} ~{model['approx_vram_gb']} GB VRAM, "
            f"~{model['speed_x_realtime']}x real-time"
        )
    return 0


def _doctor(args: argparse.Namespace) -> int:
    from .doctor import run_doctor

    result = run_doctor()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"LocalWhisper {result['summary']['version']} diagnostics")
        for name, value in result["checks"].items():
            if name == "dependencies":
                missing = [dep for dep, status in value.items() if not status["available"]]
                status = "OK" if not missing else f"MISSING {', '.join(missing)}"
            else:
                status = "OK" if value.get("ok") else "CHECK"
            print(f"  {name}: {status}")
        print(f"  log: {result['summary']['log_path']}")
    return 0 if result["ok"] else 1


def _transcribe(args: argparse.Namespace) -> int:
    from .config import Config
    from .transcriber import get_engine
    from .transcriber.file_transcriber import transcribe_file

    sources = [Path(value).expanduser().resolve() for value in args.input]
    missing = [source for source in sources if not source.is_file()]
    if missing:
        raise FileNotFoundError(missing[0])
    cfg = Config.load()
    engine = get_engine(
        args.model or cfg.model,
        cfg.compute_device,
        cfg.compute_type,
        cfg.models_dir,
    )
    engine.load()
    try:
        results = []
        for index, source in enumerate(sources, 1):
            result = transcribe_file(
                source,
                engine=engine,
                language=args.language or cfg.language,
                diarize=args.speakers,
                hf_token=cfg.hf_token or None,
                on_progress=lambda label, _pct, i=index, n=len(sources): print(
                    f"[{i}/{n}] {label}",
                    file=sys.stderr,
                ),
            )
            results.append((source, result))
    finally:
        engine.unload()

    if args.output:
        output = Path(args.output).expanduser().resolve()
        if len(results) == 1:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(
                _render_file_result(results[0][1], args.format, args.timestamps),
                encoding="utf-8",
            )
            print(output)
        else:
            output.mkdir(parents=True, exist_ok=True)
            for source, result in results:
                destination = output / f"{source.stem}.{args.format}"
                destination.write_text(
                    _render_file_result(result, args.format, args.timestamps),
                    encoding="utf-8",
                )
                print(destination)
    else:
        for source, result in results:
            if len(results) > 1:
                print(f"=== {source.name} ===")
            print(_render_file_result(result, args.format, args.timestamps))
    return 0


def _render_file_result(result, output_format: str, timestamps: bool) -> str:
    if output_format == "json":
        return result.to_json()
    if output_format == "srt":
        return result.to_srt()
    if output_format == "vtt":
        return result.to_vtt()
    return result.to_txt(with_timestamps=timestamps)


def _history_list(args: argparse.Namespace) -> int:
    from . import storage

    rows = (
        storage.search(args.query, days=args.days, limit=args.limit)
        if args.query
        else storage.list_recent(
            days=args.days,
            limit=args.limit,
            favorites_only=args.favorites,
        )
    )
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    for row in rows:
        star = "*" if row.get("favorite") else " "
        text = str(row.get("text") or "").replace("\n", " ")
        print(f"{star} {row['started_at']} [{row.get('mode', 'default')}] {text}")
    return 0


def _history_stats(args: argparse.Namespace) -> int:
    from . import storage

    result = storage.stats(args.days)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(
            f"{result['sessions']} sessions, {result['words']} words, "
            f"{result['duration_minutes']:.1f} minutes, "
            f"{result['words_per_minute']:.0f} words/minute"
        )
    return 0


def _history_export(args: argparse.Namespace) -> int:
    from . import storage

    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(storage.export_history(args.days, args.format), encoding="utf-8")
    print(output)
    return 0


def _app(_args: argparse.Namespace) -> int:
    from .app import main as app_main

    return app_main()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="localwhisper")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command")

    record = subparsers.add_parser("record", help="Record once and print the transcript")
    record.add_argument("--duration", type=float, default=5.0)
    record.add_argument("--device", type=int)
    record.add_argument("--model")
    record.add_argument("--language")
    record.set_defaults(handler=_record)

    models = subparsers.add_parser("models", help="List available speech models")
    models.set_defaults(handler=_models)

    doctor = subparsers.add_parser("doctor", help="Run read-only installation diagnostics")
    doctor.add_argument("--json", action="store_true")
    doctor.set_defaults(handler=_doctor)

    transcribe = subparsers.add_parser("transcribe", help="Transcribe an audio or video file")
    transcribe.add_argument("input", nargs="+")
    transcribe.add_argument(
        "-o",
        "--output",
        help="Output file for one input, or output directory for a batch",
    )
    transcribe.add_argument("--format", choices=["txt", "json", "srt", "vtt"], default="txt")
    transcribe.add_argument("--model")
    transcribe.add_argument("--language")
    transcribe.add_argument("--speakers", action="store_true")
    transcribe.add_argument("--timestamps", action="store_true")
    transcribe.set_defaults(handler=_transcribe)

    history = subparsers.add_parser("history", help="Inspect or export local history")
    history_subparsers = history.add_subparsers(dest="history_command")
    history_list = history_subparsers.add_parser("list", help="List recent history")
    history_list.add_argument("--days", type=int, default=30)
    history_list.add_argument("--limit", type=int, default=50)
    history_list.add_argument("--query", default="")
    history_list.add_argument("--favorites", action="store_true")
    history_list.add_argument("--json", action="store_true")
    history_list.set_defaults(handler=_history_list)
    history_stats = history_subparsers.add_parser("stats", help="Show history statistics")
    history_stats.add_argument("--days", type=int, default=30)
    history_stats.add_argument("--json", action="store_true")
    history_stats.set_defaults(handler=_history_stats)
    history_export = history_subparsers.add_parser("export", help="Export history")
    history_export.add_argument("output")
    history_export.add_argument("--days", type=int, default=30)
    history_export.add_argument("--format", choices=["markdown", "json"], default="markdown")
    history_export.set_defaults(handler=_history_export)

    app = subparsers.add_parser("app", help="Launch the desktop app")
    app.set_defaults(handler=_app)
    return parser


def _translate_legacy_args(argv: list[str]) -> list[str]:
    """Preserve the original run.py switches used by scripts and docs."""
    if "--list-models" in argv:
        return ["models"]
    if "--doctor" in argv:
        result = ["doctor"]
        if "--json" in argv:
            result.append("--json")
        return result
    if "--cli" in argv:
        return ["record", *[item for item in argv if item != "--cli"]]
    return argv


def main(argv: list[str] | None = None) -> int:
    actual_argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    args = parser.parse_args(_translate_legacy_args(actual_argv))
    handler = getattr(args, "handler", None)
    if handler is None:
        return _app(args)
    try:
        return int(handler(args) or 0)
    except KeyboardInterrupt:
        print("Cancelled.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"LocalWhisper error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
