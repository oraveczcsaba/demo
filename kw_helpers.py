# coding: utf-8
"""
Collection of some utils for kw extraction.

@Author: oraveczcsaba
"""

import sys
import itertools


def load_stopwords(file):
    """ (file) -> dict

    Return dict of words from file.
    """
    stop_words = {}
    for line in open(file):
        if line.strip()[:1] != "#":
            for word in line.split():
                stop_words[word] = stop_words.get(word, 0) + 1

    return stop_words


def unique(seq):
    # Order preserving
    seen = set()
    return [x for x in seq if x not in seen and not seen.add(x)]


def isNumeric(s):
    try:
        float(s) if '.' in s else int(s)
        return True
    except ValueError:
        return False


def printout(dict, reverse=True):
    """(dict) -> None

    Prints out input dict reverse value sorted.
    """

    for key in sorted(dict, key=dict.get, reverse=reverse):
        sys.stdout.write('{0}\t{1}\n'.format(key, dict[key]))


def neighbours(debug,
               pdict,
               sent_dict,
               ph_token,
               ph_index,
               allowed,
               testing,
               threshold=2,
               gap=1):
    """ (int, dict, dict, dict, int?, int?) -> dict

    Return dict of phrase tuples which occur next to each other at least
    threshold number of times. Key value is combined score.
    Arguments:
    - pdict: dict of phrase tuples containing their score
    - sent_dict: the position indexed sentence dictionary
    - ph_token: dictionary of phrase tuples of their positional indexes
    - ph_index: dict of positional indeces of
      ((phrase_tuple), firstwordindex, lastwordinex)
    - testing: if 1 switch off intertoken filter
    - threshold: number of times phrases must be adjacent to each other
    - gap: number of tokens allowed in between two adjacent units
    """

    neighbours = {}
    complex_phrases = {}
    # build neighbour dictionary for complex candidates
    for phrase in pdict:
        for index in ph_token[phrase]:
            if debug:
                write_out(("CHECKING:", phrase, "with index", index))
            if index + 1 >= len(ph_index):
                if debug:
                    write_out(("LAST MEMBER, NO NEXT UNIT",))
                continue
            if ph_index[index+1][0] in pdict:
                if debug:
                    write_out(("NEIGHBOUR:", ph_index[index+1][0]))
                # check index diff <= gap (+1)
                # store also the intermediate tokens as part of index
                # because they must be the same to count as a fixed phrase!
                diff = ph_index[index+1][1] - ph_index[index][2]
                # the index diff must be leq than gap but > 1!
                # (otherwise we collect tokens originally separated by
                # punctuation!)
                if diff <= gap + 1 and diff > 1:
                    inter = tuple([sent_dict[i][0].lower() for i
                                   in range(ph_index[index][2]+1,
                                            ph_index[index+1][1])])
                    if debug:
                        write_out(("INTOK:", inter))
                    # at least one token must intervene!
                    if check_inter(inter, allowed, testing):
                        unit = (phrase,
                                ph_index[index+1][0],
                                inter)
                        neighbours[unit] = neighbours.get(unit, 0) + 1
                        if debug:
                            write_out(("ADDING", unit))

    for nb in neighbours:
        if neighbours[nb] >= threshold:
            # we have a new complex KW!
            ckw = tuple(itertools.chain.from_iterable((nb[0],
                                                       nb[2],
                                                       nb[1])))
            complex_phrases[ckw] = combine_scores(neighbours[nb],
                                                  pdict[nb[0]],
                                                  pdict[nb[1]])
            if debug:
                write_out(("CKW:", neighbours[nb],
                           ckw,
                           combine_scores(neighbours[nb],
                                          pdict[nb[0]],
                                          pdict[nb[1]])))

    return complex_phrases


def post_textrank(initdict, phrase_list):
    """ (dict, list) -> dict

    Return a dict of rejoined keywords.
    """

    collapsed = []
    score = 0.0
    textranked = {}
    # iterate through the phrase list and collapse seq of adjacent KWs
    for phrase in phrase_list:
        for word in phrase:
            if word in initdict:
                collapsed.append(word)
                score += initdict[word]
            else:
                if score:
                    textranked[tuple(collapsed)] = score
                    collapsed = []
                    score = 0
        # end of phrase, so add to output
        if score:
            textranked[tuple(collapsed)] = score
            collapsed = []
            score = 0

    return textranked


def merge_dict(dict1, dict2):
    """ (dict, dict) -> dict

    Return a dictionary by merging the input dictionaries taking their
    value ranked lists and combining them. Returned dictionary contains
    the ranks as values.
    """

    # Simple merge: if key present in both dicts, its value
    # gets the sum of its ranks from both, if present only in one then
    # gets rank in one + shift
    # ('shift' currently is the average length of the input dicts)
    out = {}
    shift = (len(dict1) + len(dict2)) / 2
    rdict1 = make_ranks(dict1)
    rdict2 = make_ranks(dict2)
    # nasty bugfix: need to make a copy of original dict1 because
    # we need it later
    dict1_copy = dict(dict1)
    dict1_copy.update(dict2)
    for key in dict1_copy:
        if key in rdict1 and key in rdict2:
            out[key] = rdict1[key] + rdict2[key]
        else:
            rank = rdict1[key] if key in rdict1 else rdict2[key]
            out[key] = rank + shift
    return out


def make_ranks(indict):
    """ (dict) -> dict

    Return a dict where values are transformed into ranks.
    """

    out = {}
    rank = 1
    prank = 1
    pvalue = 0
    for key in sorted(indict, key=indict.get, reverse=True):
        value = indict[key]
        if value == pvalue:
            # it's a tie so assign same rank
            out[key] = prank
        else:
            out[key] = rank
            prank = rank
        rank += 1
        pvalue = value
    return out


def topranked(indict, plist, limit, ratio=2):
    """ (dict, list, int, int) -> dict

    Return a dictionary of the first N elements by value form the input dict.
    N is len(plist)/ratio. If limit is < N, N is set to limit.
    """
    head = len(list(itertools.chain.from_iterable(plist))) / ratio
    if head > limit:
        head = limit
    fullist = [(key, indict[key]) for key in sorted(indict,
                                                    key=indict.get)]
    return dict(fullist[:head])


def combine_scores(freq, *args):
    total = 0
    for i in args:
        total += i
    return freq * total


def check_inter(inter, allowed, testing):
    """ tuple -> bool

    Return true if input tuple satisfies test.
    Input is a tuple of word(s) that apperar(s) in between KW candidates.
    """

    if testing:
        return True

    for token in inter:
        if token not in allowed:
            return False
    return True


def write_out(seq):
    """ (list) -> None

    Print out input arg.
    """

    print " ".join([str(x) for x in seq])


if __name__ == "__main__":
    print >> sys.stderr, "Help functions for KW extraction."
