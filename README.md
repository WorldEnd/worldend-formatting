**Note:** Still very much a work-in-progress.

# Prerequisites
You should have the following:

1. Python packages listed in `Scripts/requirements.txt`
2. `xelatex` in  your PATH

Additionally, you can set up a configuration file for `xelatex`. Create `Scripts/xelatex_config.py` and populate `xelatex_extra_args`, `xelatex_output_directory`, and `xelatex_job_name`.

`xelatex_extra_args` allows you to specify any extra arguments to `xelatex`. The other two specify the options for the output directory and job name, which is useful for different version of `xelatex`.

**The default values are listed below as an example configuration.**

```python
xelatex_extra_args = ["-interaction=batchmode", "-enable-installer"]
xelatex_output_directory = "-output-directory"
xelatex_job_name = "-job-name"
```

**Note:** Currently, you have to set all three of the variables or the default will be used. (Exception being that you can set `xelatex_extra_args` as an empty list.)

# Usage
Once you have completed all the prerequisites, you can run `Scripts/output_tex.py`:

```sh
python ./Scripts/output_tex.py "./Volumes/Volume 3" "./Output"
```
