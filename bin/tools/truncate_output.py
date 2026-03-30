#!/usr/bin/env python3
"""
truncate_output.py — stdin→stdout filter para proteger el contexto.

Uso como pipe: comando | python3 truncate_output.py [--head N] [--tail N]

Si el output supera el umbral, conserva head+tail y añade un mensaje
con instrucción para usar summarize_output.py si se necesita el resto.

Ejemplos:
  git log | python3 bin/tools/truncate_output.py
  cat app.log | python3 bin/tools/truncate_output.py --head 1500 --tail 500
"""

import argparse
import sys

HEAD_DEFAULT = 2000
TAIL_DEFAULT = 1000
THRESHOLD = HEAD_DEFAULT + TAIL_DEFAULT  # only truncate if larger than this


def main() -> None:
    parser = argparse.ArgumentParser(description="Truncate large stdout to save context")
    parser.add_argument("--head", type=int, default=HEAD_DEFAULT,
                        help="Characters to keep from the start")
    parser.add_argument("--tail", type=int, default=TAIL_DEFAULT,
                        help="Characters to keep from the end")
    parser.add_argument("--threshold", type=int, default=THRESHOLD,
                        help="Minimum chars before truncation kicks in")
    args = parser.parse_args()

    try:
        data = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"[truncate_output] read error: {e}", file=sys.stderr)
        sys.exit(1)

    if len(data) <= args.threshold:
        sys.stdout.write(data)
        return

    head = data[:args.head]
    tail = data[-args.tail:]
    omitted = len(data) - args.head - args.tail
    token_est = round(omitted / 4)  # ~4 chars per token

    banner = (
        f"\n{'─'*60}\n"
        f"[OUTPUT TRUNCADO: {omitted:,} chars ({token_est:,} tokens aprox.) omitidos]\n"
        f"Para analizar el resto: python3 bin/tools/summarize_output.py --query \"TU_PREGUNTA\"\n"
        f"{'─'*60}\n"
    )

    sys.stdout.write(head + banner + tail)


if __name__ == "__main__":
    main()
