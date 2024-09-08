import argparse
from pathlib import Path
import os
import re
import itertools


def main():
    parser = argparse.ArgumentParser(
        prog="single_unified",
        description="Converts one .md file to multiple, and vice versa",
    )

    parser.add_argument("command", choices=["split", "combine"])
    parser.add_argument("input")
    parser.add_argument("output")

    args = parser.parse_args()

    if args.command == "split":
        input_file = Path(args.input).resolve()
        output_dir = Path(args.output).absolute()
        os.makedirs(output_dir, exist_ok=True)
        output_dir = output_dir.resolve()

        if not (input_file.is_file() and output_dir.is_dir()):
            raise ValueError

        split = re.split(r"\s*# (\d+(?:\.\d+)?)\n\s*", input_file.read_text())
        if split[0] and not split[0].isspace():
            raise ValueError(split[0])

        split = split[1:]
        if (len(split) % 2) != 0:
            raise ValueError(len(split))

        for num, text in itertools.batched(split, 2):
            output_file = output_dir / f"{num}.md"
            output_file.write_text(text)

    elif args.command == "combine":
        input_dir = Path(args.input).resolve()
        output_file = Path(args.output).resolve()

        if (not input_dir.is_dir()) or (
            output_file.exists() and not output_file.is_file()
        ):
            raise ValueError

        lines = []
        for p in input_dir.glob("*.md"):
            num = p.name.removesuffix(".md")
            lines.append(f"# {num}")
            lines.append(p.read_text().strip())

        output_file.write_text("\n\n".join(lines))


if __name__ == "__main__":
    main()
