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

## Exporting to EPUB
To export to EPUB, run `Scripts/output_epub.py`:

``` sh

python ./Scripts/output_epub.py "./Volumes/Volume 3/" "./Output/"
```

- The first argument (`"./Volumes/Volume 3/"`) specifies the path to the directory containing the volume.
- The second argument (`"./Output/"`) is the location for the output file and any temporary working files.
