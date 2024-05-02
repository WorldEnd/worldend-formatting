import itertools
import math
import re
from abc import ABC, abstractmethod
from collections import OrderedDict
from pathlib import Path
from typing import Iterator, Literal

try:
    from typing import override
except ImportError:
    def override(f): 
        return f

import numpy as np
import oyaml as yaml
from numpy.typing import NDArray
from PIL import Image

from .debug_printable import DebugPrintable


class Book(DebugPrintable):
    chapters: "list[Chapter]"
    directory: Path
    volume: int
    
    # @property
    # def parts(self):
    #     return itertools.chain(ch.parts for ch in self.chapters)

    @staticmethod
    def from_file(config_file):
        config_file = Path(config_file)
        if not config_file.exists():
            print(f"Error: Config file does not exist: '{config_file}'")
            return None

        with open(config_file, "r") as f:
            data = yaml.safe_load(f)
        book = Book()
        book.parse_yaml(data)
        book.directory = config_file.parent.resolve()
        return book

    def parse_yaml(self, node: dict):
        self.volume = node["volume_number"]
        self.chapters = []
        for i, c in enumerate(node["chapters"], start=1):
            chapter = Chapter()
            chapter.parent = self
            chapter.number = i
            chapter.parse_yaml(c)
            self.chapters.append(chapter)
            
    def text_directory(self):
        return self.directory / "Text"

class Chapter(DebugPrintable):
    title: str
    subtitle: str
    parts: "list[Part]"
    number: int
    parent: Book
    
    def parse_yaml(self, node: dict):
        self.title = node["title"]
        self.subtitle = node["subtitle"]
        self.parts = []
        for i, p in enumerate(node["parts"], start=1):
            part = Part()
            part.parent = self
            part.number = i
            part.parse_yaml(p)
            self.parts.append(part)
    
    def base_filename(self):
        return str(self.number)
    
    def is_single_part_chapter(self):
        return len(self.parts) == 1

class Part(DebugPrintable):
    title: str | None
    parent: Chapter
    number: int
    
    @property
    def grandparent(self) -> Book:
        return self.parent.parent
    
    def parse_yaml(self, node: dict):
        self.title = node["title"]
    
    def base_filename(self):
        if self.parent.is_single_part_chapter():
            return self.parent.base_filename()
        else:
            return f"{self.parent.base_filename()}.{self.number}"

    def text_filepath(self):
        return self.grandparent.text_directory() / (self.base_filename() + ".md")

def parse_book_config(directory):
    directory = Path(directory)
    config_file = directory / "config.yaml"
    
    if not directory.exists():
        print(f"Error: Input directory does not exist: '{directory}'")
        return None
    
    book = Book.from_file(config_file)
    
    return book

class ImagesConfig(DebugPrintable):
    insert_images: "OrderedDict[str, ImageInfo]"
    chapter_images: "OrderedDict[str, ImageInfo]"
    directory: Path

    @staticmethod
    def from_file(config_file):
        config_file = Path(config_file)
        if not config_file.exists():
            print(f"Error: Config file does not exist: '{config_file}'")
            return None

        with open(config_file, "r") as f:
            data = yaml.safe_load(f)
        config = ImagesConfig()
        config.parse_yaml(data)
        config.directory = config_file.parent.resolve()
        return config

    def parse_yaml(self, node: dict):
        self.insert_images = OrderedDict()
        for k, v in node["insert"].items():
            img = self.image_from_yaml(v, k, "Insert")
            self.insert_images[img.image_title()] = img
            
        self.chapter_images = OrderedDict()
        for k, v in node["chapter"].items():
            img = self.image_from_yaml(v, k, "Chapter")
            self.chapter_images[img.image_title()] = img
            
    def image_from_yaml(self, node, filename, subdirectory) -> "ImageInfo":
        match node["image_type"]:
            case "single":
                image = SingleImage()
            case "double":
                image = DoubleImage()
            case "toc":
                image = TOCImage()
            case _:
                raise ValueError(f"Unexpected image type `{node['image_type']}`")
        image.parent = self
        image._filename = filename
        image._subdir = subdirectory
        image.parse_yaml(node)
        return image
    
    def all_images_iter(self) -> Iterator["ImageInfo"]:
        return itertools.chain(self.insert_images.values(), self.chapter_images.values())

PAPER_W_IN = 5.5
PAPER_H_IN = 8.25
BLEED_IN = 0.125

class ImageInfo(ABC, DebugPrintable):
    image_type: Literal['single', 'double']
    height_inches: float
    offset_px: tuple[int, int]

    parent: ImagesConfig
    
    _filename: str
    _subdir: str
    
    hI: int = 0
    vI: int = 1

    def length_to_inches(self, length: str) -> float:
        m = re.match(r"^(\d+(?:\.\d+)?((?:in)|(?:cm)|(?:px)))$", length)
        if m is None:
            raise ValueError(f"Could not match `{length}` as a length")
        value = float(m[1])
        match m[2]:
            case "in":
                return value
            case "cm":
                return value / 2.54 # cm per in
            case "px":
                if (int(value) - value) != 0:
                    raise ValueError(f"Non whole-number of pixels `{value}`")
                return value / self.px_per_in

    def length_to_px(self, length: str) -> int:
        m = re.match(r"^(\d+(?:\.\d+)?((?:in)|(?:cm)|(?:px)))$", length)
        if m is None:
            raise ValueError(f"Could not match `{length}` as a length")
        value = float(m[1])
        match m[2]:
            case "in":
                return round(value * self.px_per_in)
            case "cm":
                return round(value * self.px_per_in / 2.54)
            case "px":
                if (int(value) - value) != 0:
                    raise ValueError(f"Non whole-number of pixels `{value}`")
                return int(value)
    
    def parse_yaml(self, node: dict):
        self.image_type = node["image_type"]
        
        self.height_inches = PAPER_H_IN
        if "height_inches" in node:
            self.height_inches = self.length_to_inches(node["height_inches"])

        self.offset_px = (0, 0)
        if "offset" in node:
            offset_list = node["offset"]
            if len(offset_list) != 2:
                raise ValueError(offset_list)
            self.offset_px = tuple(self.length_to_px(offset) for offset in offset_list)

    @abstractmethod
    def canvas_size_px(self, bleed: bool) -> tuple[int, int]:
        pass
    
    def image_title(self) -> str:
        return Path(self._filename).stem
    
    def image_filename(self) -> str:
        return self._filename

    def relative_image_path(self) -> Path:
        return Path(self._subdir, self._filename)
    
    def absolute_image_path(self) -> Path:
        return self.parent.directory / self.relative_image_path()
    
    def padding_lrtb(self, bleed: bool) -> tuple[int, int, int, int]:
        canvas_w, canvas_h = self.canvas_size_px(bleed)
        img_w, img_h = self.size_px
        offset_w, offset_h = self.offset_px
        
        assert ((canvas_w - img_w) % 2 == 0), f"({canvas_w}, {img_w})"
        assert ((canvas_h - img_h) % 2 == 0), f"({canvas_h}, {img_h})"
        
        base_padding_w = (canvas_w - img_w) // 2
        base_padding_h = (canvas_h - img_h) // 2
        
        left = base_padding_w + offset_w
        right = base_padding_w - offset_w
        top = base_padding_h + offset_h
        bottom = base_padding_h - offset_h
        
        return left, right, top, bottom
        
    @property
    def size_px(self):
        if not hasattr(self, "_size_px") or self._size_px is None:
            im = Image.open(self.absolute_image_path())
            self._size_px = im.size
        return self._size_px

    @property
    def width_px(self) -> int:
        return self.size_px[0]
    
    @property
    def height_px(self) -> int:
        return self.size_px[1]

    @property
    def px_per_in(self) -> float:
        return self.height_px / self.height_inches

class SingleImage(ImageInfo):    
    @override
    def canvas_size_px(self, bleed: bool) -> tuple[int, int]:
        return _canvas_size_px_helper(bleed, False, self.px_per_in,
                                      self.width_px, self.height_px)

class DoubleImage(ImageInfo):
    overlap_px: int

    @override
    def parse_yaml(self, node: dict):
        super().parse_yaml(node)
        self.overlap_px = 0
        if "overlap" in node:
            self.overlap_px = self.length_to_px(node["overlap"])

    @override
    def canvas_size_px(self, bleed: bool) -> tuple[int, int]:
        return _canvas_size_px_helper(bleed, True, self.px_per_in, self.width_px, 
                                      self.height_px, self.overlap_px)

class TOCImage(DoubleImage):
    pass

def _canvas_size_px_helper(bleed: bool, is_two_page: bool, px_per_in: float, width_px: int, height_px: int, overlap_px: int = 0) -> tuple[int, int]:
    bleed_in = BLEED_IN if bleed else 0
    if is_two_page:
        base_page_size_in = np.array([PAPER_W_IN * 2., PAPER_H_IN])
    else: 
        base_page_size_in = np.array([PAPER_W_IN, PAPER_H_IN])
    full_page_size_in = base_page_size_in + (2 * bleed_in)
    full_page_size_px = full_page_size_in * px_per_in
    
    # We round the canvas size down, so that the image is comparatively
    # larger, and thus we never expose blank space on properly-sized images
    # We may reduce padding even more to ensure we can center exactly
    if is_two_page:
        # We also subtract from the width to overlap the images for two page
        width = math.floor(full_page_size_px[0] - overlap_px)
    else:
        width = math.floor(full_page_size_px[0])
    if (width - width_px) % 2 != 0:
        width = width - 1
    height = math.floor(full_page_size_px[1])
    if (height - height_px) % 2 != 0:
        height = height - 1

    if not is_two_page:
        # Since we scale the image based on the height, we make the height 
        # slightly smaller if needed for the width to cover the page
        if (width / height) < (PAPER_W_IN / PAPER_H_IN):
            height -= 2
        assert (width / height) >= (PAPER_W_IN / PAPER_H_IN), f"{(width, height)}"
    
    return width, height

def parse_image_config(directory):
    directory = Path(directory)
    config_file = directory / "config.yaml"
    
    if not directory.exists():
        print(f"Error: Input directory does not exist: '{directory}'")
        return None
    
    config = ImagesConfig.from_file(config_file)
    
    return config
