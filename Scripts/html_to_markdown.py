import sys

SUBPART_NUMBER = 0


def main():
    args = sys.argv
    if len(args) == 1:
        sys.stderr.write("You need to provide a file\n")
        sys.exit(1)

    filename = args[1]
    if not filename.endswith(".html"):
        sys.stderr.write(f"You need to provide a .html file ({filename})\n")
        sys.exit(1)

    markdown_filename = filename[:-5] + ".md"

    with open(filename, "r") as file:
        lines = file.readlines()

    with open(markdown_filename, "w") as markdown_file:
        markdown_file.write(
            "\n\n".join(
                print_text(book)
                for book in replace_sublist(
                    parse_lines(lines),
                    [
                        ("ornament1", ""),
                        ("ornament2", ""),
                        ("ornament3", ""),
                        ("ornament4", ""),
                        ("ornamentx", ""),
                        ("ornamentx", ""),
                        ("ornamentx", ""),
                    ],
                    ("ornament", ""),
                )
            )
        )


def replace_sublist(lst, sublist, replacement):
    index = 0
    while index < len(lst):
        try:
            idx = lst.index(sublist[0], index)
            if lst[idx : idx + len(sublist)] == sublist:
                lst[idx : idx + len(sublist)] = [replacement]
                index = idx + 1
            else:
                index = idx + 1
        except ValueError:
            break
    return lst


def strip_tag(line):
    start_index = line.find(">") + 1
    end_index = line.rfind("<")
    return line[start_index:end_index]


def grab_tag(string):
    if string[0] == "<":
        return string.split(">")[0] + ">"
    return None


TAG_MAPPING = {
    '<p class="h1_co">': "subpart",
    '<p class="h1_co1">': "subpart",
    '<p class="tx">': "body",
    '<p class="tx1">': "body",
    '<p class="cotx1a">': "body",
    '<p class="space-break">': "breakbody",
    '<div class="ext_ch">': "ornament1",
    '<div class="decoration-rw10">': "ornament2",
    '<div class="media-rw image-rw float-none-rw floatgalley-none-rw align-center-rw width-fixed-rw exclude-print-rw">': "ornament3",
    '<div class="pc-rw">': "ornament4",
    "</div>": "ornamentx",
}


def parse_text(line):
    tag = grab_tag(line)
    if tag in TAG_MAPPING:
        return (
            TAG_MAPPING[tag],
            "" if TAG_MAPPING[tag].startswith("ornament") else strip_tag(line),
        )
    else:
        raise ValueError("Unaccounted tag: " + str(tag))


def print_text(book):
    global SUBPART_NUMBER

    if book[0] == "body":
        return book[1]
    elif book[0] == "ornament":
        return "* * *"
    elif book[0] == "breakbody":
        return "<br/>\n\n" + book[1]
    elif book[0] == "subpart":
        SUBPART_NUMBER += 1
        return "# " + str(SUBPART_NUMBER)
    else:
        raise ValueError(f"Unknown type: {book[0]}")


def parse_lines(lines):
    result = []
    for line in lines:
        result.append(parse_text(line))
    return result


if __name__ == "__main__":
    main()
