# README
## BR NLP module WP3: KB development/KW extraction

This directory contains the software developed for WP3.

This is a pipeline tailored version of the kbd directory of the nlp_budapest repo, now focusing only on keyword extraction.

### How KW extraction is implemented.

This module takes as input the `description_text_nlp` field of NLP analysis and outputs its result in a new json field: `keywords`. The value of this field is a list of keyword: rankscore pairs:
```
"keywords": [
{"individual facade panel": 4}, 
{"interior light condition": 7}, 
{"compression ring": 13},
...
{"perimeter": 35},
{"membrane": 40},
{"color": 41}
]
```
The extraction process is controlled by a number of parameters that can be set to fine tune the result. See the `kw.cfg` file for more info.

### Scripts/files in this directory

All scripts give a brief usage info if called with `-h' option.

* `Makefile`: runs all stuff to produce anything you can with the tools provided here. A simple make gives you useful usage info. Unfortunately, in present setup you have to work in the current directory. In the pipeline context, only the keyword option is useful for a simple sanity check.

* `extract_kw.py`: extract key(phrase|word)s by the combination of RAKE and TextRank algorithms. Processes json input with nlp field added. Run `extract_kw.py` on any proper input file (eg. in `/mnt/nlp-data/data/normalized.nlp/worldarchitects/projects/`) to see some nice outputs. For input in the format of pipeline nlp dump files use `extract_kw.py -o inputfile`. Needs some fine tuning but already looks pretty impressive.

* `kw_helpers.py`: helper functions for KW extraction. (No options!)

* `make_stoplist.py`: helper script to generate python input data structures from resource files for KW extraction (see below). Can be run with make resources.

#### Resource files

* `kw.cfg`: configuration file for KW extraction parameters, self documented.

* `stoplist.txt`: list of tokens which separate (and so cannot be part of) keyword candidates.

* `postlist.txt`: list of tokens to be filtered out from final list of one token keywords.

* `patterns.txt`: list of patterns to filter out keywords matching any of the given patterns.

* `basetest.nlp`: source file for simple test run with make keyword.

### Contact

oravecz.csaba@gmail.com


