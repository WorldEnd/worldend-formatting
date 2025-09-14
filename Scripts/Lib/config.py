import itertools
import math
import pint
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
from PIL import Image

from .debug_printable import DebugPrintable


class Book(DebugPrintable):
    chapters: "list[Chapter]"
    directory: Path
    volume: int
    isbn: str
    publication_year: int

    # @property
    # def parts(self):
    #     return itertools.chain(ch.parts for ch in self.chapters)

    @staticmethod
    def from_file(config_file: str):
        config_file = Path(config_file)
        if not config_file.exists():
            print(f"Error: Config file does not exist: '{config_file}'")
            return None

        data = yaml.safe_load(config_file.read_text())
        book = Book()
        book.parse_yaml(data)
        book.directory = config_file.parent.resolve()
        return book

    def parse_yaml(self, node: dict):
        self.volume = node["volume_number"]
        self.isbn = node["isbn"]
        self.publication_year = node["publication_year"]
        self.chapters = []
        for i, c in enumerate(node["chapters"], start=1):
            chapter = Chapter()
            chapter.parent = self
            chapter.number = i
            chapter.parse_yaml(c)
            self.chapters.append(chapter)

    def text_directory(self) -> Path:
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

    def base_filename(self) -> str:
        return str(self.number)

    def is_single_part_chapter(self) -> bool:
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

    def base_filename(self) -> str:
        if self.parent.is_single_part_chapter():
            return self.parent.base_filename()
        else:
            return f"{self.parent.base_filename()}.{self.number}"

    def text_filepath(self) -> Path:
        return self.grandparent.text_directory() / (self.base_filename() + ".md")


def parse_book_config(directory: str):
    directory = Path(directory)
    config_file = directory / "config.yaml"

    if not directory.exists():
        print(f"Error: Input directory does not exist: '{directory}'")
        return None

    book = Book.from_file(config_file)

    return book


class BaseImagesConfig(DebugPrintable):
    directory: Path

    def __init__(self):
        self.directory = None

    @classmethod
    def from_file(cls, config_file):
        config_file = Path(config_file)
        if not config_file.exists():
            print(f"Error: Config file does not exist: '{config_file}'")
            return None

        data = yaml.safe_load(config_file.read_text())
        config = cls()
        config.directory = config_file.parent.resolve()
        config.parse_yaml(data)
        return config

    def image_from_yaml(self, node: dict, default_image_type=None) -> "ImageInfo":
        image_class_map = {"single": SingleImage, "double": DoubleImage}
        image_class = image_class_map[node.get("image_type", default_image_type)]

        return image_class(self, node)

    @abstractmethod
    def parse_yaml(self, node: dict):
        pass

    @abstractmethod
    def all_images_iter(self) -> Iterator["ImageInfo"]:
        pass


class GlobalImagesConfig(BaseImagesConfig):
    insert_filler: "ImageInfo"
    credits_background: "ImageInfo"
    after_credits: "ImageInfo"

    def __init__(self):
        super().__init__()
        self.insert_filler = None
        self.credits_background = None
        self.after_credits = None

    @override
    def parse_yaml(self, node: dict):
        self.insert_filler = self.image_from_yaml(node["insert_filler"], "single")
        self.insert_filler.is_filler = True

        self.credits_background = self.image_from_yaml(
            node["credits_background"], "single"
        )
        self.after_credits = self.image_from_yaml(node["after_credits"], "single")

    @override
    def all_images_iter(self) -> Iterator["ImageInfo"]:
        return filter(
            lambda x: x is not None,
            [self.insert_filler, self.credits_background, self.after_credits],
        )


class ImagesConfig(BaseImagesConfig):
    front_cover: "ImageInfo"
    back_cover: "ImageInfo"
    titlepage: "ImageInfo"
    toc: "ImageInfo"
    insert_images: "list[ImageInfo]"
    chapter_images: "OrderedDict[int, ImageInfo]"

    def __init__(self):
        super().__init__()
        self.front_cover = None
        self.back_cover = None
        self.titlepage = None
        self.toc = None
        self.insert_images = []
        self.chapter_images = OrderedDict()
        self.directory = None

    @override
    def parse_yaml(self, node: dict):
        self.front_cover = self.image_from_yaml(node["front_cover"], "single")
        self.back_cover = self.image_from_yaml(node["back_cover"], "single")
        self.titlepage = self.image_from_yaml(node["titlepage"], "single")
        self.toc = self.image_from_yaml(node["table_of_contents"], "double")

        for image_node in node["insert"]:
            self.insert_images.append(self.image_from_yaml(image_node))

        for chapter_number, image_node in node["chapter"].items():
            self.chapter_images[int(chapter_number)] = self.image_from_yaml(
                image_node, "double"
            )

    def non_filler_insert_images(self) -> Iterator["ImageInfo"]:
        return filter(lambda x: not x.is_filler, self.insert_images)

    @override
    def all_images_iter(self) -> Iterator["ImageInfo"]:
        return itertools.chain(
            self.insert_images,
            self.chapter_images.values(),
            filter(
                lambda x: x is not None,
                [self.front_cover, self.back_cover, self.titlepage, self.toc],
            ),
        )


PAPER_W_IN = 5.5
PAPER_H_IN = 8.25


class ImageInfo(ABC, DebugPrintable):
    parent: BaseImagesConfig
    is_filler: bool
    _filepath: str
    _height_inches: float
    _offset_px: tuple[int, int]

    def __init__(self, parent_config: BaseImagesConfig, yaml_node: dict):
        self.parent = parent_config
        self.is_filler = yaml_node.get("filler", False)
        self._filepath = yaml_node["filepath"]

        self._height_inches = PAPER_H_IN
        if "height" in yaml_node:
            self._height_inches = self.length_to_inches(yaml_node["height"])

        self._offset_px = (0, 0)
        if "offset" in yaml_node:
            offset_list = yaml_node["offset"]
            if len(offset_list) != 2:
                raise ValueError(offset_list)
            self._offset_px = tuple(self.length_to_px(offset) for offset in offset_list)

    def length_to_unit(self, length: str, unit: str) -> float:
        ureg = pint.UnitRegistry()
        ureg.define(f"px = inch / {self.px_per_in}")

        # We check it before since you can't make a Quantity without a unit,
        # and we check after since you can't convert a length without a unit.
        if not isinstance(length, str):
            raise ValueError(length)
        quantity = ureg(length)
        if isinstance(quantity, (int, float)):
            raise ValueError(quantity)
        return quantity.to(unit).magnitude

    def length_to_inches(self, length: str) -> float:
        return self.length_to_unit(length, "inch")

    def length_to_px(self, length: str) -> int:
        return round(self.length_to_unit(length, "px"))

    @abstractmethod
    def canvas_size_px(self, bleed_size: float) -> tuple[int, int]:
        pass

    def relative_image_path(self) -> Path:
        return Path(self._filepath)

    def absolute_image_path(self) -> Path:
        return self.parent.directory / self.relative_image_path()

    def padding_lrtb(self, bleed_size: float) -> tuple[int, int, int, int]:
        canvas_w, canvas_h = self.canvas_size_px(bleed_size)
        img_w, img_h = self.size_px
        offset_w, offset_h = self._offset_px

        assert (canvas_w - img_w) % 2 == 0, f"({canvas_w}, {img_w})"
        assert (canvas_h - img_h) % 2 == 0, f"({canvas_h}, {img_h})"

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
        return self.height_px / self._height_inches


class SingleImage(ImageInfo):
    @override
    def canvas_size_px(self, bleed_size: float) -> tuple[int, int]:
        return _canvas_size_px_helper(
            bleed_size, False, self.px_per_in, self.width_px, self.height_px
        )


class DoubleImage(ImageInfo):
    _overlap_px: int

    def __init__(self, parent_config: BaseImagesConfig, yaml_node: dict):
        super().__init__(parent_config, yaml_node)

        self._overlap_px = 0
        if "overlap" in yaml_node:
            self._overlap_px = self.length_to_px(yaml_node["overlap"])

    @override
    def canvas_size_px(self, bleed_size: float) -> tuple[int, int]:
        return _canvas_size_px_helper(
            bleed_size,
            True,
            self.px_per_in,
            self.width_px,
            self.height_px,
            self._overlap_px,
        )


def _canvas_size_px_helper(
    bleed_size: float,
    is_two_page: bool,
    px_per_in: float,
    width_px: int,
    height_px: int,
    overlap_px: int = 0,
) -> tuple[int, int]:
    if is_two_page:
        base_page_size_in = np.array([PAPER_W_IN * 2.0, PAPER_H_IN])
    else:
        base_page_size_in = np.array([PAPER_W_IN, PAPER_H_IN])
    full_page_size_in = base_page_size_in + (2 * bleed_size)
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
        while (width / height) < (PAPER_W_IN / PAPER_H_IN):
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
