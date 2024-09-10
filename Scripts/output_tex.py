import argparse
import itertools
import logging
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath

import colorlog
import colors
import cv2
import numpy as np
import pint
import regex
from argparse_color_formatter import ColorHelpFormatter
from Lib.config import (
    Book,
    Chapter,
    ImageInfo,
    ImagesConfig,
    Part,
    TOCImage,
    parse_book_config,
    parse_image_config,
)
from Lib.project_dirs import common_dir
from PIL import Image, ImageDraw, ImageFont
from pylatexenc.latexencode import (
    RULE_REGEX,
    UnicodeToLatexConversionRule,
    UnicodeToLatexEncoder,
)

formatter = colorlog.ColoredFormatter(
    "%(log_color)s%(levelname)s: %(message)s",
    log_colors={
        "DEBUG": "cyan",
        "INFO": "green",
        "WARNING": "yellow",
        "ERROR": "red",
        "CRITICAL": "bold_red",
    },
)

handler = logging.StreamHandler()
handler.setFormatter(formatter)

logger = logging.getLogger(__name__)
logger.addHandler(handler)
logger.setLevel(logging.INFO)

ureg = pint.UnitRegistry()

xelatex_default_miktex = "xelatex -interaction={MODE} -enable-installer -output-directory={OUTPUT_DIRECTORY} -job-name={JOB_NAME} {TEX_FILE}"
xelatex_default_texlive = "xelatex -interaction={MODE} -output-directory={OUTPUT_DIRECTORY} -jobname={JOB_NAME} {TEX_FILE}"


def get_xelatex_command():
    try:
        xelatex_version = subprocess.check_output(
            ["xelatex", "--version"], stderr=subprocess.STDOUT, text=True
        )

        if "MiKTeX" in xelatex_version:
            logger.debug("MiKTeX xelatex detected")
            return xelatex_default_miktex
        elif "TeX Live" in xelatex_version:
            logger.debug("TeX Live xelatex detected")
            return xelatex_default_texlive
        else:  # All others, currently the same default as for Tex Live
            logger.debug("Unknown TeX Distribution - Defaulting to TeX Live")
            return xelatex_default_texlive
    except Exception as e:
        logger.critical(
            f"An error occurred while trying to detect the TeX distribution: {e}"
        )
        sys.exit(1)


def in_curlies(s):
    return "{" + str(s) + "}"


def length_to_inches(length: str) -> float:
    # We check it before since you can't make a Quantity without a unit,
    # and we check after since you can't convert a length without a unit.
    if not isinstance(length, str):
        logger.error(f"Invalid length `{length}`. Perhaps you are missing a unit?")
        sys.exit(1)
    quantity = ureg(length)
    if isinstance(quantity, (int, float)):
        logger.error(f"Invalid length `{quantity}`. Perhaps you are missing a unit?")
        sys.exit(1)
    return quantity.to("inch").magnitude


def env_path_prepend(s_old: str, *args) -> str:
    l = list(args)
    if s_old and not s_old.isspace():
        l.append(s_old)
    else:
        l.append("")  # In case TEXINPUTS is unset, retain the last `:`
    return os.pathsep.join(str(x) for x in l)


def get_latex_converter() -> UnicodeToLatexEncoder:
    if not hasattr(get_latex_converter, "converter"):
        # Check whether this character is preceded/followed by a word character
        # (\w), possibly with some HTML tags in between
        after_wchar = r"(?<=\w(?:<[^<>]+>)*)"
        before_wchar = r"(?=(?:<[^<>]+>)*\w)"

        # Command to run at the beginning of the span, and command to run
        # at the end. Use \bgroup and \egroup instead of { and } if you need to
        # enclose something between the start and end command
        def span_replacement(start_command, end_command=""):
            return (
                r"\\begin{SpanEnv}\\renewcommand{\\SpanEnvClose}{"
                + end_command
                + "}"
                + start_command
            )

        regex_replacements = {
            rf"{after_wchar}(?:(?:\.\.\.)|(?:…)){before_wchar}": r"{\\EllipsisSplittable}",
            r"(?:(?:\.\.\.)|(?:…))": r"{\\Ellipsis}",
            rf"</span>": r"\\end{SpanEnv}",
            rf'<span class="v-centered-page">': span_replacement(
                r"\\newpage\\hspace{0pt}\\vfill ", r" \\vfill\\hspace{0pt}\\newpage"
            ),
            rf'<span class="page-break"[ ]?/>': r"\\newpage",
            r"<i>": r"\\textit{",
            r"</i>": r"}",
            r"<em>": r"\\textit{",
            r"</em>": r"}",
            r"<u>": r"\\ul{",
            r"</u>": r"}",
            r"<code>": r"\\texttt{",
            r"</code>": r"}",
            r"<b>": r"\\textbf{",
            r"</b>": r"}",
            r"<strong>": r"\\textbf{",
            r"</strong>": r"}",
            r"<br(?:[ ]?/)?>": r"\\",
        }

        conversion_rules = [
            UnicodeToLatexConversionRule(
                RULE_REGEX,
                [(regex.compile(k), v) for k, v in regex_replacements.items()],
                replacement_latex_protection="none",
            ),
            "defaults",
        ]
        get_latex_converter.converter = UnicodeToLatexEncoder(
            conversion_rules=conversion_rules, replacement_latex_protection="braces-all"
        )

    return get_latex_converter.converter


def format_text(text: str) -> str:
    converted_text = get_latex_converter().unicode_to_latex(text)

    def transform_paragraph(p: str) -> str:
        p = p.strip()
        if p == "* * *":
            p = r"\icon"
        return p

    split_text = regex.split(r"\r?\n\s*\n", converted_text)
    transformed_text = (transform_paragraph(p) for p in split_text)
    filtered_text = list(filter(lambda x: x and not x.isspace(), transformed_text))
    for i in range(len(filtered_text)):
        if (
            filtered_text[i] == r"\icon"
            and i + 1 < len(filtered_text)
            and filtered_text[i + 1] != r"\icon"
        ):
            filtered_text[i + 1] = r"\noindent" + "\n" + filtered_text[i + 1]

    text = "\n\n".join(filtered_text)

    text = text.replace("\n\n" + r"\\", "\n" + r"\\")

    m = regex.search(r"<[^\r\n<>]+>", text)
    if m is not None:
        logger.warning(
            f"Possible unprocessed HTML tag `{m.group(0)}`. "
            + "If this is an error, processing for this tag needs to be "
            + "added in `mid_to_tex.py:format_text`"
        )

    return text


def convert_part_text(part: Part, work_dir: Path, content_lines: list[str]):
    output_filename = work_dir / (part.base_filename() + ".tex")
    input_text = part.text_filepath().read_text()

    output_text = format_text(input_text)

    output_filename.write_text(output_text)

    content_lines.append(rf"\insertPartText{in_curlies(output_filename.name)}")


def convert_part(part: Part, work_dir: Path, content_lines: list[str]):
    content_lines.append(rf"\beginPart{in_curlies(f'{part.number}. {part.title}')}")
    convert_part_text(part, work_dir, content_lines)


def convert_chapter(chapter: Chapter, work_dir: Path, content_lines: list[str]):
    part1 = chapter.parts[0]
    part_title_string = ""
    if part1.title is not None:
        part_title_string = f"[{part1.number}. {part1.title}]"

    content_lines.append(
        rf"\beginChapter{part_title_string}{in_curlies(chapter.title)}{in_curlies(chapter.subtitle)}"
    )
    convert_part_text(part1, work_dir, content_lines)

    for part in itertools.islice(chapter.parts, 1, None):
        convert_part(part, work_dir, content_lines)


def image_latex_command(img_info: ImageInfo, no_cover: bool) -> str:
    image_path_string = str(
        PurePosixPath(img_info.relative_image_path().with_suffix(".png"))
    )
    if img_info.image_type == "double" or img_info.image_type == "toc":
        return rf"\insertDoubleImage{in_curlies(image_path_string)}"
    elif (
        img_info.image_type == "single"
        or img_info.image_type == "titlepage"
        or img_info.image_type == "filler"
    ):
        return rf"\insertSingleImage{in_curlies(image_path_string)}"
    elif img_info.image_type == "cover":
        return (
            ""
            if no_cover
            else (
                rf"\insertSingleImage{in_curlies(image_path_string)}" + "\n\n"
                r"\newpage\vspace*{\fill}\thispagestyle{empty}\vspace*{\fill}\newpage"
            )
        )
    else:
        raise AssertionError(img_info.image_type)


def convert_book(
    book_config: Book,
    image_config: ImagesConfig,
    output_dir: Path,
    work_dir: Path,
    bleed_size=0.0,
    dont_print_images=False,
    skip_generate_images=False,
    xelatex_command_line: str = xelatex_default_texlive,
    no_cover=False,
    gutter_size=0.0,
):
    content_lines = []
    for img_info in image_config.insert_images.values():
        content_lines.append(image_latex_command(img_info, no_cover))

    for chapter in book_config.chapters:
        img_info = image_config.chapter_images[str(chapter.number)]
        content_lines.append(image_latex_command(img_info, no_cover))
        convert_chapter(chapter, work_dir, content_lines)

    content_text = "\n\n".join(content_lines)
    (work_dir / "content.tex").write_text(content_text)

    config_lines = []
    config_lines.append(
        r"\newcommand{\volumeNumberHeaderText}{Vol." + str(book_config.volume) + "}"
    )
    config_lines.append(
        rf"\newcommand{{\bleedSize}}{in_curlies((str(bleed_size) + 'in'))}"
    )
    config_lines.append(
        rf"\newcommand{{\gutterSize}}{in_curlies(str(gutter_size) + 'in')}"
    )
    if dont_print_images:
        config_lines.append(r"\providecommand{\dontPrintImages}{}")

    config_text = "\n".join(config_lines)
    (work_dir / "config.tex").write_text(config_text)

    intermediate_output_directory = work_dir / "CompilationDir"
    os.makedirs(intermediate_output_directory, exist_ok=True)
    output_stem = f"WorldEnd2_v{book_config.volume:02}"
    main_tex_file = common_dir() / "TeX" / "WorldEnd2_Common.tex"
    tex_inputs = env_path_prepend(os.environ.get("TEXINPUTS"), work_dir, ".")
    tex_inputs_no_images = env_path_prepend(
        tex_inputs, common_dir() / "TeX" / "Optional" / "NoImages"
    )

    page_numbers_file = (
        intermediate_output_directory / f"{output_stem}.page-numbers.txt"
    )

    args = [
        arg.format(
            MODE="nonstopmode" if logger.isEnabledFor(logging.DEBUG) else "batchmode",
            OUTPUT_DIRECTORY=intermediate_output_directory,
            JOB_NAME=output_stem,
            TEX_FILE=main_tex_file,
        )
        for arg in shlex.split(xelatex_command_line)
    ]

    logger.debug(" ".join(args))

    env = os.environ.copy()

    # We do two passes for two reasons: 1) It resolves an issue with images not
    # being centered correctly the first time we compile, and 2) In the future,
    # we're going to implement auto-generation of the table of contents with
    # correct page numbers, which requires a first pass to actually determine
    # the page numbers.
    # The first pass doesn't take very long since we don't print the images.

    logger.info("==Starting xelatex (first pass)==")
    env["TEXINPUTS"] = tex_inputs_no_images
    subprocess.run(args=args, env=env, cwd=str(main_tex_file.parent))

    if not skip_generate_images:
        page_numbers = get_page_numbers(page_numbers_file)
        generate_images(image_config, work_dir, page_numbers, bleed_size)

    if not dont_print_images:
        logger.info("==Starting xelatex (second pass)==")
        env["TEXINPUTS"] = tex_inputs
        subprocess.run(args=args, env=env, cwd=str(main_tex_file.parent))

    logger.info("==Finished xelatex==")
    intermediate_output_file = intermediate_output_directory / (output_stem + ".pdf")
    final_output_file = output_dir / (output_stem + ".pdf")
    if intermediate_output_file.exists():
        shutil.move(intermediate_output_file, final_output_file)
    else:
        logger.error("No PDF file generated")


def get_page_numbers(file_path: Path):
    page_numbers = []
    content = file_path.read_text()
    for line in content.splitlines():
        match = regex.match(r"ChapterPageNumber:\s*(\d+)", line)
        if match:
            page_numbers.append(int(match.group(1)))
        else:
            # Basic error handling as a sanity check
            raise ValueError(f"Error: Invalid line in page-numbers file: `{line}`")
    return page_numbers


def draw_page_numbers(page_numbers: list[int], toc_path: Path, output_path: Path):
    padded_numbers = [str(num - 3).zfill(3) for num in page_numbers]

    image = Image.open(toc_path)

    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(
        common_dir()
        / "TeX"
        / "Fonts"
        / "HomepageBaukasten-Book"
        / "HomepageBaukasten-Book-Modified.ttf",
        size=42,
    )

    text_color = (0, 0, 0)

    offshift_x = 1301
    offshift_y = 246

    position_x = 0
    position_y = 0

    for number in padded_numbers:
        text = "P\u2009.\u2009" + number

        text_position = (
            59.52 + offshift_x * position_x,
            521.82 + offshift_y * position_y,
        )

        position_y += 1
        if position_y == 3:
            position_y = -1
            position_x = 1

        draw.text(text_position, text, fill=text_color, font=font)

    image.save(output_path)

    image.close()


def generate_images(
    config: ImagesConfig, work_dir: Path, page_numbers: list[int], bleed_size: float
):
    for image_info in config.all_images_iter():
        input_path = image_info.absolute_image_path()
        output_path = (work_dir / image_info.relative_image_path()).with_suffix(".png")
        os.makedirs(output_path.parent, exist_ok=True)

        if isinstance(image_info, TOCImage):
            draw_page_numbers(page_numbers, input_path, output_path)
            input_path = output_path

        img = cv2.imread(str(input_path))
        logger.debug(np.shape(img))

        l, r, t, b = image_info.padding_lrtb(bleed_size)
        logger.debug((l, r, t, b))
        mask = np.ones((img.shape[0], img.shape[1]), dtype=np.uint8) * 255
        mask = crop_and_pad_mat(mask, [(t, b), (l, r)])
        mask = 255 - mask
        img = crop_and_pad_mat(img, [(t, b), (l, r)])
        logger.debug(img.dtype)
        logger.debug(img.shape)

        cv2.setRNGSeed(42)  # For consistent generation between runs
        img = cv2.inpaint(img, mask, 2, cv2.INPAINT_TELEA)

        logger.debug(output_path)
        cv2.imwrite(str(output_path), img)


def crop_and_pad_mat(mat, pad_crop_values):
    pad_crop_values = tuple(pad_crop_values) + (
        ((0, 0),) * (len(mat.shape) - len(pad_crop_values))
    )

    pad_values = tuple((max(0, a), max(0, b)) for a, b in pad_crop_values)
    crop_values = tuple((max(0, -a), max(0, -b)) for a, b in pad_crop_values)

    mat = np.pad(mat, pad_values)
    mat = crop_mat(mat, crop_values)
    return mat


def crop_mat(mat, crop_values):
    crop_values = tuple(crop_values) + (((0, 0),) * (len(mat.shape) - len(crop_values)))
    slices = tuple(slice(start or None, -end or None) for start, end in crop_values)
    ret = mat.__getitem__(slices)
    return ret


def cv2_to_pil(img, from_space="BGR", to_space="RGB"):
    flag = getattr(cv2, f"COLOR_{from_space}2{to_space}")
    converted = cv2.cvtColor(img, flag)
    return Image.fromarray(converted, to_space)


def main():
    parser = argparse.ArgumentParser(
        prog="md_to_tex",
        description="Converts the input .md files to .tex files.",
        formatter_class=ColorHelpFormatter,
        add_help=False,
    )

    parser.add_argument("input_dir")
    parser.add_argument("output_dir")
    parser.add_argument(
        "-h",
        "--help",
        action="help",
        default=argparse.SUPPRESS,
        help="Show this help message and exit.",
    )
    parser.add_argument(
        "-b",
        "--bleed-size",
        default="0.0in",
        type=str,
        help="Specify bleed size. Recommended size is 0.125in, if printing.",
    )
    parser.add_argument(
        "-g",
        "--gutter-size",
        default="0.0in",
        type=str,
        help="Specify gutter size. Recommended size is 0.15in, if printing.",
    )
    parser.add_argument(
        "-n",
        "--no-cover",
        action="store_true",
        help="Do not include cover in output file.",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Be verbose.")
    parser.add_argument(
        "-s",
        "--skip-images",
        action="store_true",
        help="Skip generating the images. Will use previously generated images. Speeds up execution.",
    )
    parser.add_argument(
        "-d",
        "--dont-print-images",
        action="store_true",
        help="Don't print the images to the PDF. Greatly speeds up execution.",
    )
    parser.add_argument(
        "-x",
        "--xelatex-command-line",
        type=str,
        help=f"Allow overriding the command used to call xelatex. This will be formatted with `{colors.faint('str.format')}`, with keyword arguments MODE (optional to preserve verbosity), OUTPUT_DIRECTORY, JOB_NAME, and TEX_FILE. The default is `{colors.faint(xelatex_default_miktex)}` for MiKTeX, and `{colors.faint(xelatex_default_texlive)}` for TeX Live and other TeX distributions.",
    )

    # Custom action for `--print-mode`
    class PrintMode(argparse.Action):
        def __call__(self, parser, namespace, values, option_string=None):
            setattr(namespace, "bleed_size", "0.125in")
            setattr(namespace, "gutter_size", "0.15in")
            setattr(namespace, "no_cover", True)

    parser.add_argument(
        "-p",
        "--print-mode",
        action=PrintMode,
        nargs=0,
        help=f"Activate print mode, short for `{colors.faint('-b 0.125in -g 0.15in -n')}`",
    )

    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    xelatex_command = args.xelatex_command_line or get_xelatex_command()

    input_dir = Path(args.input_dir).absolute()

    book_config = parse_book_config(input_dir)
    if book_config is None:
        return

    output_dir = Path(args.output_dir).absolute()
    os.makedirs(output_dir, exist_ok=True)
    output_dir = output_dir.resolve()

    work_dir = output_dir / "WorkDir" / "TeX"
    os.makedirs(work_dir, exist_ok=True)
    work_dir = work_dir.resolve()

    images_config = parse_image_config(book_config.directory / "Images")

    result = convert_book(
        book_config,
        images_config,
        output_dir,
        work_dir,
        length_to_inches(args.bleed_size),
        args.dont_print_images,
        args.skip_images,
        xelatex_command,
        args.no_cover,
        length_to_inches(args.gutter_size),
    )


if __name__ == "__main__":
    main()
