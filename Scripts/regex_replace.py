import argparse
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

import yaml

SENTENCE_END_RE = re.compile(r'[.!?…]["\')\]]*\s*$')


@dataclass
class Rule:
    find: str
    replace: str
    regex: bool = False
    manual: bool = False
    notes: str = ""
    flags: int = 0
    case_mode: str = "literal"  # literal | preserve_case | sentence_aware

    def pattern(self) -> re.Pattern:
        if self.regex:
            return re.compile(self.find, self.flags)
        return re.compile(re.escape(self.find), self.flags)


def load_rules(yaml_path: Path) -> List[Rule]:
    with yaml_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not data or "rules" not in data:
        raise ValueError('YAML file must contain a top-level "rules" list.')

    rules = []
    for i, item in enumerate(data["rules"], start=1):
        if not item:
            continue

        find = item.get("find")
        replace = item.get("replace", "")
        regex = bool(item.get("regex", False))
        manual = bool(item.get("manual", False))
        notes = item.get("notes", "")
        case_mode = item.get("case_mode", "literal")

        if case_mode not in {"literal", "preserve_case", "sentence_aware"}:
            raise ValueError(f"Rule #{i}: invalid case_mode '{case_mode}'")

        if find is None:
            raise ValueError(f'Rule #{i} is missing "find".')

        flags_value = 0
        flags_list = item.get("flags", [])
        if isinstance(flags_list, str):
            flags_list = [flags_list]

        for flag in flags_list:
            flag = flag.lower()
            if flag in ("i", "ignorecase"):
                flags_value |= re.IGNORECASE
            elif flag in ("m", "multiline"):
                flags_value |= re.MULTILINE
            elif flag in ("s", "dotall"):
                flags_value |= re.DOTALL
            else:
                raise ValueError(f'Unknown flag "{flag}" in rule #{i}')

        rules.append(
            Rule(
                find=find,
                replace=replace,
                regex=regex,
                manual=manual,
                notes=notes,
                flags=flags_value,
                case_mode=case_mode,
            )
        )

    return rules


def line_col_from_offset(text: str, offset: int) -> Tuple[int, int]:
    line = text.count("\n", 0, offset) + 1
    last_newline = text.rfind("\n", 0, offset)
    if last_newline == -1:
        col = offset + 1
    else:
        col = offset - last_newline
    return line, col


def capitalize_initial(s: str) -> str:
    if not s:
        return s
    return s[0].upper() + s[1:]


def apply_case_pattern(source: str, replacement: str) -> str:
    if not source:
        return replacement

    if source.isupper():
        return replacement.upper()

    if source.islower():
        return replacement.lower()

    if source[0].isupper() and source[1:].islower():
        return capitalize_initial(replacement.lower())

    return replacement


def is_sentence_start(text: str, start: int) -> bool:
    if start == 0:
        return True

    i = start - 1
    while i >= 0 and text[i] in (" ", "\t"):
        i -= 1

    if i < 0:
        return True

    if text[i] == "\n":
        return True

    lookback_start = max(0, i - 200)
    lookback = text[lookback_start : i + 1].rstrip()

    return bool(SENTENCE_END_RE.search(lookback))


def make_replacement_function(rule: Rule, full_text: str):
    def repl(match: re.Match) -> str:
        expanded = match.expand(rule.replace)

        if rule.case_mode == "literal":
            return expanded

        if rule.case_mode == "preserve_case":
            return apply_case_pattern(match.group(0), expanded)

        if rule.case_mode == "sentence_aware":
            if is_sentence_start(full_text, match.start()):
                return capitalize_initial(expanded)
            return expanded.lower()

        return expanded

    return repl


def apply_rules(text: str, rules: List[Rule], file_path: str):
    manual_hits = []
    replacement_counts = []

    for idx, rule in enumerate(rules, start=1):
        pattern = rule.pattern()
        matches = list(pattern.finditer(text))

        if matches and rule.manual:
            for m in matches:
                line, col = line_col_from_offset(text, m.start())
                snippet_start = max(0, m.start() - 50)
                snippet_end = min(len(text), m.end() + 50)
                snippet = text[snippet_start:snippet_end].replace("\n", "\\n")
                manual_hits.append(
                    {
                        "file": file_path,
                        "rule_number": idx,
                        "find": rule.find,
                        "replace": rule.replace,
                        "line": line,
                        "column": col,
                        "match_text": m.group(0),
                        "notes": rule.notes,
                        "snippet": snippet,
                    }
                )

        repl_func = make_replacement_function(rule, text)
        text, replaced_count = pattern.subn(repl_func, text)

        replacement_counts.append((idx, replaced_count, rule.find, rule.replace))

    return text, manual_hits, replacement_counts


def collect_md_files(input_path: Path) -> List[Path]:
    if input_path.is_file():
        if input_path.suffix.lower() != ".md":
            raise ValueError(f"Input file is not .md: {input_path}")
        return [input_path]

    if input_path.is_dir():
        return sorted(input_path.rglob("*.md"))

    raise ValueError(f"Input path does not exist: {input_path}")


def write_output_file(
    src_file: Path, input_base: Path, output_base: Path, content: str
):
    if input_base.is_file():
        out_file = output_base
    else:
        rel = src_file.relative_to(input_base)
        out_file = output_base / rel

    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(content, encoding="utf-8")


def write_manual_review(manual_hits, output_path: Path):
    lines = ["# Manual Review Report", ""]

    if not manual_hits:
        lines.append("No manual-review matches found.")
        lines.append("")
        output_path.write_text("\n".join(lines), encoding="utf-8")
        return

    current_file = None
    current_rule = None

    for hit in manual_hits:
        if hit["file"] != current_file:
            current_file = hit["file"]
            current_rule = None
            lines.append(f"## File: `{current_file}`")
            lines.append("")

        rule_key = (hit["rule_number"], hit["find"], hit["replace"], hit["notes"])
        if rule_key != current_rule:
            current_rule = rule_key
            lines.append(f"### Rule {hit['rule_number']}")
            lines.append(f"- find: `{hit['find']}`")
            lines.append(f"- replace: `{hit['replace']}`")
            if hit["notes"]:
                lines.append(f"- notes: {hit['notes']}")
            lines.append("")

        lines.append(f"- location: `{hit['file']}:{hit['line']}:{hit['column']}`")
        lines.append(f"  - matched: `{hit['match_text']}`")
        lines.append(f"  - context: `{hit['snippet']}`")
        lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(
        description="Regex/plain-text replacement on Markdown files using YAML rules."
    )
    default_rules_path = (
        Path(__file__).resolve().parent.parent / "Volumes" / "replacements.yaml"
    )

    parser.add_argument("input", help="Input .md file or directory of .md files")
    parser.add_argument(
        "--rules",
        default=default_rules_path,
        help=f"YAML rules file (default: Volumes/replacements.yaml)",
    )

    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("-o", "--output", help="Output file or directory")
    mode.add_argument(
        "-i", "--in-place", action="store_true", help="Overwrite input files"
    )

    parser.add_argument(
        "--manual-review",
        default="manual_review.md",
        help="Path to manual review report",
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        help="Create backups when using `--in-place`",
    )

    args = parser.parse_args()

    input_path = Path(args.input)
    rules_path = Path(args.rules)
    manual_review_path = Path(args.manual_review)

    if args.backup and not args.in_place:
        parser.error("--backup can only be used with --in-place")

    rules = load_rules(rules_path)
    files = collect_md_files(input_path)

    all_manual_hits = []
    all_replacement_counts = []

    output_path = Path(args.output) if args.output else None

    for file_path in files:
        original_text = file_path.read_text(encoding="utf-8")
        new_text, manual_hits, replacement_counts = apply_rules(
            original_text, rules, str(file_path)
        )

        all_manual_hits.extend(manual_hits)
        all_replacement_counts.extend(
            (str(file_path), *item) for item in replacement_counts
        )

        if args.in_place:
            if new_text != original_text:
                if args.backup:
                    backup_path = file_path.with_suffix(file_path.suffix + ".bak")
                    shutil.copy2(file_path, backup_path)
                file_path.write_text(new_text, encoding="utf-8")
        else:
            write_output_file(file_path, input_path, output_path, new_text)

    write_manual_review(all_manual_hits, manual_review_path)

    print(f"Processed {len(files)} file(s).")
    print(f"Manual review file: {manual_review_path}")
    print(f"Manual-review hits: {len(all_manual_hits)}")


if __name__ == "__main__":
    main()
