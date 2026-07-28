from __future__ import annotations

from localwhisper.cli import _translate_legacy_args, build_parser


def test_legacy_cli_arguments_are_preserved():
    assert _translate_legacy_args(["--list-models"]) == ["models"]
    assert _translate_legacy_args(["--doctor", "--json"]) == ["doctor", "--json"]
    assert _translate_legacy_args(["--cli", "--duration", "3"]) == [
        "record",
        "--duration",
        "3",
    ]


def test_batch_transcribe_parser():
    args = build_parser().parse_args(
        ["transcribe", "one.wav", "two.mp4", "--format", "srt", "-o", "out"]
    )
    assert args.input == ["one.wav", "two.mp4"]
    assert args.format == "srt"
    assert args.output == "out"
