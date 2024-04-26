import argparse
import itertools
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path, PurePosixPath

import colors
import cv2
import numpy as np
from argparse_color_formatter import ColorHelpFormatter
from Lib.config import (Book, Chapter, ImageInfo, ImagesConfig, Part,
                        parse_book_config, parse_image_config)
from Lib.project_dirs import common_dir
from PIL import Image

xelatex_default_windows = 'xelatex -interaction=batchmode -enable-installer -output-directory={OUTPUT_DIRECTORY} -job-name={JOB_NAME} {TEX_FILE}'
xelatex_default_linux = 'xelatex -interaction=batchmode -output-directory={OUTPUT_DIRECTORY} -jobname={JOB_NAME} {TEX_FILE}'
if sys.platform.startswith('win32'): # Windows
    xelatex_command_default = xelatex_default_windows
elif sys.platform.startswith('linux'): # Linux
    xelatex_command_default = xelatex_default_linux
else: # All others, currently the same default as Linux
    xelatex_command_default = xelatex_default_linux

def in_curlies(s):
    return "{" + str(s) + "}"

def env_path_prepend(s_old: str, *args) -> str:
    l = list(args)
    if s_old and not s_old.isspace():
        l.append(s_old)
    return os.pathsep.join(str(x) for x in l)

def format_text(text: str) -> str:  
    text = text.replace(r"<i>", r"\textit{")
    text = text.replace(r"</i>", r"}")
    text = text.replace(r"<em>", r"\textit{")
    text = text.replace(r"</em>", r"}")

    text = text.replace(r"<u>", r"\underline{")
    text = text.replace(r"</u>", r"}")

    text = text.replace(r"<b>", r"\textbf{")
    text = text.replace(r"</b>", r"}")    
    text = text.replace(r"<strong>", r"\textbf{")
    text = text.replace(r"</strong>", r"}") 
    
    text = re.sub(r"<br( )?(/)?>", r"\\", text)

    def transform_paragraph(p: str) -> str:
        p = p.strip()
        if p == "* * *":
            p = r"\icon"
        return p
    split_text = re.split(r"\r?\n\s*\n", text)
    transformed_text = (transform_paragraph(p) for p in split_text)
    filtered_text = list(filter(lambda x: x and not x.isspace(), transformed_text))
    for i in range(len(filtered_text)):
        if (filtered_text[i] == r"\icon" 
        and i + 1 < len(filtered_text) 
        and filtered_text[i + 1] != r"\icon"):
            filtered_text[i + 1] = r"\noindent" + "\n" + filtered_text[i + 1]

    text = "\n\n".join(filtered_text)

    text = text.replace("\n\n" + r"\\", "\n" + r"\\")
    
    m = re.search(r"<[^\r\n<>]+>", text)
    if m is not None:
        print(f"Warning: Possible unprocessed HTML tag `{m.group(0)}`. " +
            "If this is an error, processing for this tag needs to be" +
            "added in mid_to_tex.py:format_text")

    return text

def convert_part_text(part: Part, work_dir: Path, content_lines: list[str]):
    output_filename = work_dir / (part.base_filename() + ".tex")
    with open(part.text_filepath(), "r") as in_file:
        input_text = in_file.read()

    output_text = format_text(input_text)
    
    with open(output_filename, "w") as out_file:
        out_file.write(output_text)

    content_lines.append(fr"\insertPartText{in_curlies(output_filename.name)}")

def convert_part(part: Part, work_dir: Path, content_lines: list[str]):
    content_lines.append(fr"\beginPart{in_curlies(f'{part.number}. {part.title}')}")
    convert_part_text(part, work_dir, content_lines)

def convert_chapter(chapter: Chapter, work_dir: Path, content_lines: list[str]):
    part1 = chapter.parts[0]
    part_title_string = ""
    if part1.title is not None:
        part_title_string = f"[{part1.number}. {part1.title}]"

    content_lines.append(fr"\beginChapter{part_title_string}{in_curlies(chapter.title)}{in_curlies(chapter.subtitle)}")
    convert_part_text(part1, work_dir, content_lines)
    
    for part in itertools.islice(chapter.parts, 1, None):
        convert_part(part, work_dir, content_lines)

def image_latex_command(img_info: ImageInfo) -> str:
        image_path_string = str(PurePosixPath(img_info.relative_image_path().with_suffix(".png")))
        if (img_info.image_type == "double"):
            return rf"\insertDoubleImage{in_curlies(image_path_string)}"
        elif (img_info.image_type == "single"):
            return rf"\insertSingleImage{in_curlies(image_path_string)}"
        else:
            raise AssertionError(img_info.image_type)

def convert_book(book_config: Book, image_config: ImagesConfig, output_dir: Path, work_dir: Path, bleed = False, dont_print_images = False, xelatex_command_line: str = xelatex_command_default):   
    content_lines = []
    for img_info in image_config.insert_images.values():
        content_lines.append(image_latex_command(img_info))

    for chapter in book_config.chapters:
        img_info = image_config.chapter_images[str(chapter.number)]
        content_lines.append(image_latex_command(img_info))
        convert_chapter(chapter, work_dir, content_lines)

    content_text = "\n\n".join(content_lines)
    with open(work_dir / "content.tex", "w") as content_file:
        content_file.write(content_text)
    
    config_lines = []
    config_lines.append(r"\newcommand{\volumeNumberHeaderText}{Vol." + str(book_config.volume) + "}")
    if bleed:
        config_lines.append(r"\newcommand{\bleedSize}{0.125in}")
    if dont_print_images:
        config_lines.append(r"\newcommand{\dontPrintImages}{}")
    
    config_text = "\n".join(config_lines)
    with open(work_dir / "config.tex", "w") as config_file:
        config_file.write(config_text)
    
    intermediate_output_directory = work_dir / "CompilationDir"
    os.makedirs(intermediate_output_directory, exist_ok=True)
    output_stem = f"WorldEnd2 v{book_config.volume:02}"
    main_tex_file = common_dir() / "TeX" / "WorldEnd2_Common.tex"
    tex_inputs = env_path_prepend(os.environ.get("TEXINPUTS"), work_dir, ".")
    
    args = [
        arg.format(OUTPUT_DIRECTORY=intermediate_output_directory, JOB_NAME=output_stem, TEX_FILE=main_tex_file)
        for arg in shlex.split(xelatex_command_line)
    ]
    env = os.environ.copy()
    env["TEXINPUTS"] = tex_inputs
    print("==Starting xelatex==")
    subprocess.run(args=args, env=env, cwd=str(main_tex_file.parent))
    print("==Finished xelatex==")
    intermediate_output_file = intermediate_output_directory / (output_stem + ".pdf")
    final_output_file = output_dir / (output_stem + ".pdf")
    if intermediate_output_file.exists():
        shutil.move(intermediate_output_file, final_output_file)
    else:
        print("Error: No PDF file generated")
        
def generate_images(config: ImagesConfig, work_dir: Path, bleed: bool):
    for image_info in config.all_images_iter():
        input_path = image_info.absolute_image_path()
        output_path = (work_dir / image_info.relative_image_path()).with_suffix(".png")
        os.makedirs(output_path.parent, exist_ok=True)
        
        img = cv2.imread(str(input_path)) 
        print(np.shape(img))
        
        l, r, t, b = image_info.padding_lrtb(bleed)
        print((l, r, t, b))
        mask = np.ones((img.shape[0], img.shape[1]), dtype=np.uint8) * 255
        mask = crop_and_pad_mat(mask, [(t, b), (l, r)])
        mask = 255 - mask
        img = crop_and_pad_mat(img, [(t, b), (l, r)])
        print(img.dtype)
        print(img.shape)

        cv2.setRNGSeed(42) # For consistent generation between runs
        img = cv2.inpaint(img, mask, 2, cv2.INPAINT_TELEA)
        
        print(output_path)
        cv2.imwrite(str(output_path), img)
    
def crop_and_pad_mat(mat, pad_crop_values):
    pad_crop_values = tuple(pad_crop_values) + (((0, 0),) * (len(mat.shape) - len(pad_crop_values)))
    
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
                        prog='md_to_tex',
                        description='Converts the input .md files to .tex files',
                        formatter_class=ColorHelpFormatter)
    
    parser.add_argument("input_dir")
    parser.add_argument("output_dir")
    parser.add_argument('--bleed', '-b', action='store_true', help="Add bleed to the output file, for printing")
    parser.add_argument('--skip-images', '-s', action='store_true', help="Skip generating the images. Will use previously generated images. Speeds up execution")
    parser.add_argument('--dont-print-images', '-d', action='store_true', help="Don't print the images to the PDF. Greatly speeds up execution.")
    parser.add_argument('--xelatex-command-line', '-x',
                        default = xelatex_command_default,
                        help=f"Allow overriding the command used to call xelatex.\n This will be formatted with str.format, with keyword arguments OUTPUT_DIRECTORY, JOB_NAME, and TEX_FILE. The default is `{colors.faint(xelatex_default_windows)}` on Windows, and `{colors.faint(xelatex_default_linux)}` on Linux and other systems")
    
    args = parser.parse_args()

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
    if not args.skip_images:
        generate_images(images_config, work_dir, args.bleed)
        time.sleep(5)
    
    convert_book(book_config, images_config, output_dir, work_dir, args.bleed, args.dont_print_images, args.xelatex_command_line)

if __name__ == '__main__':
    main()
