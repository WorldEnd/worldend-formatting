import argparse
from pathlib import Path
import re

class AlternatingReplacer:
    def __init__(self, *args):
        self._counter = 0
        self._replace_by = list(args)

    def repl(self, _m):
        val = self._replace_by[self._counter]
        self._counter = (self._counter + 1) % len(self._replace_by)

        return val
    
    def reset(self, value = 0):
        self._counter = value % len(self._replace_by)
        
    def curr(self):
        return self._counter

def main():

    BOLD = "##BF##"
    IT = "##IT##"
    RULE = "##HR##"
    
    parser = argparse.ArgumentParser(
                        prog='markdown_html_tags',
                        description='Convert the tags * tags in markdown to HTML tags')
    
    parser.add_argument("input_file")
    parser.add_argument("output_file")
    
    args = parser.parse_args()
    
    input_file = Path(args.input_file)
    text = input_file.read_text()
    
    text = re.sub("[*_]( )?[*_]( )?[*_]", RULE, text)
    text = text.replace("**", BOLD)
    text = text.replace("*", IT)
    
    pars = text.split("\n\n")
    
    it = AlternatingReplacer("<em>", "</em>")
    bf = AlternatingReplacer("<strong>", "</strong>")
    rule = "* * *"
    for i in range(len(pars)):
        pars[i] = re.sub(IT, it.repl, pars[i])
        if it.curr() != 0:
            raise AssertionError(f"{it.curr()} - `{pars[i]}`")
        pars[i] = re.sub(BOLD, bf.repl, pars[i])
        if bf.curr() != 0:
            raise AssertionError(f"{bf.curr()} - `{pars[i]}`")
        pars[i] = re.sub(RULE, rule, pars[i])
    output_file = Path(args.output_file)
    output_file.write_text("\n\n".join(pars))
        
    

if __name__ == '__main__':
    main()