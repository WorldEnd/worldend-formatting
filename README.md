**Note:** Still very much a work-in-progress.

# Prerequisites
You should have the following:

1. Python packages listed in `Scripts/requirements.txt`.
2. (If exporting to PDF) `xelatex` in your PATH.
    * If your TeX distribution does not support automatically installing missing packages, you'll also need to install all the necessary TeX packages to compile `Common/TeX/WorldEnd2_Common.tex`.

# Usage
## Exporting to PDF
Once you have completed all the prerequisites, you can run `Scripts/output_tex.py`:

```sh
python ./Scripts/output_tex.py "./Volumes/Volume 3/" "./Output/"
```

- The first argument (`"./Volumes/Volume 3/"`) specifies the path to the directory containing the volume.
- The second argument (`"./Output/"`) is the location for the output file and any temporary working files.

### Printing
If you want to generate the PDF for printing in a perfect-bound book, there are three related flags:

- `-b` (`--bleed-size`): Specify the bleed size.
- `-g` (`--gutter-size`): Specify the gutter size.
- `-n` (`--no-cover`): Do not include cover.
 
By default, the bleed size is 0, gutter size is 0, and cover is included.

For convenience, `-p` (`--print-mode`) is provided, which is short for `-b 0.125 -g 0.15 -n`.

It is possible to tweak the print options alongside `--print-mode` by appending them after. For example, `-p -b 0` enables print mode without bleed. If you put the print options before print mode, they will be overwritten, but other arguments can be put before without consequence.

## Exporting to EPUB
To export to EPUB, run `Scripts/output_epub.py`:

``` sh

python ./Scripts/output_epub.py "./Volumes/Volume 3/" "./Output/"
```

- The first argument (`"./Volumes/Volume 3/"`) specifies the path to the directory containing the volume.
- The second argument (`"./Output/"`) is the location for the output file and any temporary working files.
