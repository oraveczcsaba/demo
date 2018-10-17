#!/usr/bin/env python
# coding: utf-8

"""
Short util to make a python readable dictionary from input file.
Not too decorated, used only from Makefile.

@Author: oraveczcsaba
"""

import sys
import argparse
from kw_helpers import load_stopwords

ap = argparse.ArgumentParser(
    description="""
    Make stopword/pattern resources for KW extraction.
    """)
ap.add_argument('-p', '--post', action="count",
                help="""
                prepare postprocess list
                (default is the main stoplist
                """)
ap.add_argument('-r', '--regex', action="count",
                help='prepare the list of patterns')
ap.add_argument('--version', action='version', version='%(prog)s 0.1')
ap.add_argument('-d', '--debug', action="count")
ap.add_argument('input', nargs='?', help='input file or stdin',
                default=sys.stdin)
args = ap.parse_args()

outfile = "constants.py"

if args.post:
    outfile = "postconstants.py"
elif args.regex:
    outfile = "patterns.py"

outdict = "stopwords"

if args.post:
    outdict = "postwords"
elif args.regex:
    outdict = "patterns"

infile = args.input


def load_patterns(file):
    """(file) -> dict

    Return dict of words from file.
    """

    # needs to be strict on line content preserving whitespace, too
    patterns = {}
    for line in open(file):
        if line.strip()[:1] != "#":
            # remove newline from end but nothing more!
            line = line[:-1]
            if line.isspace() or not line:
                continue
            patterns[line] = patterns.get(line, 0) + 1

    return patterns


def main():
    """
    Read input and do everything if standalone.
    """

    stopdict = load_patterns(infile) if args.regex else load_stopwords(infile)
    with open(outfile, 'w') as out:
        # preamble:
        print >>out, outdict, "= {"
        for key in stopdict:
            out.write("    {0}: {1},\n".format(repr(key.encode('utf-8')), 1))

        print >>out, "    }"


if __name__ == '__main__':
    main()
