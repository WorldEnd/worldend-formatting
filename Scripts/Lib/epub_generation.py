from .config import (
    Chapter,
    Book,
    ImagesConfig,
)

import regex
from pathlib import Path
import string
import uuid
from datetime import datetime

uuid = str(uuid.uuid4())


class EPUBState:
    previous_is_break: bool
    previous_is_subpart: bool
    previous_is_first: bool
    previous_is_split: bool

    def __init__(self):
        self.previous_is_break = False
        self.previous_is_subpart = False
        self.previous_is_first = False
        self.previous_is_split = False

    def set_three(self, old_break: bool, old_subpart: bool, old_split: bool):
        self.previous_is_break = old_break
        self.previous_is_subpart = old_subpart
        self.previous_is_split = old_split


class EPUBGenerator:
    book_volume: int
    isbn: str
    text_directory: Path
    chapters: "list[Chapter]"
    images_config: ImagesConfig

    @classmethod
    def from_book_config(cls, book_config: Book, images_config: ImagesConfig):
        book = cls()
        book.book_volume = book_config.volume
        book.isbn = book_config.isbn
        book.text_directory = book_config.text_directory()
        book.chapters = book_config.chapters
        book.images_config = images_config
        return book

    def process_line(self, line: str, state: EPUBState) -> str:
        span = regex.match(r'^<span class="v-centered-page">(.+?)</span>$', line)

        if line == "* * *":
            state.set_three(False, True, False)
            return (
                '<div class="ext_ch">\n'
                '<div class="decoration-rw10">\n'
                '<div class="media-rw image-rw float-none-rw floatgalley-none-rw align-center-rw width-fixed-rw exclude-print-rw">\n'
                '<div class="pc-rw"><img class="ornament1" alt="" src="images/Art_sborn.jpg"/></div>\n'
                "</div>\n"
                "</div>\n"
                "</div>"
            )
        elif line == "<br/>":
            state.set_three(True, False, False)
            return ""
        elif span:
            state.set_three(False, False, True)
            return span.group(1)
        else:
            result = '<p class="{}">{}</p>'.format(
                (
                    "space-break"
                    if state.previous_is_break
                    else (
                        "tx1"
                        if state.previous_is_subpart
                        else ("cotx1a" if state.previous_is_first else "tx")
                    )
                ),
                line,
            )
            state.set_three(False, False, False)
            return result

    def process_chapter(self, chapter_number: int) -> list[list[str]]:
        letters = iter(string.ascii_lowercase)

        title_subtitle = self.replace_text(
            '<h1 class="chapter-title"><a id="Ref_{BOOK_VOLUME:02}{COUNTER:02}" href="toc.xhtml#Ref_{BOOK_VOLUME:02}{COUNTER:02}a">{CHAPTER_TITLE}</a></h1>\n'
            '<h2 class="chapter-subtitle"><a href="toc.xhtml#Ref_{BOOK_VOLUME:02}{COUNTER:02}a1">-{CHAPTER_SUBTITLE}-</a></h2>',
            start=chapter_number,
        )

        end = "</section>\n" "</div>\n" "</body>\n" "</html>"
        output = []

        for i, sublist in enumerate(self._join_chapter_parts(chapter_number)):
            letter = next(letters)
            beginning = self.replace_text(
                '<?xml version="1.0" encoding="UTF-8"?><html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="fr" lang="fr">\n'
                "<head>\n"
                "<title>WorldEnd2: What Do You Do at the End of the World? Could We Meet Again Once More?, Vol. {BOOK_VOLUME}</title>\n"
                '<link rel="stylesheet" href="css/stylesheet.css" type="text/css"/>\n'
                '<meta http-equiv="default-style" content="text/html; charset=utf-8"/>\n'
                "</head>\n"
                "<body>\n"
                '<div class="galley-rw">\n'
                '<section id="chapter{COUNTER:03}{LETTER}" class="body-rw Chapter-rw" epub:type="bodymatter chapter">',
                start=chapter_number,
                extra_replacements={"LETTER": letter},
            )

            if i == 0:
                output.append([beginning] + [title_subtitle] + sublist + [end])
            else:
                output.append([beginning] + sublist + [end])
        return output

    def _join_chapter_parts(self, chapter_number: int) -> list[list[str]]:
        combined_content = []

        state = EPUBState()

        current_section = []

        for part in self.chapters[chapter_number - 1].parts:
            if part.title is None:
                filename = f"{chapter_number}.md"
                state.previous_is_first = True
            else:
                filename = f"{chapter_number}.{part.number}.md"
                current_section.append(
                    '<p class="h1_co{}">{number}. {title}</p>'.format(
                        "" if part.number == 1 else "1",
                        number=part.number,
                        title=part.title,
                    )
                )
                state.previous_is_subpart = True

            lines = (self.text_directory / filename).read_text().splitlines()

            for line in lines:
                stripped_line = line.strip()

                if stripped_line:
                    new_line = self.process_line(stripped_line, state)
                    state.previous_is_first = False
                    if state.previous_is_split:
                        combined_content.append(current_section)
                        if new_line:
                            combined_content.append([f'<p class="tx10">{new_line}</p>'])
                        current_section = []
                        state.previous_is_split = False
                    elif new_line:
                        if not current_section:
                            current_section.append(
                                new_line.replace('<p class="tx">', '<p class="tx1">')
                            )
                        else:
                            current_section.append(new_line)

        if current_section:
            combined_content.append(current_section)
        return combined_content

    def generate_chapter_pages(self, chapter_number: int) -> str:
        return self.replace_text(
            "<?xml version='1.0' encoding='utf-8'?>\n"
            '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="fr" lang="fr">\n'
            "<head>\n"
            "<title>WorldEnd2: What Do You Do at the End of the World? Could We Meet Again Once More?, Vol. {BOOK_VOLUME}</title>\n"
            '<link rel="stylesheet" href="css/stylesheet.css" type="text/css"/>\n'
            "</head>\n"
            "<body>\n"
            '<div class="galley-rw">\n'
            '<section id="chapter{CHAPTER_NUMBER:03}" class="body-rw Chapter-rw" epub:type="bodymatter chapter">\n'
            '<div class="image_full"><img alt="Book Title Page" src="images/Art_chapter{CHAPTER_NUMBER:03}.jpg"/></div>\n'
            "</section>\n"
            "</div>\n"
            "</body>\n"
            "</html>",
            start=chapter_number,
        )

    def generate_nav_xhtml(self) -> str:
        text = self.replace_text(
            "<?xml version='1.0' encoding='utf-8'?>\n"
            '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="fr" lang="fr">\n'
            "<head>\n"
            "<title>WorldEnd2: What Do You Do at the End of the World? Could We Meet Again Once More?, Vol. {BOOK_VOLUME}</title>\n"
            '<link rel="stylesheet" href="css/stylesheet.css" type="text/css"/>\n'
            "</head>\n"
            "<body>\n"
            '<nav epub:type="toc">\n'
            "  <h1>Contents</h1>\n"
            "  <ol>\n"
            '    <li><a href="cover.xhtml">Cover</a></li>\n'
            '    <li><a href="insert001.xhtml">Insert</a></li>\n'
            '    <li><a href="titlepage.xhtml">Title Page</a></li>\n'
            '    <li><a href="toc.xhtml">Table of Contents</a></li>\n',
        )

        text += self.replace_text(
            '    <li><a href="chapter{CHAPTER_NUMBER:03}.xhtml">{CHAPTER_TITLE}</a></li>\n',
            self.chapters,
        )

        text += (
            "  </ol>\n"
            "</nav>\n"
            '<nav epub:type="landmarks" class="hidden-tag" hidden="hidden">\n'
            "<h1>Navigation</h1>\n"
            '<ol epub:type="list">\n'
            '<li><a epub:type="cover" href="cover.xhtml#coverimage">Begin Reading</a></li>\n'
            '<li><a epub:type="toc" href="toc.xhtml">Table of Contents</a></li>\n'
            "</ol>\n"
            "</nav>\n"
            "</body>\n"
            "</html>"
        )

        return text

    def generate_title_page(self) -> str:
        return self.replace_text(
            '<?xml version="1.0" encoding="UTF-8"?><html xmlns:epub="http://www.idpf.org/2007/ops" xmlns="http://www.w3.org/1999/xhtml" lang="en" xml:lang="en">\n'
            "<head>\n"
            '<meta http-equiv="default-style" content="text/html; charset=utf-8"/>\n'
            "<title>WorldEnd2: What Do You Do at the End of the World? Could We Meet Again Once More?, Vol. {BOOK_VOLUME}</title>\n"
            '<link rel="stylesheet" href="css/stylesheet.css" type="text/css"/>\n'
            "</head>\n"
            "<body>\n"
            '<section class="frontmatter-rw TitlePage-rw exclude-print-rw" id="BookTitlePage1" epub:type="frontmatter titlepage">\n'
            '<div class="width-90">\n'
            '<div class="pc">\n'
            '<img alt="Book Title Page" src="images/Art_tit.jpg"/>\n'
            "</div>\n"
            "</div>\n"
            "</section>\n"
            "</body>\n"
            "</html>",
        )

    def generate_insert_pages(self, insert_number: int) -> str:
        return self.replace_text(
            '<?xml version="1.0" encoding="UTF-8"?><html xmlns:epub="http://www.idpf.org/2007/ops" xmlns="http://www.w3.org/1999/xhtml" lang="en" xml:lang="en">\n'
            "<head>\n"
            '<meta http-equiv="default-style" content="text/html; charset=utf-8"/>\n'
            "<title>WorldEnd2: What Do You Do at the End of the World? Could We Meet Again Once More?, Vol. {BOOK_VOLUME}</title>\n"
            '<link rel="stylesheet" href="css/stylesheet.css" type="text/css"/>\n'
            "</head>\n"
            "<body>\n"
            '<section id="insert{INSERT_NUMBER:03}" epub:type="frontmatter titlepage">\n'
            '<div class="image_full">\n'
            '<img src="images/Art_insert{INSERT_NUMBER:03}.jpg" alt="Book Title Page"/>\n'
            "</div>\n"
            "</section>\n"
            "</body>\n"
            "</html>",
            extra_replacements={"INSERT_NUMBER": insert_number},
        )

    def generate_toc_xhtml(self) -> str:
        text = self.replace_text(
            '<?xml version="1.0" encoding="UTF-8"?><html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">\n'
            "<head>\n"
            "<title>WorldEnd2: What Do You Do at the End of the World? Could We Meet Again Once More?, Vol. {BOOK_VOLUME}</title>\n"
            '<meta content="text/html; charset=utf-8" http-equiv="default-style"/>\n'
            '<link rel="stylesheet" href="css/stylesheet.css" type="text/css"/>\n'
            "</head>\n"
            "<body>\n"
            '<div class="galley-rw">\n'
            '<section id="tocx" class="body-rw Chapter-rw" epub:type="bodymatter chapter">\n'
            '<h1 class="toc-title">Contents</h1>\n'
            '<p class="toc-front" id="cover"><a href="cover.xhtml">Cover</a></p>\n'
            '<p class="toc-front" id="insert001"><a href="insert001.xhtml">Insert</a></p>\n'
            '<p class="toc-front" id="titlepage"><a href="titlepage.xhtml">Title Page</a></p>\n'
        )

        text += self.replace_text(
            '<p class="toc-chapter1" id="Ref_{BOOK_VOLUME:02}{CHAPTER_NUMBER:02}a"><a href="chapter{CHAPTER_NUMBER:03}.xhtml"><strong>{CHAPTER_TITLE}</strong></a></p>\n'
            '<p class="toc-chaptera" id="Ref_{BOOK_VOLUME:02}{CHAPTER_NUMBER:02}a1"><a href="chapter{CHAPTER_NUMBER:03}.xhtml">-{CHAPTER_SUBTITLE}-</a></p>\n',
            self.chapters,
        )

        text += "</section>\n" "</div>\n" "</body>\n" "</html>"

        return text

    def generate_toc_ncx(self) -> str:
        text = self.replace_text(
            "<?xml version='1.0' encoding='utf-8'?>\n"
            '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1" xml:lang="en">\n'
            "  <head>\n"
            '    <meta name="dtb:uid" content="{ISBN}"/>\n'
            '    <meta name="dtb:depth" content="2"/>\n'
            '    <meta name="dtb:totalPageCount" content="0"/>\n'
            '    <meta name="dtb:maxPageNumber" content="0"/>\n'
            "  </head>\n"
            "  <docTitle>\n"
            "    <text>WorldEnd2: What Do You Do at the End of the World? Could We Meet Again Once More?, Vol. {BOOK_VOLUME}</text>\n"
            "  </docTitle>\n"
            "  <navMap>\n"
            '    <navPoint id="num_1" playOrder="1">\n'
            "      <navLabel>\n"
            "        <text>Cover</text>\n"
            "      </navLabel>\n"
            '      <content src="cover.xhtml"/>\n'
            "    </navPoint>\n"
            '    <navPoint id="num_2" playOrder="2">\n'
            "      <navLabel>\n"
            "        <text>Insert</text>\n"
            "      </navLabel>\n"
            '      <content src="insert001.xhtml"/>\n'
            "    </navPoint>\n"
            '    <navPoint id="num_3" playOrder="3">\n'
            "      <navLabel>\n"
            "        <text>Title Page</text>\n"
            "      </navLabel>\n"
            '      <content src="titlepage.xhtml"/>\n'
            "    </navPoint>\n"
            '    <navPoint id="num_4" playOrder="4">\n'
            "      <navLabel>\n"
            "        <text>Table of Contents</text>\n"
            "      </navLabel>\n"
            '      <content src="toc.xhtml"/>\n'
            "    </navPoint>\n",
        )

        for chapter in self.chapters:
            text += (
                '    <navPoint id="num_{CHAPTER_NUMBER_5}" playOrder="{CHAPTER_NUMBER_5}">\n'
                "      <navLabel>\n"
                "        <text>{CHAPTER_TITLE}</text>\n"
                "      </navLabel>\n"
                '      <content src="chapter{CHAPTER_NUMBER:03}.xhtml"/>\n'
                "    </navPoint>\n"
            ).format(
                CHAPTER_NUMBER=chapter.number,
                CHAPTER_NUMBER_5=chapter.number + 4,
                CHAPTER_TITLE=chapter.title,
            )

        text += "  </navMap>\n" "</ncx>"
        return text

    def generate_cover_page(self) -> str:
        return self.replace_text(
            "<?xml version='1.0' encoding='utf-8'?>\n"
            '<html xmlns:epub="http://www.idpf.org/2007/ops" xmlns="http://www.w3.org/1999/xhtml" lang="en" xml:lang="en">\n'
            "<head>\n"
            "<title>WorldEnd2: What Do You Do at the End of the World? Could We Meet Again Once More?, Vol. {BOOK_VOLUME}</title>\n"
            '<link rel="stylesheet" type="text/css" href="css/stylesheet.css"/>\n'
            "</head>\n"
            "<body>\n"
            '<section epub:type="cover">\n'
            '<div class="cover_image"><img id="coverimage" src="images/{ISBN}.jpg" alt="Cover"/></div>\n'
            "</section>\n"
            "</body>\n"
            "</html>",
        )

    def generate_package_opf(self, combined_chapters: dict[int, list[list[str]]]):
        text = self.replace_text(
            '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" xml:lang="en" unique-identifier="pub-id">\n'
            '  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
            '    <dc:title id="id">WorldEnd2: What Do You Do at the End of the World? Could We Meet Again Once More?, Vol. {BOOK_VOLUME}</dc:title>\n'
            '    <dc:creator id="id-1">Akira Kareno</dc:creator>\n'
            '    <dc:creator id="id-2">ue</dc:creator>\n'
            # "    <dc:rights>©2014 Akira Kareno, ue</dc:rights>\n"
            "    <dc:identifier>uuid:{UUID}</dc:identifier>\n"
            '    <dc:identifier id="pub-id">{ISBN}</dc:identifier>\n'
            "    <dc:language>en</dc:language>\n"
            "    <dc:publisher>Orlandri Translation Company</dc:publisher>\n"
            '    <meta refines="#id" property="title-type">main</meta>\n'
            '    <meta refines="#id" property="file-as">WorldEnd2: What Do You Do at the End of the World? Could We Meet Again Once More?, Vol. {BOOK_VOLUME}</meta>\n'
            '    <meta property="dcterms:modified">{TIME}</meta>\n'
            '    <meta refines="#id-1" property="role" scheme="marc:relators">aut</meta>\n'
            '    <meta refines="#id-1" property="file-as">Kareno, Akira</meta>\n'
            '    <meta refines="#id-2" property="role" scheme="marc:relators">aut</meta>\n'
            '    <meta refines="#id-2" property="file-as">ue</meta>\n'
            "  </metadata>\n"
            "  <manifest>\n"
            '    <item href="cover.xhtml" id="id_cover_xhtml" media-type="application/xhtml+xml"/>\n',
            extra_replacements={
                "UUID": uuid,
                "TIME": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
        )

        text += self.replace_text(
            '    <item href="insert{COUNTER:03}.xhtml" id="insert{COUNTER:03}" media-type="application/xhtml+xml"/>\n',
            self.images_config.non_filler_insert_images(),
        )

        text += (
            '    <item href="titlepage.xhtml" id="titlepage" media-type="application/xhtml+xml"/>\n'
            '    <item href="toc.xhtml" id="toc" media-type="application/xhtml+xml"/>\n'
        )

        for chapter_number, combined_content in combined_chapters.items():
            letters = iter(string.ascii_lowercase)
            text += f'    <item href="chapter{chapter_number:03}.xhtml" id="chapter{chapter_number:03}" media-type="application/xhtml+xml"/>\n'
            for section in combined_content:
                letter = next(letters)
                text += f'    <item href="chapter{chapter_number:03}{letter}.xhtml" id="chapter{chapter_number:03}{letter}" media-type="application/xhtml+xml"/>\n'

        text += self.replace_text(
            '    <item href="nav.xhtml" id="nav" media-type="application/xhtml+xml" properties="nav"/>\n'
            '    <item href="toc.ncx" id="ncx" media-type="application/x-dtbncx+xml"/>\n'
            '    <item href="css/stylesheet.css" id="id_chapter_1_style_css" media-type="text/css"/>\n'
            '    <item href="images/{ISBN}.jpg" id="acover" media-type="image/jpeg" properties="cover-image"/>\n'
            '    <item href="images/Art_copy.jpg" id="aArt_copy" media-type="image/jpeg"/>\n'
        )

        text += self.replace_text(
            '    <item href="images/Art_insert{COUNTER:03}.jpg" id="aArt_insert{COUNTER:03}" media-type="image/jpeg"/>\n',
            self.images_config.non_filler_insert_images(),
        )

        text += '    <item href="images/Art_line1.jpg" id="aArt_line1" media-type="image/jpeg"/>\n'

        text += self.replace_text(
            '    <item href="images/Art_chapter{CHAPTER_NUMBER:03}.jpg" id="aArt_chapter{CHAPTER_NUMBER:03}" media-type="image/jpeg"/>\n',
            self.chapters,
        )

        text += (
            '    <item href="images/Art_sborn.jpg" id="aArt_sborn" media-type="image/jpeg"/>\n'
            '    <item href="images/Art_tit.jpg" id="aArt_tit" media-type="image/jpeg"/>\n'
            "  </manifest>\n"
            '  <spine page-progression-direction="ltr" toc="ncx">\n'
            '    <itemref idref="id_cover_xhtml" linear="yes"/>\n'
        )

        text += self.replace_text(
            '    <itemref idref="insert{COUNTER:03}" linear="yes"/>\n',
            self.images_config.non_filler_insert_images(),
        )

        text += (
            '    <itemref idref="titlepage" linear="yes"/>\n'
            '    <itemref idref="toc" linear="yes"/>\n'
        )

        for chapter_number, combined_content in combined_chapters.items():
            letters = iter(string.ascii_lowercase)
            text += f'    <itemref idref="chapter{chapter_number:03}" linear="yes"/>\n'
            for section in combined_content:
                letter = next(letters)
                text += f'    <itemref idref="chapter{chapter_number:03}{letter}" linear="yes"/>\n'

        text += (
            "  </spine>\n"
            "  <guide>\n"
            '    <reference type="start" title="Begin Reading" href="cover.xhtml"/>\n'
            '    <reference type="text" title="Begin Reading" href="toc.xhtml"/>\n'
            '    <reference type="toc" title="Table of Contents" href="toc.xhtml"/>\n'
            '    <reference type="cover" title="Cover Image" href="cover.xhtml"/>\n'
            "  </guide>\n"
            "</package>"
        )
        return text

    def replace_text(
        self,
        text: str,
        things=[None],
        extra_replacements={},
        start=1,
        conditional_function=None,
    ) -> str:
        result = ""
        counter = start
        for thing in things:
            if conditional_function is None or conditional_function(thing):
                result += text.format(
                    CHAPTER_NUMBER=(
                        self.chapters[counter - 1].number
                        if regex.search(r"\{CHAPTER_NUMBER(:\w+)?\}", text)
                        else ""
                    ),
                    CHAPTER_TITLE=(
                        self.chapters[counter - 1].title
                        if regex.search(r"\{CHAPTER_TITLE(:\w+)?\}", text)
                        else ""
                    ),
                    CHAPTER_SUBTITLE=(
                        self.chapters[counter - 1].subtitle
                        if regex.search(r"\{CHAPTER_SUBTITLE(:\w+)?\}", text)
                        else ""
                    ),
                    BOOK_VOLUME=self.book_volume,
                    ISBN=self.isbn,
                    COUNTER=counter,
                    **extra_replacements,
                )
                counter += 1
        return result
