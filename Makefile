# A general purpose makefile for KB devel tasks
#########################################################################
# MAKEFILE
# No specific requirements

SHELL = /bin/bash
JUNKEXT = bak,log,err,aux
JUNKSUFF = ~
JUNKPREF = error,tmp,\#
JUNKFILE = core,.fix
CLEANSUFF= .tmp,.log
DISTCLEANSUFF =

.PHONY : clean default usage
.PRECIOUS: %.txt %.xml %.freq %.ncnd %.acnd

poslist=-p 'N.*,V.*,J.*'
prefix=.

#### Start of script configuration section. ####
bindir=$(prefix)
libdir=$(prefix)/../lib
modeldir=$(libdir)/models
workdir=.
sourcedir=/mnt/nlp-data/data/json
outdir=/mnt/nlp-data/nlp-output/resources/wordlists/

### Resource files
sourcenames = hassellstudio worldarchitects
reflist=$(libdir)/basic_en.lst
kwinput=./basetest.nlp
stoplist=./stoplist.txt
postlist=./postlist.txt
patterns=./patterns.txt
testset=./br_minta_v1.json

OUTLL= $(shell for i in $(sourcenames); do echo $$i.txt|sed s/.txt/.ll/; done)
OUTAMMWE= $(shell for i in $(sourcenames); do echo $$i.txt|sed s/.txt/.am_mwe/; done)
OUTATMWE= $(shell for i in $(sourcenames); do echo $$i.txt|sed s/.txt/.at_mwe/; done)
OUTAAMWE= $(shell for i in $(sourcenames); do echo $$i.txt|sed s/.txt/.aa_mwe/; done)
OUTNMMWE= $(shell for i in $(sourcenames); do echo $$i.txt|sed s/.txt/.nm_mwe/; done)
OUTNTMWE= $(shell for i in $(sourcenames); do echo $$i.txt|sed s/.txt/.nt_mwe/; done)
OUTNAMWE= $(shell for i in $(sourcenames); do echo $$i.txt|sed s/.txt/.na_mwe/; done)

### Targets
default: usage

inputs:
	@for i in $(sourcenames); do \
	echo "Extracting descriptions text from $$i"; \
	$(bindir)/dump_descriptions.py $(sourcedir)/$$i/projects/$$i* \
	> $$i.txt ; done


usage:
	@echo -e "Usage:\nRun 'make inputs' to prepare description text dumps\n into $(sourcenames) .txt files (takes a long time!).\n\nThen make <file>.ext with selected extension to get to the\n level of analysis you want.\n\nExtensions:\nxml  -> pos tagged\nfreq -> freqlist (use eg. poslist='-p N.*,J.*' to get only nouns and adjectives,\n        default is N,V,A)\nll   -> log-likelihood frequency profile (termlist) of text\ncnd  -> N-N MWE candidate list\nacnd -> A-N MWE candidate list\n*mwe -> various MWE lists (see source for details.\nBest to use 'make inputs; make all; make move' to get all stuff at once.\n\nKEYWORD extraction:\nrun 'make keyword' for a demo run or\n'make keyword kwinput=<your nlp-ed json file>' for the real stuff.\n'make eval testset=file' will run KW extraction on testset."

%.xml: %.txt
	java -cp $(libdir)/stanford-postagger.jar \
	edu.stanford.nlp.tagger.maxent.MaxentTagger -model \
	$(modeldir)/english-bidirectional-distsim.tagger \
	-textFile $< -outputFormat inlineXML \
	-outputFormatOptions lemmatize > $@

%.freq: %.xml
	$(bindir)/generate_freqlist.py $(poslist) $< > $@

%.ncnd: %.xml
	$(bindir)/make_mwe_candidates.py -f 'N.*' $< > $@

%.acnd: %.xml
	$(bindir)/make_mwe_candidates.py $< > $@

%.ll: %.freq
	$(bindir)/ll_value.py  -c 1 -a $< -b $(reflist) | \
	sort -nr > $@

%.am_mwe: %.acnd
	$(bindir)/make_mwe.py -m m -f 0 $< > $@

%.at_mwe: %.acnd
	$(bindir)/make_mwe.py -m t -f 0 $< > $@

%.aa_mwe: %.acnd
	$(bindir)/make_mwe.py -m a -f 0 $< > $@

%.nm_mwe: %.ncnd
	$(bindir)/make_mwe.py -m m -f 0 $< > $@

%.nt_mwe: %.ncnd
	$(bindir)/make_mwe.py -m t -f 0 $< > $@

%.na_mwe: %.ncnd
	$(bindir)/make_mwe.py -m a -f 0 $< > $@

all: $(OUTLL) $(OUTAMMWE) $(OUTATMWE) $(OUTAAMWE) $(OUTNMMWE) $(OUTNTMWE) $(OUTNAMWE)

move:
	mv *.ll *_mwe $(outdir)

resource:
	$(bindir)/make_stoplist.py $(stoplist)
	$(bindir)/make_stoplist.py -p $(postlist)
	$(bindir)/make_stoplist.py -r $(patterns)

keyword: resource
	$(bindir)/extract_kw.py -p 'N.*,J.*' $(kwinput)

eval:
	@[ -f $(testset) ] || { echo "Needs the testset..."; exit 1; }
	@ps auxww| grep -v grep| grep corenlp-server-0.1.jar>/dev/null || { echo "Needs the corenlp server..."; exit 1; }
	@if echo `pwd` | grep datamachine>/dev/null; \
	then echo 'Can only be run within the nlp_budapest repo!!!'; \
	else \
	d=$$(mktemp -d --tmpdir=.); \
	python ../brat/json_to_txt.py $(testset) $$d ; \
	cd $$d ; a=1; for i in *.txt; do echo $$a. Processing $$i...; \
	../../nlp/nlp_json.py --txt_infile $$i $${i%txt}raw; \
	let a=$$a+1; done ; \
	for i in *.raw; do cat $$i | perl -n -e 'chomp; print "[\"DUMYY_ID\", ", "$$_", "]\n"' > $${i%raw}json; done ; \
	for i in *.json; do ../extract_kw.py -a $$i > $${i%json}kw; done; \
	cd .. ; echo "Results are in .kw files in $$d" ; fi

start_corenlp-server:
	java -Xmx1g -cp /opt/stanford-nlp -jar /opt/stanford-nlp/corenlp-server-0.1.jar /home/projects/buildingradar_2015/devel/nlp_budapest/src/nlp/corenlp.properties	&

stop_corenlp-server:
	python ../nlp/corenlp-server-client.py stop

clean:
	sh -c 'rm -f *{$(CLEANSUFF)} *~ {$(JUNKFILE)}' 

distclean:
	sh -c 'rm -f *{$(DISTCLEANSUFF)} *~ {$(JUNKFILE)}'
