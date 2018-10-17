#!/usr/bin/env python
# coding: utf-8

"""
Script to extract KWs by using several extraction algorithms and interpolating
their results applying 'clever' linguistic filters. The algorithms are:

- Rapid Automatic Keyword Extraction algorithm.
(Rose, S. etal, 2010)
Based on:
https://github.com/aneesha/RAKE
released under the MIT Licence.

- TextRank
(Mihalcea, R. and P. Tarau, 2004)
Based on:
https://gist.github.com/voidfiles/1646117

Uses nlp parsed and preprocessed (json) input!

TODO:

- set hard boundary at the end of NP when generating phrase candidates
  (this might not be needed, seems too strict and very rarely needed)
- boost it up with more resources (must_add_list, wordnet scores etc.)
- postprocess result list with filters:
  - if KW_i is subsumed by longer KW_j then delete KW_i (? not sure this is
    needed...)
@Author: oraveczcsaba
"""

import sys
import argparse
import json
import re
import itertools
import collections
from kw_helpers import unique, isNumeric, printout, \
    neighbours, write_out, post_textrank, merge_dict, topranked
from pygraph.classes.digraph import digraph
from pygraph.algorithms.pagerank import pagerank
from pygraph.classes.exceptions import AdditionError
from pkg_resources import resource_filename
import ConfigParser

config = ConfigParser.RawConfigParser()

try:
    from pipeline.spark.spark_utils import save_dump
    config.read(resource_filename("pipeline.projects.kbd", "kw.cfg"))
except ImportError:
    config.read(resource_filename(__name__, "kw.cfg"))
    sys.stderr.write("Carefully, carefully, you have a standalone run!\n")

from constants import stopwords
from postconstants import postwords
from patterns import patterns


ap = argparse.ArgumentParser(
    description="""
    Extract keywords merging the RAKE and TextRank algorithms.
    """)
ap.add_argument('-v', '--verbose', action="count",
                help='verbose output for testing (eg. no intertoken filter)')
ap.add_argument('-l', '--lemma', action="count",
                help='use lemmas instead of wordforms')
ap.add_argument('-a', '--spark', action="count",
                help='take the spark processing route')
ap.add_argument('-o', '--oneline', action="count",
                help='standalone with one line/one json input')
ap.add_argument('-r', '--rake', action="count",
                help='return RAKE output (in add. to merged)')
ap.add_argument('-t', '--textrank', action="count",
                help='return TextRank output (in add. to merged)')
ap.add_argument('-p', action='store', dest='pos', type=str,
                help='(comma separated list of) pos regexps to include')
ap.add_argument('-n', action='store', dest='window', type=int,
                help='size of window for TextRank')
ap.add_argument('-c', action='store', dest='threshold', type=int,
                help='minimum freq for RAKE complex keywords')
ap.add_argument('--version', action='version', version='%(prog)s 0.2')
ap.add_argument('-d', '--debug', action="count")
ap.add_argument('input', nargs='?', help='input json or stdin',
                default=sys.stdin)
args = ap.parse_args()

# set parameters
window = args.window if args.window else config.getint('General', 'window')
threshold = args.threshold if args.threshold else config.getint('General',
                                                                'threshold')
poslist = args.pos.split(',') if args.pos else \
    config.get('General', 'poslist').split(',')
allowed = config.get('General', 'allowed').split(',')
lemma = 1 if args.lemma else config.getint('General', 'lemma')
tr_ratio = config.getint('General', 'ratio')
toprank = config.getint('General', 'toprank')
kwlimit = config.getint('General', 'kwlimit')
textlength = config.getint('General', 'textlength')
maxmember = config.getint('General', 'maxmember')
testing = 1 if args.verbose else 0
debug = args.debug
infile = args.input

if not infile == sys.stdin:
    infile = open(infile, 'r')

job_name = 'kw'


def process_spark(input_data, dump=False, job_sub_name='tmp'):
    """ (rdd, str, str) -> rdd

    Return keyword assigned entries.
    """

    kw = input_data.map(process_spark_entry)
    if dump:
        save_dump(kw, job_name, job_sub_name)

    return kw


def process_spark_entry(entry_unit):
    """ [list] -> tuple

    Return an (id, entry) tuple with keyword field. Use for processing
    under spark.
    """

    entry_id, entry = entry_unit
    if 'description_text_nlp' not in entry:
        return (entry_id, entry)
    else:
        nlp_entry = entry['description_text_nlp']
        # entry['description_text_nlp'] = "__DELETED__"
        sentences, sent_index, numtokens = get_sentences_from_entry(nlp_entry)
        if numtokens < textlength:
            return (entry_id, entry)
        phraseList, phrase_by_token, phrase_by_index = make_candidate_kw(
            sentences,
            stopwords,
            lemma,
            poslist)
        wordscores = rake_word_scores(phraseList)
        rake_candidates = rake_phrase_scores(phraseList, wordscores)
        ckw = neighbours(debug, rake_candidates,
                         sent_index, phrase_by_token,
                         phrase_by_index, allowed,
                         testing,
                         threshold=threshold)
        rake_candidates.update(ckw)
        textrank_kw = compute_textrank(phraseList, window, lemma, tr_ratio)
        merged = merge_dict(rake_candidates, textrank_kw)
        postmerged = postfilter(merged, postwords, patterns, maxmember)
        head = topranked(postmerged, phraseList, kwlimit, toprank)
        # add KW field but only if not empty
        if head:
            kwlist = [{" ".join(key): head[key]} for
                      key in sorted(head, key=head.get)]
            entry['keywords'] = kwlist
    return (entry_id, entry)


def process_entries(nlp_entry, stopwords, lemma,
                    poslist, threshold, tr_ratio,
                    toprank, textlength):
    """ (dict, dict, int, list, int, int) -> None

    Temporary main processor for KW extraction. To be replaced by
    more principled integration into pipeline.
    """
    # default split of input into fragments, plus text storage
    sentences, sent_index, numtokens = get_sentences_from_entry(nlp_entry)
    if numtokens < textlength:
        print "===>TEXT LENGTH UNDER LIMIT: SKIPPED<==="
        return False
    # generate candidate keywords and indexes for postprocessing
    phraseList, phrase_by_token, phrase_by_index = make_candidate_kw(
        sentences,
        stopwords,
        lemma,
        poslist)
    # calculate RAKE word scores
    wordscores = rake_word_scores(phraseList)
    # and phrase scores
    rake_candidates = rake_phrase_scores(phraseList, wordscores)
    # postprocess RAKE candidates to get more complex phrases
    ckw = neighbours(debug, rake_candidates,
                     sent_index, phrase_by_token,
                     phrase_by_index, allowed,
                     testing,
                     threshold=threshold)
    # merge the above two results
    rake_candidates.update(ckw)
    # compute textrank dict
    textrank_kw = compute_textrank(phraseList, window, lemma, tr_ratio)
    # merge the two rankings into one
    merged = merge_dict(rake_candidates, textrank_kw)
    # apply postfilter
    postmerged = postfilter(merged, postwords, patterns, maxmember)
    # take the first N elements only (proportional to text length)
    head = topranked(postmerged, phraseList, kwlimit, toprank)
    # make a simple print for the time being
    if args.textrank:
        print "====>TEXTRANK<===="
        printout(textrank_kw)
    if args.rake:
        print "=====>RAKE<====="
        printout(rake_candidates)
    # print merged
    print "====>MERGED<===="
    printout(head, reverse=False)


def read_json(file):
    """ (file) -> list

    Returns a list of json 'description_text_nlp' fields
    from input file (stdin).
    To be replaced by a proper entry reader.
    """

    nlp_entries = []
    for entry in json.load(file):
        nlp_entries.append(entry['description_text_nlp'])
    return nlp_entries


def get_sentences_from_entry(nlp_entry):
    # this is the entry point for this program if integrated
    # into the pipeline
    """ (dict) -> list, dict, int
    Return
    1. a list of sentence fragments (split by punctuations)
    from the input dict containing an nlp entry.
    A sentence fragment is a list of (token, lemma, POS, textposition) tuples.

    2. a dict of indexes with (word, lemma, pos) tuples as values.

    3. the number of non-punctuation tokens in the text (to allow for
    text length threshold check).

    Input is the content of the description_text_nlp field.
    """

    sentences = []
    sent = []
    sent_index = {}
    index = 0
    for sentence in nlp_entry['sentences']:
        for token in sentence['tokens']:
            word = token['word'].encode('utf-8')
            lemma = token['lemma'].encode('utf-8')
            pos = str(token['POS'])
            if str.isalpha(pos[0]):
                sent.append((word,
                             lemma,
                             pos,
                             index))
                sent_index[index] = (word,
                                     lemma,
                                     pos)
                index += 1
            else:
                if sent:
                    if debug:
                        write_out(("ADDING S:", sent))
                    sentences.append(sent)
                    sent = []
        if sent:
            # add last chunk at the end of sentence
            if debug:
                write_out(("ADDING S:", sent))
            sentences.append(sent)
            sent = []
    return sentences, sent_index, index


def make_candidate_kw(sentences, stopwords, lemma, poslist):
    """(list, dict, int, list) -> list, dict, dict

    Return
    1. a list of list of words as candidate phrases for KWs,
    2. a dictionary of phrase tuples containing positional indeces,
    3. a dictionary of positional indexes containing
    (phrase_tuple, textindex_of_first_word, textindex_of_last_word) tuples.
    The 2. and 3. dictionaries can be used for postprocessing to rejoin phrases
    into complex KWs.
    """

    phrase_list = []
    phrase_count = 0
    # store phrase indexes for postprocessing KW candidates
    phrase_by_token = collections.defaultdict(lambda: [])
    phrase_by_index = collections.defaultdict(lambda: [])
    for sentence in sentences:
        prevpos = 'X'
        phrase = []
        firstindex = 0
        for wtuple in sentence:
            pos = wtuple[2]
            word = wtuple[lemma]
            # do not case fold proper nouns
            if pos != 'NNP':
                word.lower()
            word_index = wtuple[3]
            if debug:
                write_out(("WORD+INDEX:", word_index, word))
            firstindex = firstindex if len(phrase) else word_index
            # filter for pos if needed
            skip = 1 if poslist else 0
            adjskip = 1 if (prevpos[0] == 'N' and pos[0] == 'J') else 0
            prevpos = pos
            if [pos for fpos in poslist if re.match(fpos, pos)]:
                skip = 0
            if word in stopwords or skip or adjskip:
                # if word is stopword switch off adjskip branch below!
                if word in stopwords:
                    adjskip = 0
                # boundary of phrase so set back indexes unless adjskip
                word_index = word_index - 1
                if len(phrase) > 0:
                    phrase_list.append(phrase)
                    phrase_by_token[tuple(phrase)].append(phrase_count)
                    phrase_by_index[phrase_count] = ((tuple(phrase),
                                                      firstindex,
                                                      word_index))
                    if debug:
                        write_out(("ADDING PHRASE:",
                                   tuple(phrase),
                                   phrase_count,
                                   firstindex,
                                   word_index))
                    phrase_count += 1
                    phrase = []
                # if adjskip we have to start next phrase and set its
                # firstindex as this adj can be first member of next phrase
                if adjskip:
                    firstindex = word_index + 1
                    phrase.append(word)
                    if debug:
                        print "ADJSKIP:", word, "FIRSTINDEX:", firstindex
            else:
                phrase.append(word)
                if debug:
                    write_out(("APPEND FIRSTINDEX:",
                               firstindex, "WORD:",
                               word, "WORDINDEX:",
                               word_index))
        # add last member in sentence
        if len(phrase) > 0:
            phrase_list.append(phrase)
            phrase_by_token[tuple(phrase)].append(phrase_count)
            phrase_by_index[phrase_count] = ((tuple(phrase),
                                              firstindex,
                                              word_index))
            phrase_count += 1
            if debug:
                write_out(("ADDING LAST PHRASE:",
                           tuple(phrase),
                           phrase_count,
                           firstindex, word_index))
    return phrase_list, phrase_by_token, phrase_by_index


def rake_word_scores(phraseList):
    """(list) -> dict

    Return a dict of words with their RAKE score values.
    """

    word_freq = {}
    word_degree = {}
    for phrase in phraseList:
        degree = len(filter(lambda x: not isNumeric(x), phrase)) - 1
        for word in phrase:
            word_freq[word] = word_freq.get(word, 0) + 1.0
            word_degree[word] = word_degree.get(word, 0) + float(degree)
    for word in word_freq:
        word_degree[word] = word_degree[word] + word_freq[word]  # itself
    # word score = deg(w) / freq(w)
    word_score = {}
    for word in word_freq:
        word_score[word] = word_degree[word] / word_freq[word]
        if debug:
            write_out(("ITEM:", word,
                       "SCORE:",  word_score[word]))
    return word_score


def compute_textrank(phrase_list, window, lemma, ratio=2):
    """(list, int, int, int) -> dict

    Return a dict of KWs with textrank scores.
    Arguments:
    - phrase_list: list of candidate phrase lists
    - window: size of cocccurrence window
    - lemma: 1 if lemmas are used instead of wordforms
    - ratio: ratio of all KWs included in the top N list
    """

    # flatten out input phrase list to get back text for postprocessing
    # this is not very optimal
    text = list(itertools.chain.from_iterable(phrase_list))
    numwords = len(text)
    # set up graph
    gr = digraph()
    gr.add_nodes(unique(text))
    if debug:
        write_out(("TEXT:", text))
    # add edges for words within window, be careful to add members
    # for the last shrinking windows at the end of list!
    i = 0
    while i < numwords - 1:
        source = text[i]
        firstindex = i + 1
        lastindex = i + window
        if lastindex > numwords:
            lastindex = numwords
        if firstindex > numwords - 1:
            break

        for w in text[firstindex:lastindex]:
            if debug:
                write_out(("EGDE BTW:", source,
                           "and", w))
            try:
                gr.add_edge((source, w))
            except AdditionError:
                sys.stderr.write('Already added: {0}\t{1}\n'.format(source, w))

        i += 1

    # calculate pagerank
    prdict = pagerank(gr)
    prlist = [(key, prdict[key]) for key in sorted(prdict,
                                                   key=prdict.get,
                                                   reverse=True)]
    # get first number of nodes/ratio elements
    if debug:
        write_out(("TR FULL LIST:", prlist))
    prlist = prlist[:numwords / ratio]
    if debug:
        write_out(("TR SHORT LIST:", prlist))
    # make a dict from the list to facilitate postprocessing
    prdict = dict(prlist)
    # postrocess initial result
    textranked = post_textrank(prdict, phrase_list)
    return textranked


def rake_phrase_scores(phrase_list, word_scores):
    """(list, dict) -> dict

    Return a dict of phrases with their scores.
    """

    phrase_scores = {}
    for phrase in phrase_list:
        phrase_score = 0
        for word in phrase:
            phrase_score += word_scores[word]
        phrase_scores[tuple(phrase)] = phrase_score
    return phrase_scores


def postfilter(merged, postwords, patterns, maxmember):
    """(dict, dict, dict, int) -> dict

    Return a filtered result KW dictionary by stoplist and patterns.
    Arguments:
    - merged: input dictionary of KWs
    - postwords: dict of tokens not allowed as individual KWs
    - patterns: dict of patterns not allowed in KWs
    - maxmember: maximum number of tokens allowed in complex KW
    """

    out = {}
    for kw in merged:
        # check if KW matches forbidden pattern
        kwstring = repr(" ".join(kw))
        if debug:
            print "KWSTRING:", kwstring
        if [kwstring for fp in patterns.keys()if re.search(fp,
                                                           kwstring,
                                                           re.U)]:
            if debug:
                print "MATCHED:", kwstring
            continue
        # check if one token KW is in forbidden list
        if len(kw) == 1 and kw[0] in postwords:
            if debug:
                print "POSTFILTERED:", kw[0]
            continue
        # check length limit
        if len(kw) > maxmember:
            continue

        out[kw] = merged[kw]

    return out


def main():
    """
    Read input and do everything if standalone.
    """

    if args.spark:
        # one line/json input, similar output
        for line in infile:
            entry = json.loads(line)
            sys.stdout.write('{0}\n'.format(
                json.dumps(process_spark_entry(entry))))
    elif args.oneline:
        # one line/json input, standalone output for testing
        for line in infile:
            entry_unit = json.loads(line)
            entry_id, entry = entry_unit
            if 'description_text_nlp' not in entry:
                continue
            if 'description' in entry:
                print "TEXT:", entry['description'].encode('utf-8')
            nlp_entry = entry['description_text_nlp']
            process_entries(nlp_entry, stopwords, lemma,
                            poslist, threshold, tr_ratio,
                            toprank, textlength)
            print '=' * 24
    else:
        # standalone with all entries in one json file
        for nlp_entry in read_json(infile):
            print '=' * 24
            process_entries(nlp_entry, stopwords, lemma,
                            poslist, threshold, tr_ratio,
                            toprank, textlength)


if __name__ == '__main__':
    main()
