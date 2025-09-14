import argparse
import logging
import os
import shutil

import string
import zipfile

from pathlib import Path

import colorlog

from PIL import Image

from argparse_color_formatter import ColorHelpFormatter
from Lib.config import (
    Book,
    ImagesConfig,
    SingleImage,
    parse_book_config,
    parse_image_config,
)
from Lib.project_dirs import common_dir
from Lib.epub_generation import EPUBGenerator

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


def convert_book(
    generator: EPUBGenerator,
    book_config: Book,
    image_config: ImagesConfig,
    output_dir: Path,
    work_dir: Path,
):
    text_output_directory = work_dir / "OEBPS"
    images_output_directory = work_dir / "OEBPS" / "images"
    if os.path.exists(work_dir):
        shutil.rmtree(work_dir)
    shutil.copytree(common_dir() / "ePub", work_dir)
    output_stem = f"WorldEnd2_v{book_config.volume:02}"

    output_file = output_dir / (output_stem + ".epub")
    process_images(image_config, images_output_directory, book_config.isbn)
    convert_md_to_html(generator, book_config, image_config, text_output_directory)
    logger.info("==Zipping work directory into EPUB==")
    convert_zip_to_epub(output_file, work_dir)
    logger.info(f"==Output file at {output_file}==")


def resize_image(input_file: Path, output_file: Path, scale_height=True):
    img = Image.open(input_file)

    if img.mode == "RGBA":
        img = img.convert("RGB")

    width, height = img.size

    if scale_height:
        ratio = 1800 / height if height > 1800 else 1
    else:
        ratio = 1800 / width if width > 1800 else 1

    new_width = int(width * ratio)
    new_height = int(height * ratio)
    img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
    img.save(output_file, quality=100, subsampling=0)
    logger.debug(
        f"{Path(input_file.parent.name) / input_file.name} ({width}x{height} => {new_width}x{new_height})"
    )


def convert_zip_to_epub(output_file: Path, intermediate_output_directory: Path):
    with zipfile.ZipFile(output_file, "w", compression=zipfile.ZIP_STORED) as epub:
        os.chdir(intermediate_output_directory)

        epub.write("mimetype", arcname="mimetype", compress_type=zipfile.ZIP_STORED)

        for root, dirs, files in os.walk("META-INF"):
            for file in files:
                if not file.endswith(".DS_Store"):
                    file_path = Path(root) / file
                    epub.write(file_path)
                    logger.debug(file_path)

        for root, dirs, files in os.walk("OEBPS"):
            for file in files:
                if not file.endswith(".DS_Store"):
                    file_path = Path(root) / file
                    epub.write(file_path)
                    logger.debug(file_path)

        epub.close()


def convert_md_to_html(
    generator: EPUBGenerator,
    book_config: Book,
    images_config: ImagesConfig,
    output_dir: Path,
):
    combined_chapters = {
        chapter.number: generator.process_chapter(chapter.number)
        for chapter in book_config.chapters
    }

    letters = iter(string.ascii_lowercase)

    for chapter_number, combined_content in combined_chapters.items():
        (output_dir / f"chapter{chapter_number:03}.xhtml").write_text(
            generator.generate_chapter_pages(chapter_number)
        )
        for section in combined_content:
            letter = next(letters)
            (output_dir / f"chapter{chapter_number:03}{letter}.xhtml").write_text(
                "\n".join(section)
            )

        letters = iter(string.ascii_lowercase)

    for insert_number, insert in enumerate(
        images_config.non_filler_insert_images(), start=1
    ):
        (output_dir / f"insert{insert_number:03}.xhtml").write_text(
            generator.generate_insert_pages(insert_number)
        )

    (output_dir / "cover.xhtml").write_text(generator.generate_cover_page())
    (output_dir / "nav.xhtml").write_text(generator.generate_nav_xhtml())
    (output_dir / "titlepage.xhtml").write_text(generator.generate_title_page())
    (output_dir / "toc.xhtml").write_text(generator.generate_toc_xhtml())
    (output_dir / "toc.ncx").write_text(generator.generate_toc_ncx())
    (output_dir / "package.opf").write_text(
        generator.generate_package_opf(combined_chapters)
    )


def process_images(images_config: ImagesConfig, output_dir: Path, isbn: str):
    os.makedirs(output_dir, exist_ok=True)

    logger.info("==Resizing Images==")

    if images_config.front_cover:
        img_info = images_config.front_cover
        image_path = img_info.absolute_image_path()
        output_path = output_dir / f"{isbn}.jpg"
        resize_image(image_path, output_path, isinstance(img_info, SingleImage))

    for insert_image_number, img_info in enumerate(
        images_config.non_filler_insert_images(), start=1
    ):
        image_path = img_info.absolute_image_path()
        output_path = output_dir / f"Art_insert{insert_image_number:03}.jpg"
        resize_image(image_path, output_path, isinstance(img_info, SingleImage))

    if images_config.titlepage:
        img_info = images_config.titlepage
        image_path = img_info.absolute_image_path()
        output_path = output_dir / "Art_tit.jpg"
        resize_image(image_path, output_path, isinstance(img_info, SingleImage))

    for chapter_number, img_info in images_config.chapter_images.items():
        image_path = img_info.absolute_image_path()
        output_path = output_dir / f"Art_chapter{chapter_number:03}.jpg"
        resize_image(image_path, output_path, isinstance(img_info, SingleImage))


def main():
    parser = argparse.ArgumentParser(
        prog="md_to_epub",
        description="Converts the input .md files to .epub files.",
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
    parser.add_argument("-v", "--verbose", action="store_true", help="Be verbose.")

    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    input_dir = Path(args.input_dir).absolute()

    book_config = parse_book_config(input_dir)
    if book_config is None:
        return

    output_dir = Path(args.output_dir).absolute()
    os.makedirs(output_dir, exist_ok=True)
    output_dir = output_dir.resolve()

    work_dir = output_dir / "WorkDir" / "ePub"
    os.makedirs(work_dir, exist_ok=True)
    work_dir = work_dir.resolve()

    images_config = parse_image_config(book_config.directory / "Images")

    generator = EPUBGenerator.from_book_config(book_config, images_config)

    convert_book(generator, book_config, images_config, output_dir, work_dir)


if __name__ == "__main__":
    main()
