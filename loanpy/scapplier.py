# -*- coding: utf-8 -*-
"""
This module provides tools for predicting and analyzing changes in the
horizontal or vertical transfer of words. It includes the
Adrc class, which supports the adaptation and reconstruction of words based
on sound and prosodic correspondences and inventories. The module also
contains functions for repairing phonotactics.

Horizontal transfer refers to the borrowing of words
between languages in contact, while vertical transfer refers to the
inheritance of words from a parent language to its descendants.
"""

import heapq
import re
from collections import OrderedDict
from itertools import cycle, product
from json import load
from pathlib import Path
from typing import Dict, Iterable, List, Tuple, Union

from loanpy.utils import prod

class Adrc():
    """
    Adapt or Reconstruct (ADRC) class.

    This class provides functionality for automatically
    adapting or reconstructing words of a language,
    based on sound and prosodic correspondences and inventories.
    Inputs are generated by ``loanpy.scminer``.

    :param sc: The path to the sound-correspondence json-file containing the
               list of six dictionaries, outputted by
               ``loanpy.scminer.get_correspondences``
    :type sc: str or pathlike object, optional

    :param prosodic_inventory: Path to the prosodic inventory json-file.
    :type prosodic_inventory: str or pathlike object, optional

    .. code-block:: python

        >>> from loanpy.scapplier import Adrc
        >>> adrc = Adrc("examples/sc2.json", "examples/inv.json")
        >>> adrc.sc
        [{'d': ['d', 't'], 'a': ['a', 'o']},
         {'d d': 5, 'd t': 4, 'a a': 7, 'a o': 1},
         {},
         {'CVCV': ['CVC']}]
        >>> adrc.prosodic_inventory
        ['CV', 'CVV']
    """

    def __init__(
            self, sc: Union[str, Path] = "", prosodic_inventory: Union[str, Path] = ""
            ) -> None:
        """
        Constructor for the ADRC class.

        :param sc: Path to the sound correspondence dictionary file.
        :type sc: str, optional

        :param prosodic_inventory: Path to the CVCV and phoneme inventories file.
        :type prosodic_inventory: str, optional
        """

        self.sc = None
        self.prosodic_inventory = None
        self.workflow = None  # will be filled by self.adapt()
        if sc:
            with open(sc, "r", encoding='utf-8') as f:
                self.sc = load(f) #  sound correspondence dictionaries
        if prosodic_inventory:
            with open(prosodic_inventory, "r", encoding='utf-8') as f:
                self.prosodic_inventory = load(f) # CVCV and phoneme inventories

    def set_sc(self, sc: List[dict]) -> None:
        """
        Method to set sound correspondences manually.
        Called by loanpy.eval_sca.eval_one

        :param sc: The sound correspondence dictionary file.
        :type sc: list

        :return: Set the attribute sc
        :rtype: None

        .. code-block:: python

            >>> from loanpy.scapplier import Adrc
            >>> adrc = Adrc("examples/sc2.json", "examples/inv.json")
            >>> adrc.set_sc("lol")
            >>> adrc.sc
            'lol'
        """
        self.sc = sc

    def set_prosodic_inventory(self, prosodic_inventory: List[str]) -> None:
        """
        Method to set the phonotactic prosodic_inventory manually.
        Called by loanpy.eval_sca.eval_one

        :param prosodic_inventory: The phonotactic prosodic_inventory file.
        :type sc: list of strings

        :return: Set the attribute prosodic_inventory
        :rtype: None

        .. code-block:: python

            >>> from loanpy.scapplier import Adrc
            >>> adrc = Adrc("examples/sc2.json", "examples/inv.json")
            >>> adrc.set_prosodic_inventory("rofl")
            >>> adrc.prosodic_inventory
            'rofl'
        """
        self.prosodic_inventory = prosodic_inventory

    def adapt(self,
              ipastr: Union[str, List[str]],
              howmany: int = 1,
              prosody: str = ""
              ) -> str:
        """
        Predict the adaptation of a loanword in a target recipient language.

        :param ipastr: Space-separated tokenised input IPA string.
        :type ipastr: str

        :param howmany: Number of adapted words to return. Default is 1.
        :type howmany: int

        :param prosody: Prosodic structure of the adapted words (e.g. "CVCV").
                        Default is an empty string. Providing this triggers
                        phonotactic repair.
        :type prosody: str of 'C' and 'V'

        :return: A list containing possible loanword adaptations.
        :rtype: list of str

        .. code-block:: python

            >>> from loanpy.scapplier import Adrc
            >>> adrc = Adrc("examples/sc2.json", "examples/inv.json")
            >>> adrc.adapt("d a d a")
            ['dada']
            >>> adrc.adapt("d a d a", 5)
            ['dada', 'data', 'doda', 'dota', 'tada']
            >>> adrc.adapt("d a d a", 5, "CVCV")  # sc2.json says CVCV to CVC
            ['dad', 'dat', 'dod', 'dot', 'tad']
            >>> adrc.adapt("d a d", 5, "CVC")   # no info on CVC in sc2.json
            ['da', 'do', 'ta', 'to']
            # closest in inventory is "CV"
        """

        ipalist = ipastr.split(" ") if isinstance(ipastr, str) else ipastr
        if prosody:
            ipalist = self.repair_phonotactics(ipalist, prosody)
        out = self.read_sc(ipalist, howmany)
        out = ["".join(word).replace("-", "") for word in product(*out)]
        return out[:howmany]  # cut off leftover, turn to string

    def reconstruct(self,
                    ipastr: str,
                    howmany: int = 1,
                    ) -> str:
        """
        Reconstructs a phonological form from a given IPA string using
        a sound correspondence dictionary.

        :param ipastr: A string of space-separated IPA symbols representing
                       the phonetic form to be reconstructed.
        :type ipastr: str

        :param howmany: The maximum number of phonological forms to
                        return. Default is 1.
        :type howmany: int

        :return: A string of reconstructed phonological forms that match the
                 given IPA string, based on the sound correspondence
                 dictionary.
        :rtype: str

        :raises ValueError: If any of the IPA symbols in the input string are
                            missing from the sound correspondence dictionary.

        .. code-block:: python

            >>> from loanpy.scapplier import Adrc
            >>> adrc = Adrc("examples/sc2.json", "examples/inv.json")
            >>> adrc.reconstruct("d a d a")
            '^(d)(a)(d)(a)$'
            >>> adrc.reconstruct("d a d a", 1000)
            '^(d|t)(a|o)(d|t)(a|o)$'
            >>> adrc.reconstruct("l a l a")
            'l not old'

        """

        ipalist = ipastr.split(" ") if isinstance(ipastr, str) else ipastr

        # if phonemes missing from sound correspondence dict, return which ones
        if not all(phon in self.sc[0] for phon in ipalist):
            missing = [i for i in ipalist if i not in self.sc[0]]
            return ', '.join(set(missing)) + " not old"

        # read the correct number of sound correspondences per phoneme
        out = self.read_sc(ipalist, howmany)

        out = ''.join([list2regex(i) for i in out if i != ['-']])
        return "^" + out + "$"  # regex

    def repair_phonotactics(self,
                            ipalist: List[str],
                            prosody: str
                            ) -> List[str]:
        """
        Repairs the phonotactics (prosody) of an IPA string.

        :param ipalist: A list of IPA symbols representing the input word.
        :type ipalist: list of str

        :param prosody: A string representing the prosodic structure of the
                        input word.
        :type prosody: str

        :return: A list of repaired IPA strings.
        :rtype: list of str

        .. code-block:: python

            >>> from loanpy.scapplier import Adrc
            >>> adrc = Adrc("examples/sc2.json", "examples/inv.json")
            >>> adrc.repair_phonotactics(["d", "a", "d", "a"], "CVCV")
            ['d', 'a', 'd']
        """

        # check if there is data available data for this structure
        try:
            predicted_phonotactics = self.sc[3][prosody][0]
        except KeyError:
            predicted_phonotactics = self.get_closest_phonotactics(prosody)
        #print("predicted phonotactics: ", predicted_phonotactics)
        # Get edit operations between structures, apply them 2 input IPA string
        matrix = get_mtx(prosody, predicted_phonotactics)
        graph = mtx2graph(matrix)
        end = (len(matrix)-1, len(matrix[0])-1)
        path = dijkstra(graph=graph, start=(0, 0), end=end)
        editops = tuples2editops(path, prosody, predicted_phonotactics)
        return apply_edit(ipalist, editops)

    def get_diff(
            self, sclistlist: List[List[str]], ipa: List[str]
            ) -> List[int]:
        """
        Computes the difference in the number of examples between the current
        and the next sound correspondences for each phoneme or cluster in a
        word.

        :param sclistlist: A list of sound correspondence lists.
        :type sclistlist: list

        :param ipa: A list of IPA symbols representing the word.
        :type ipa: list

        :return: A list of differences between the number of examples for each
                 sound correspondence in the input word.
        :rtype: list

        .. code-block:: python

            >>> from loanpy.scapplier import Adrc
            >>> adrc = Adrc()
            >>> adrc.set_sc([{}, {"k k": 2, "k c": 1, "i e": 2, "i o": 1}, {}, {}, {}, {}, {}])
            >>> sclistlist = [["k", "c", "$"], ["e", "o", "$"], ["k", "c", "$"], ["e", "o", "$"]]
            >>> adrc.get_diff(sclistlist, ["k", "i", "k", "i"])
            [1, 1, 1, 1]
        """

        # difference in nr of examples between current and next sound corresp
        # for each phoneme or cluster in a word
        difflist = []  # this will be returned
        # loop through phonemes/clusters of word
        for idx, sclist in enumerate(sclistlist):
            # get nr of occurences of current sound corresp (0 if not in dict)
            firstsc = self.sc[1].get(ipa[idx] + " " + sclist[0], 0)
            # check for two exceptions:
            if len(sclist) == 2:  # exception 1: if list has reached the end...
                # ... it can never be moved again. Bc nth bigger than inf.
                difflist.append(float("inf"))  # = stop button
                continue  # check next phoneme
            # exception 2: no data avail. ~ nr of occurences == 0 ~ heuristics
            # don't loop through heuristics before all data available used
            if firstsc == 0:
                difflist.append(9999999)  # = pause/freeze button...
                continue  # ... can be unfrozen by inf (= end of list)

            # get nr of occurences of next sound corresp (0 if no data avail.)

            nextsc = self.sc[1].get(ipa[idx] + " " + sclist[1], 0)
            # append diffrnc between current & next sound corresp to outputlist
            difflist.append(firstsc - nextsc)

        return difflist

    def read_sc(self, ipa: List[str], howmany: int = 1) -> List[List[str]]:
        """
        Replaces every phoneme of a word with a list of phonemes
        that it can correspond to. The next phoneme it picks is
        always the one that makes the least difference in terms
        of absolute frequency.

        :param ipa: a tokenized/clusterized word
        :type ipa: list

        :param howmany: The desired number of possible combinations.
                        This is the false positive rate if the prediction
                        is wrong but the false positive rate -1 if the
                        prediction is right.
        :type howmany: int, default=1

        :return: The information about which sounds each input sound can
                 correspond to.
        :rtype: list of lists

        .. code-block:: python

            >>> from loanpy.scapplier import Adrc
            >>> adrc = Adrc()
            >>> adrc.set_sc([{"k": ["k", "h"], "i": ["e", "o"]},
            ...              {"k k": 5, "k c": 3, "i e": 2, "i o": 1},
            ...              {}, {}, {}, {}, {}])
            >>> sclistlist = [["k", "c", "$"], ["e", "o", "$"], ["k", "c", "$"], ["e", "o", "$"]]
            >>> adrc.read_sc(["k", "i"], 2)
            [['k'], ['e', 'o']]
            # difference between i e and i o = 2 - 1 = 1
            # and between k k and k c = 5 - 3 = 2
            # so picking the "o" makes less of a difference than the "c"
        """

        # pick all sound correspondences from dictionary
        sclistlist = [self.sc[0][i] for i in ipa]
        # if howmany is bigger/equal than their product, return all of them.
        if howmany >= prod([len(scl) for scl in sclistlist]):
            return sclistlist
        # else add a stop sign to the end of each sound corresp list
        sclistlist = [sclist+["$"] for sclist in sclistlist]
        # pick only 1st (=most likely/frequent) sound corresp for each phoneme
        out = [[i[0]] for i in sclistlist]
        # decide which sound corresp to accept next. Stop if product reached
        while howmany > prod([len(scl) for scl in out]):
            # get by how much each new sound corresp would diminish the nse
            difflist = self.get_diff(sclistlist, ipa)  # e.g. [0, 0, 1, 2]
            minimum = min(difflist)  # how much is lowest possible difference?
            # get list index for all phonemes making the least difference.
            indices = [i for i, v in enumerate(difflist) if v == minimum]
            if len(indices) == 1:  # if only 1 element makes least difference
                sclistlist, out = move_sc(sclistlist, indices[0], out)  # Use!
                continue  # jump up to while and check if product is reached
            # but if multiple elements are the minimum...
            difflist2 = difflist  # ...remember the differences they make, ...
            idxpool = cycle(indices)  # ... and cycle through them...
            while (difflist2 == difflist and  # ... until diffs change, or:
                   howmany > prod([len(scl) for scl in out])):  # ">" (!)
                # pick next sound correspondence
                sclistlist, out = move_sc(sclistlist, next(idxpool), out)
                # check the differences all phonemes would make
                difflist2 = self.get_diff(sclistlist, ipa)
                # latest if a sound hits end of list: turns 2 inf, breaks loop

        return out

    def get_closest_phonotactics(self, struc: str) -> str:
        """
        Get the closest prosodic structure (e.g. "CVCV") from the
        prosodic inventory of a given language based on edit distance
        with two operations.

        :param struc: The phonotactic structure to compare against.
        :type struc: str

        :return: The closest prosodic structure (e.g. "CVCV") in
        the prosodic inventory.
        :rtype: str

        .. code-block:: python

            >>> from loanpy.scapplier import Adrc
            >>> adrc = Adrc("examples/sc2.json", "examples/inv.json")
            >>> adrc.get_closest_phonotactics("CVC")
            'CV'
            >>> adrc.get_closest_phonotactics("CVCV")
            'CVV'
        """

        dist_and_strucs = [
            (edit_distance_with2ops(struc, i), i) for i in self.prosodic_inventory
            ]

        return min(dist_and_strucs)[1]


def move_sc(
        sclistlist: List[List[str]], whichsound: int, out: List[List[str]]
        ) -> Tuple[List[List[str]], List[List[str]]]:
    """
    Moves a sound correspondence from the input list to the output
    list and updates both lists.

    :param sclistlist: A list of lists containing sound correspondences.
    :type sclistlist: list of lists

    :param whichsound: The index of the sound to be moved.
    :type whichsound: int

    :param out: The output list where the sound correspondence will be
                moved to.
    :type out: list of lists

    :return: An updated tuple containing the modified sclistlist and out.
    :rtype: tuple of (list of lists, list of lists)

    .. code-block:: python

        >>> from loanpy.scapplier import move_sc
        >>> move_sc([["x", "x"]], 0, [[]])
        ([['x']], [['x']])
        >>> move_sc([["x", "x"], ["y", "y"], ["z"]], 1, [["a"], ["b"], ["c"]])
        ([['x', 'x'], ['y'], ['z']], [['a'], ['b', 'y'], ['c']])
    """

    out[whichsound].append(sclistlist[whichsound][1])  # move sound #1 to out
    sclistlist[whichsound].pop(0)  # move input by 1 (remove sound #0)
    return sclistlist, out  # tuple

def edit_distance_with2ops(
        string1: str,
        string2: str,
        w_del: Union[int, float] = 100,
        w_ins: Union[int, float] = 49
        ) -> Union[int, float]:
    """
    Called by loanpy.scapplier.Adrc.get_closest_phonotactics.
    Takes two strings and calculates their similarity by
    only allowing two operations: insertion and deletion.
    In line with the "Threshold Principle" `(Paradis and LaCharité 1997:
    385) <http://www.jstor.com/stable/4176422>`_ \

    :param string1: The first of two strings to be compared to each other
    :type string1: str

    :param string2: The second of two strings to be compared to each other
    :type string2: str

    :param w_del: weight (cost) for deleting a phoneme. Default should
                  always stay 100, since only relative costs between inserting
                  and deleting count.
    :type w_del: int or float, default=100

    :param w_ins: weight (cost) for inserting a phoneme. Default 49
                  is in accordance with the "Threshold Principle":
                  2 insertions (2*49=98) are cheaper than a deletion (100).
    :type w_ins: int or float, default=49.

    :returns: The distance between two input strings
    :rtype: int or float

    .. code-block:: python

        >>> from loanpy.scapplier import edit_distance_with2ops
        >>> edit_distance_with2ops("rajka", "ajka", w_del=100, w_ins=49)
        100
        >>> edit_distance_with2ops("ajka", "rajka", w_del=100, w_ins=49)
        49
        >>> edit_distance_with2ops("Bécs", "Pécs", w_del=100, w_ins=49)
        149
        >>> edit_distance_with2ops("Hegyeshalom", "Mosonmagyaróvár", w_del=100, w_ins=49)
        1388

    """

    m = len(string1)     # Find longest common subsequence (LCS)
    n = len(string2)
    L = [[0 for x in range(n + 1)]
         for y in range(m + 1)]
    for i in range(m + 1):
        for j in range(n + 1):
            if (i == 0 or j == 0):
                L[i][j] = 0
            elif (string1[i - 1] == string2[j - 1]):
                L[i][j] = L[i - 1][j - 1] + 1
            else:
                L[i][j] = max(L[i - 1][j],
                              L[i][j - 1])

    lcs = L[m][n]
    # Edit distance is delete operations + insert operations*0.49.
    # costs (=distance) are lower for insertions
    return (m - lcs) * w_del + (n - lcs) * w_ins

def apply_edit(word: Iterable[str], editops: List[str]) -> List[str]:
    """
    Called by loanpy.scapplier.Adrc.repair_phonotactics.
    Applies a list of human readable edit operations to a string.

    :param word: The input word
    :type word: an iterable (e.g. list of phonemes, or string)

    :param editops: list of (human readable) edit operations
    :type editops: list or tuple of strings

    :returns: transformed input word
    :rtype: list of str

    .. code-block:: python

        >>> from loanpy.scapplier import apply_edit
        >>> apply_edit(
        ...       ['f', 'ɛ', 'r', 'i', 'h', 'ɛ', 'ɟ'],
        ...       ('insert d',
        ...        'insert u',
        ...        'insert n',
        ...        'insert ɒ',
        ...        'insert p',
        ...        'substitute f by ɒ',
        ...        'delete ɛ',
        ...        'keep r',
        ...        'delete i',
        ...        'delete h',
        ...        'delete ɛ',
        ...        'substitute ɟ by t')
        ... )
        ['d', 'u', 'n', 'ɒ', 'p', 'ɒ', 'r', 't']
    """

    out, letter = [], iter(word)
    for i, op in enumerate(editops):
        if i != len(editops):  # to avoid stopiteration
            if "keep" in op:
                out.append(next(letter))
            elif "delete" in op:
                next(letter)
        if "substitute" in op:
            out.append(op[op.index(" by ") + 4:])
            if i != len(editops) - 1:
                next(letter)
        elif "insert" in op:
            out.append(op[len("insert "):])
    return out

def list2regex(sclist: List[str]) -> str:
    """
    Called by loanpy.scapplier.Adrc.reconstruct.
    Turns a list of phonemes into a regular expression.

    :param sclist: a list of phonemes
    :type sclist: list of str

    :returns: The phonemes from the input list separated by a pipe. "-" is
              removed and replaced with a question mark at the end.
    :rtype: str

    .. code-block:: python

        >>> from loanpy.scapplier import list2regex
        >>> list2regex(["b", "k", "-", "v"])
        '(b|k|v)?'
    """

    s = ")?" if "-" in sclist else ")"
    out = "|".join([i.replace(".", "") for i in sclist if i != "-"])
    return "(" + out + s

def tuples2editops(
        op_list: List[Tuple[int, int]], s1: str, s2: str
        ) -> List[str]:
    """
    Called by loanpy.scapplier.editops.
    The path how string1 is converted to string2 is given in form of tuples
    that contain the x and y coordinates of every step through the matrix
    shaped graph.
    This function converts those numerical instructions to human readable
    ones.
    The x values stand for horizontal movement, y values for vertical ones.
    Vertical movement means deletion, horizontal means insertion.
    Diagonal means the value is kept.
    Moving horizontally and vertically after each other means
    substitution.

    :param op_list: The numeric list of edit operations
    :type op_list: list of tuples of 2 int

    :param s1: The first of two strings to be compared to each other
    :type s1: str

    :param s2: The second of two strings to be compared to each other
    :type s2: str

    :returns: list of human readable edit operations
    :rtype: list of strings

    .. code-block:: python

        >>> from loanpy.scapplier import tuples2editops
        >>> tuples2editops([(0, 0), (0, 1), (1, 1), (2, 2)], "ló", "hó")
        ['substitute l by h', 'insert ó']
        >>> tuples2editops([(0, 0), (1, 1), (2, 2), (2, 3)], "lóh", "ló")
        ['keep l', 'keep ó', 'delete h']

    """

    s1, s2 = "#" + s1, "#" + s2
    out = []
    for i in range(1, len(op_list)):
        # where does the arrow point?
        direction = [op_list[i][0] - op_list[i - 1][0],
                     op_list[i][1] - op_list[i - 1][1]]
        if direction == [1, 1]:  # if diagonal
            out.append(f"keep {s1[op_list[i][1]]}")
        elif direction == [0, 1]:  # if horizontal
            out.append(f"delete {s1[op_list[i][1]]}")
        elif direction == [1, 0]:  # if vertical
            out.append(f"insert {s2[op_list[i][0]]}")

    return substitute_operations(out)

def substitute_operations(operations: List[str]) -> List[str]:
    """
    Replaces subsequent "delete, insert" / "insert, delete" operations with
    "substitute". Called by loanpy.apply.tuples2editops.

    :param operations: A list of human readable edit operations
    :type operations: List of strings, e.g. ['insert l', 'delete h', 'keep ó']

    :returns: Updated operations
    :rtype: List of strings, e.g. ['substitute l by h', 'keep ó']

    .. code-block:: python

        >>> from loanpy.scapplier import substitute_operations
        >>> substitute_operations(['insert A', 'delete B', 'insert C'])
        ['substitute B by A', 'insert C']
        >>> substitute_operations(['delete A', 'insert B', 'delete C', 'insert D'])
        ['substitute A by B', 'substitute C by D']

    """

    i = 0
    while i < len(operations) - 1:
        if (operations[i].startswith('delete ') and
                operations[i+1].startswith('insert ')):
            x = operations[i][7:]
            y = operations[i+1][7:]
            operations[i:i+2] = [f'substitute {x} by {y}']
        elif (operations[i].startswith('insert ') and
                operations[i+1].startswith('delete ')):
            x = operations[i][7:]
            y = operations[i+1][7:]
            operations[i:i+2] = [f'substitute {y} by {x}']
        else:
            i += 1
    return operations

def get_mtx(target: Iterable, source: Iterable) -> List[List[int]]:
    """
    Called by loanpy.scapplier.Adrc.repair_phonotactics. Similar to
    loanpy.scapplier.edit_distance_with2ops but without
    weights (i.e. deletion and insertion
    both always cost one) and the matrix is returned.
    Draws a matrix of minimum edit distances between every substring of two
    input strings.

    :param target: The target word
    :type target: iterable, e.g. str or list

    :param source: The source word
    :type source: iterable, e.g. str or list

    :returns: A matrix where every cell tells the cost of turning one
              substring to the other (only delete and insert with cost 1 for
              both)
    :rtype: list of lists

    .. code-block:: python

        >>> from loanpy.scapplier import get_mtx
        >>> get_mtx("Bécs", "Pécs")
        [[0, 1, 2, 3, 4],
         [1, 2, 3, 4, 5],
         [2, 3, 2, 3, 4],
         [3, 4, 3, 2, 3],
         [4, 5, 4, 3, 2]]
        # What happens under the hood:
        # deletion costs 1, insertion costs 1, so the distances are:
        # B C D E  # hashtag stands for empty string
        # 0 1 2 3 4  # distance B-#=1, BC-#=2, BCD-#=3, BCDE-#=4
        # D 1 2 3 2 3  # distance D-#=1, D-B=2, D-BC=3, D-BCD=2, D-BCDE=3
        # E 2 3 4 3 2  # distance DE-#=2, DE-B=3, DE-BC=4, DE-BCD=3, DE-BCDE=2
        # the min. edit distance from BCDE-DE=2: delete B, delete C

    .. seealso::
        `YouTube tutorial by Rylan Fowers
        <https://www.youtube.com/watch?v=AY2DZ4a9gyk>`_
    """

    # build matrix of correct size
    target = ['#'] + [k for k in target]  # add hashtag as starting value
    source = ['#'] + [k for k in source]  # starting value is always zero

    # matrix consists of zeros at first. sol stands for solution.
    sol = [[0 for _ in range(len(target))] for _ in range(len(source))]

    # first row of matrix is 1,2,3,4,5,... as long as the target word is
    sol[0] = [j for j in range(len(target))]

    # first column is also 1,2,3,4,5....  as long as the source word is
    for j in range(len(source)):
        sol[j][0] = j

    # Add anchor value
    if target[1] != source[1]:  # if first letters of the 2 words r different
        sol[1][1] = 2  # set the first value (upper left corner) to 2
    # else it just stays zero

    # loop through the indexes of the two words with a nested loop
    for c in range(1, len(target)):
        for r in range(1, len(source)):
            if target[c] != source[r]:  # when the two letters are different
                # pick minimum of the 2 boxes to the left and above and add 1
                sol[r][c] = min(sol[r - 1][c], sol[r][c - 1]) + 1
            else:  # but if the letters are different
                # pick the letter diagonally up left
                sol[r][c] = sol[r - 1][c - 1]

    # returns the entire matrix. min edit distance in bottom right corner jff.
    return sol

def add_edge(
        graph: Dict[Tuple[int, int], List[Tuple[int, int, int]]],
        u: Tuple[int, int],
        v: Tuple[int, int],
        weight: int
        ) -> None:
    """
    Add an edge to a graph. Called by loanpy.scapplier.mtx2graph.

    :param graph: The graph to be populated
    :type graph: dict

    :param u: Position of the starting node
    :type u: Tuple of two integers, e.g. (0, 0)

    :param v: Position of the ending node
    :type v: Tuple of two integers, e.g. (0, 1)

    :param weight: The weigt of the edge connecting the two nodes
    :type weight: int

    :return: Updates the graph in-place
    :rtype: None

    .. code-block:: python

        >>> from loanpy.scapplier import add_edge
        >>> graph = {'A': {'B': 3}}
        >>> add_edge(graph, 'A', 'C', 7)
        >>> graph
        {'A': {'B': 3, 'C': 7}}

    """

    if u not in graph:
        graph[u] = {}
    graph[u][v] = weight

def mtx2graph(
        matrix: List[List[int]],
        w_del: int = 100,
        w_ins: int = 49
        ) -> Dict[Tuple[int, int], Dict[Tuple[int, int], int]]:
    """
    Converts a distance-matrix to a weighted directed graph

    :param matrix: The distance matrix, generated by loanpy.apply.get_mtx.
    :type matrix: A list of list of integers

    :w_del: Weight of deletions. According to the Theory of Constraints and
            Repair Strategies (TCRS), two insertions are cheaper than one
            deletion. Therefore, the weight of deletions, i.e. moving
            horizontally through the matrix, is set to 49 by default.
    :w_ins: Weight of insertions. Set to 100 by default, so that two
            insertions
            (2*49=98) are still cheaper than a deletion.

    :returns: A directed graph with weighted edges
    :rtype: dictionary with tuples as keys and dictionaries as values.
            The value-dictionaries contain tuples as keys and weights
            (integers) as values.
            All tuples contain two integers that represent the position
            of a node in the matrix/graph, e.g. (0, 0).

    .. code-block:: python

        >>> from loanpy.scapplier import mtx2graph
        >>> mtx2graph([[0, 1, 2], [1, 2, 3], [2, 3, 2]])
        {(0, 0): {(0, 1): 100, (1, 0): 49},
         (0, 1): {(0, 2): 100, (1, 1): 49},
         (0, 2): {(1, 2): 49},
         (1, 0): {(1, 1): 100, (2, 0): 49},
         (1, 1): {(1, 2): 100, (2, 1): 49, (2, 2): 0},
         (1, 2): {(2, 2): 49},
         (2, 0): {(2, 1): 100},
         (2, 1): {(2, 2): 100},
         (2, 2): {}}

    """

    graph = {}
    rows, cols = len(matrix), len(matrix[0])

    for i in range(rows):
        for j in range(cols):
            current_node = (i, j)
            graph[current_node] = {}

            if j < cols - 1:  # Right neighbor
                weight = w_del if matrix[i][j + 1] != matrix[i][j] else 0
                graph[current_node][(i, j + 1)] = weight

            if i < rows - 1:  # Down neighbor
                weight = w_ins if matrix[i + 1][j] != matrix[i][j] else 0
                graph[current_node][(i + 1, j)] = weight

            if i < rows - 1 and j < cols - 1:  # Diagonal down-right neighbor
                weight = 0 if matrix[i + 1][j + 1] == matrix[i][j] else None
                if weight is not None:
                    graph[current_node][(i + 1, j + 1)] = weight

    return graph

def dijkstra(
        graph: Dict[Tuple[int, int], Dict[Tuple[int, int], int]],
        start: Tuple[int, int],
        end: Tuple[int, int]
        ) -> Union[List[Tuple[int, int]], None]:
    """
    Find the shortest path between two nodes in a weighted graph
    using Dijkstra's algorithm.

    Dijkstra's algorithm is an algorithm for finding the shortest path
    between two nodes in a weighted graph. It
    maintains a priority queue of nodes to be expanded and their tentative
    distances from the start node. The
    algorithm iteratively extracts the node with the minimum tentative
    distance from the priority queue and updates
    the tentative distances of its neighbors if a shorter path is found.

    :param graph: A dictionary representing the weighted graph, where each
                  key is a node and each value is a
                  dictionary representing its neighbors and edge weights.
    :type graph: dict
    :param start: The starting node.
    :type start: A tuple of two integers representing the node's position on
                 the x and y axis.
    :param end: The ending node.
    :type end: A tuple of two integers representing the node's position on
                 the x and y axis.
    :return: The shortest path between the start and end nodes,
             represented as a list of nodes in the order they are
             visited, or None if no path exists.
    :rtype: list or None
    :raises KeyError: If the start or end node is not in the graph.

    .. code-block:: python

        >>> from loanpy.scapplier import dijkstra
        >>> graph1 = {
        ...         'A': {'B': 1, 'C': 4},
        ...         'B': {'C': 2, 'D': 6},
        ...         'C': {'D': 3},
        ...         'D': {}
        ...     }
        >>> dijkstra(graph1, 'A', 'D')
        ['A', 'B', 'C', 'D']

    .. seealso::
        `Dijkstra's algorithm on Wikipedia
        <https://en.wikipedia.org/wiki/Dijkstra%27s_algorithm>`_
    """

    dist = {node: float('inf') for node in graph}
    dist[start] = 0
    queue = [(0, start)]
    path = {}

    while queue:
        current_dist, current_node = heapq.heappop(queue)

        if current_dist > dist[current_node]:
            continue

        for neighbor, weight in graph[current_node].items():
            new_dist = current_dist + weight

            if new_dist < dist[neighbor]:
                dist[neighbor] = new_dist
                path[neighbor] = current_node
                heapq.heappush(queue, (new_dist, neighbor))

    if end not in path:
        return None

    # Reconstruct the shortest path
    shortest_path = [end]
    while shortest_path[-1] != start:
        shortest_path.append(path[shortest_path[-1]])
    shortest_path.reverse()

    return shortest_path
