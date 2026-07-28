import sys

from localwhisper.cli import main

raise SystemExit(main(["transcribe", *sys.argv[1:]]))
