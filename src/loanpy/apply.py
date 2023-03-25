"""
This module provides tools for predicting and analyzing changes in the
horizontal or vertical transfer of words in languages. It includes the
Adrc class, which supports the adaptation and reconstruction of words based
on sound and prosodic correspondences and inventories. The module also
contains functions for repairing phonotactics, handling vowel harmony, and
working with IPA strings.

Horizontal transfer refers to the borrowing of words and linguistic features
between languages in contact, while vertical transfer refers to the inheritance
of words and linguistic features from a parent language to its descendants.
"""


from collections import OrderedDict
import heapq
from itertools import cycle, product
from json import load
from math import prod
import re

class Adrc():
    """
    Adapt or Reconstruct (ADRC) class.

    This class provides functionality for automatically
    adapting or reconstructing words of a language,
    based on sound and prosodic correspondences and inventories.
    Inputs are generated by loanpy.recover.

    :param sc: The tab separated correspondence dictionary file.
    :type sc: str, optional
    :param invs: Path to the prosodic and phoneme inventories file.
    :type invs: str, optional
    """

    def __init__(self, sc="", invs=""):
        """
        Constructor for the ADRC class.

        :param sc: Path to the sound correspondence dictionary file.
        :type sc: str, optional
        :param invs: Path to the CVCV and phoneme inventories file.
        :type invs: str, optional
        """
        self.sc = None
        self.invs = None
        self.workflow = None  # will be filled by self.adapt()
        if sc:
            with open(sc, "r") as f:
                self.sc = load(f) #  sound correspondence dictionaries
        if invs:
            with open(invs, "r") as f:
                self.invs = load(f) # CVCV and phoneme inventories


    def adapt(self,
              ipastr,
              howmany=1,
              prosody=""):
        """
        Adapt loanwords based on various parameters.

        :param ipastr: Space-separated tokenised input IPA string.
        :type ipastr: str
        :param howmany: Number of adapted words to return.
        :type howmany: int, optional, default: 1
        :param prosody: Prosodic structure, e.g. "CVCV"
        :type prosody: str, optional, default: ""
        :param phonotactics_filter: Whether to apply a phonotactics filter.
        :type phonotactics_filter: bool, optional, default: False
        :param repair_vowelharmony: Whether to repair vowel harmony.
        :type repair_vowelharmony: bool, optional, default: False
        :param max_repaired_phonotactics: Maximum number of repaired
                                          phonotactics.
        :type max_repaired_phonotactics: int, optional, default: 0
        :param max_paths2repaired_phonotactics: Maximum number of paths to
                                                repaired phonotactics.
        :type max_paths2repaired_phonotactics: int, optional, default: 1
        :param deletion_cost: Cost of deletion in the phonotactics repair
                              process.
        :type deletion_cost: int, optional, default: 100
        :param insertion_cost: Cost of insertion in the phonotactics
                               repair process.
        :type insertion_cost: int, optional, default: 49
        :param show_workflow: Whether to show the workflow information.
        :type show_workflow: bool, optional, default: False
        :return: A string containing the adapted loanwords, separated by
                 commas.
        :rtype: str
        """

        if prosody:
            out = self.repair_phonotactics(ipastr, prosody)
        out = self.read_sc(ipastr.split(" "), howmany)
        out = ["".join(word) for word in product(*out)]
        return ", ".join(out[:howmany])  # cut off leftover, turn to string

    def reconstruct(self,
                    ipastr,
                    howmany=1,
                    ):
        """
        Reconstructs a phonological form from a given IPA string using
        a sound correspondence dictionary.

        :param ipastr: A string of space-separated IPA symbols representing the
                       phonetic form to be reconstructed.
        :type ipastr: str
        :param howmany: The maximum number of phonological forms to
                        return, defaults to 1.
        :type howmany: int
        :param phonotactics_filter: If True, applies a phonotactics filter
                                    to the resulting forms. Defaults to False.
        :type phonotactics_filter: bool
        :param vowelharmony_filter: If True, applies a vowel harmony filter
                                    to the resulting forms. Defaults to False.
        :type vowelharmony_filter: bool
        :return: A string of reconstructed phonological forms that match
                 the given IPA string, based on the
                 sound correspondence dictionary.
        :rtype: str
        """

        ipalist = ipastr.split(" ")

        # apply uralign tags TODO: outsource to pre-processing.
        ipalist[0], ipalist[-1] = f"#{ipalist[0]}", f"{ipalist[-1]}#"
        ipalist = ipalist + ["-#"]

        # if phonemes missing from sound correspondence dict, return which ones
        if not all(phon in self.sc[0] for phon in ipalist):
            missing = [i for i in ipalist if i not in self.sc[0]]
            return ', '.join(missing) + " not old"

        # read the correct number of sound correspondences per phoneme
        out = self.read_sc(ipalist, howmany)

        out = ''.join([list2regex(i) for i in out if i != ['-']])
        return "^" + out + "$"  # regex

    def repair_phonotactics(self,
                            ipastr,
                            prosody
                            ):
        """
        Repairs the phonotactics (prosody) of an IPA string.

        :param ipalist: A list of IPA symbols representing the
                       input word.
        :type ipastr: list
        :param prosody: A string representing the
                        prosodic structure of the input word.
        :type prosody: str
        :param max_repaired_phonotactics: The maximum number of phonotactics
                                          structures to use for repairing.
        :type max_repaired_phonotactics: int, optional
        :param max_paths2repaired_phonotactics: The maximum number of different
                                                paths to consider when
                                                computing
                                                edit distances between
                                                phonotactics
                                                .
        :type max_paths2repaired_phonotactics: int, optional
        :param deletion_cost: The cost of deleting a phoneme during the
                              repair process.
        :type deletion_cost: int, optional
        :param insertion_cost: The cost of inserting a phoneme during the
                               repair process.
        :type insertion_cost: int, optional
        :param show_workflow: Whether to display the workflow for debugging
                              purposes.
        :type show_workflow: bool, optional
        :return: A list of repaired IPA strings.
        :rtype: list
        """

        # check if there is data available data for this structure
        try:
            predicted_phonotactics = self.sc[3][prosody][0]
        except KeyError:
            predicted_phonotactics = self.get_closest_phonotactics(prosody)

        # Get edit operations between structures, apply them 2 input IPA string
        matrix = get_mtx(prosody, predicted_phonotactics)
        graph = mtx2graph(matrix)
        end = (len(matrix)-1, len(matrix[0])-1)
        print("matrix:", matrix)
        print("end:", end)
        path = dijkstra(graph=graph, start=(0, 0), end=end)
        editops = tuples2editops(path, prosody, predicted_phonotactics)
        return apply_edit(ipastr, editops)

    def get_diff(self, sclistlist, ipa):
        """
        Computes the difference in the number of examples between the current
        and the next sound correspondences for each phoneme or cluster in a
        word.

        :param sclistlist: A list of sound correspondence lists.
        :type sclistlist: list
        :param ipa: A space-separated string of IPA symbols
                    representing the word.
        :type ipa: str
        :return: A list of differences between the number of examples for each
                 sound correspondence in the input word.
        :rtype: list
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

    def read_sc(self, ipa, howmany=1):
        """
        Replaces every phoneme of a word with a list of phonemes
        that it can correspond to, based on specified conditions.

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

    def get_closest_phonotactics(self, struc):
        """
        Ranks the closest phonotactic structures based on edit distance.

        :param struc: The phonotactic structure to compare against.
        :type struc: str
        :param howmany: The desired number of closest structures to return.
        :type howmany: int, default=9999999
        :return: A comma-separated string of the closest phonotactic structures.
        :rtype: str
        """
        dist_and_strucs = [
            (edit_distance_with2ops(struc, i), i)
            for i in self.invs["pros"]
        ]

        return min(dist_and_strucs)[1]


def move_sc(sclistlist, whichsound, out):
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

    """
    out[whichsound].append(sclistlist[whichsound][1])  # move sound #1 to out
    sclistlist[whichsound].pop(0)  # move input by 1 (remove sound #0)
    return sclistlist, out  # tuple

def edit_distance_with2ops(string1, string2, w_del=100, w_ins=49):
    """
    Called by loanpy.helpers.Etym.rank_closest_phonotactics and \
loanpy.qfysc.Qfy.get_phonotactics_corresp. \
Takes two strings and calculates their similarity by \
only allowing two operations: insertion and deletion. \
In line with the "Threshold Principle" by Carole Paradis and \
Darlene LaCharité (1997) \
the distance is weighted in a way that two insertions are cheaper than \
one deletion: "The problem is really not very different from the dilemma \
of a landlord stuck with a limited budget for maintenance and a building \
which no longer meets municipal guidelines. Beyond a certain point, \
renovating is not viable (there are too many steps to be taken) and \
demolition is in order. Similarly, we posit that I) languages have \
a limited budget for adapting ill- formed phonological structures, \
and that 2) the limit for the budget is universally set at two steps, \
beyond which a repair by 'demolition' may apply. In other words, we \
predict that a segment is deleted if (but only if) its rescue is too \
costly in terms of the Threshold Principle" (p.385, Preservation \
and Minimality \
in Loanword Adaptation, \
Author(s): Carole Paradis and Darlene Lacharité, \
Source: Journal of Linguistics , Sep., 1997, Vol. 33, No. 2 (Sep., 1997), \
pp. 379-430, \
Published by: Cambridge University Press, \
Stable URL: http://www.jstor.com/stable/4176422). \
The code is based on a post by ita_c on \
https://www.geeksforgeeks.org/edit-distance-and-lcs-longest-common-subsequence\
 (last access: June 8th, 2022)

    :param string1: The first of two strings to be compared to each other
    :type string1: str

    :param string2: The second of two strings to be compared to each other
    :type string2: str

    :param w_del: weight (cost) for deleting a phoneme. Default should \
always stay 100, since only relative costs between inserting and deleting \
count.
    :type w_del: int | float, default=100

    :param w_ins: weight (cost) for inserting a phoneme. Default 49 \
is in accordance with the "Threshold Principle": \
2 insertions (2*49=98) are cheaper than a deletion \
(100).
    :type w_ins: int | float, default=49.

    :returns: The distance between two input strings
    :rtype: int | float

    :Example:

    >>> from loanpy.helpers import edit_distance_with2ops
    >>> edit_distance_with2ops("hey","hey")
    0

    >>> from loanpy.helpers import edit_distance_with2ops
    >>> edit_distance_with2ops("hey","he")
    100

    >>> from loanpy.helpers import edit_distance_with2ops
    >>> edit_distance_with2ops("hey","heyy")
    49

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

def apply_edit(word, editops):
    """
    Called by loanpy.adrc.Adrc.repair_phonotactics. \
Applies a list of human readable edit operations to a string.

    :param word: The input word
    :type word: an iterable (e.g. list of phonemes, or string)

    :param editops: list of (human readable) edit operations
    :type editops: list or tuple of strings

    :returns: transformed input word
    :rtype: list of str

    :Example:

    >>> from loanpy.helpers import apply_edit
    >>> apply_edit(["l", "ó"], ('substitute l by h', 'keep ó'))
    ['h', 'ó']
    >>> apply_edit("ló", ('keep C', 'insert C', 'insert V', 'keep V'))
    ['l', 'C', 'V', 'ó']
    >>> apply_edit("ló", ('insert C', 'keep C', 'insert V', 'keep V'))
    ['C', 'l', 'V', 'ó']
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

def list2regex(sclist):
    """
    Called by loanpy.adrc.Adrc.reconstruct. \
Turns a list of phonemes into a regular expression.

    :param sclist: a list of phonemes
    :type sclist: list of str

    :returns: The phonemes from the input list separated by a pipe. "-" is \
removed and replaced with a question mark at the end.
    :rtype: str

    :Example:

    >>> from loanpy.helpers import list2regex
    >>> list2regex(["b", "k", "v"])
    '(b|k|v)'

    >>> from loanpy.helpers import list2regex
    >>> list2regex(["b", "k", "-", "v"])
    '(b|k|v)?'

    """

    s = ")?" if "-" in sclist else ")"
    return "(" + "|".join([i.replace(".", "") for i in sclist if i != "-"]) + s

def tuples2editops(op_list, s1, s2):
    """
    Called by loanpy.helpers.editops. \
The path how string1 is converted to string2 is given in form of tuples \
that contain the x and y coordinates of every step through the matrix \
shaped graph. \
This function converts those numerical instructions to human readable ones. \
The x values stand for horizontal movement, y values for vertical ones. \
Vertical movement means deletion, horizontal means insertion. \
Diagonal means the value is kept. \
Moving horizontally and vertically after each other means \
substitution.

    :param op_list: The numeric list of edit operations
    :type op_list: list of tuples of 2 int

    :param s1: The first of two strings to be compared to each other
    :type s1: str

    :param s2: The second of two strings to be compared to each other
    :type s2: str

    :returns: list of human readable edit operations
    :rtype: list of strings

    :Example:

    >>> from loanpy.helpers import tuples2editops
    >>> tuples2editops([(0, 0), (0, 1), (1, 1), (2, 2)], "ló", "hó")
    ['substitute l by h', 'keep ó']
    >>>  # What happened under the hood:
    # (0, 0), (0, 1): move 1 vertically = 1 deletion
    # (0, 1), (1, 1): move 1 horizontally = 1 insertion
    # insertion and deletion after each other equals substitution
    # (1, 1), (2, 2): move 1 diagonally = keep the sound

    """
    s1, s2 = "#" + s1, "#" + s2
    out = []
    for i in range(1, len(op_list)):
        # where does the arrow point?
        direction = [op_list[i][0] - op_list[i - 1][0], op_list[i][1] - op_list[i - 1][1]]
        if direction == [1, 1]:  # if diagonal
            out.append(f"keep {s1[op_list[i][1]]}")
        elif direction == [0, 1]:  # if horizontal
            out.append(f"delete {s1[op_list[i][1]]}")
        elif direction == [1, 0]:  # if vertical
            out.append(f"insert {s2[op_list[i][0]]}")

    return substitute_operations(out)

def substitute_operations(operations):
    i = 0
    while i < len(operations) - 1:
        if operations[i].startswith('delete ') and operations[i+1].startswith('insert '):
            x = operations[i][7:]
            y = operations[i+1][7:]
            operations[i:i+2] = [f'substitute {x} by {y}']
        elif operations[i].startswith('insert ') and operations[i+1].startswith('delete '):
            x = operations[i][7:]
            y = operations[i+1][7:]
            operations[i:i+2] = [f'substitute {y} by {x}']
        else:
            i += 1
    return operations



def get_mtx(target, source):
    """
    Called by loanpy.helpers.mtx2graph. Similar to \
loanpy.helpers.edit_distance_with2ops but without \
weights (i.e. deletion and insertion \
both always cost one) and the matrix is returned.

    From https://www.youtube.com/watch?v=AY2DZ4a9gyk. \
(Last access: June 8th, 2022) \
Draws a matrix of minimum edit distances between every substring of two \
input strings. The ~secret~ to fill the matrix: \
If two letters are not the same, look at the \
upper and left hand cell, pick the minimum and add one. If they are the same, \
pick the value from the upper left diagonal cell.

    :param target: The target word
    :type target: iterable, e.g. str or list

    :param source: The source word
    :type source: iterable, e.g. str or list

    :returns: A matrix where every cell tells the cost of turning one \
substring to the other (only delete and insert with cost 1 for both)
    :rtype: numpy.ndarray

    :Example:

    >>> from loanpy.helpers import get_mtx
    >>> get_mtx("bcde", "de")
    array([[0., 1., 2., 3., 4.],
       [1., 2., 3., 2., 3.],
       [2., 3., 4., 3., 2.]])
    >>>  # What in reality happened (example from video):
         # deletion costs 1, insertion costs 1, so the distances are:
      # B C D E  # hashtag stands for empty string
    # 0 1 2 3 4  # distance B-#=1, BC-#=2, BCD-#=3, BCDE-#=4
    D 1 2 3 2 3  # distance D-#=1, D-B=2, D-BC=3, D-BCD=2, D-BCDE=3
    E 2 3 4 3 2  # distance DE-#=2, DE-B=3, DE-BC=4, DE-BCD=3, DE-BCDE=2
    # the min. edit distance from BCDE-DE=2: delete B, delete C

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
    if target[1] != source[1]:  # if first letters of the 2 words are different
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

def add_edge(graph, u, v, weight):
    if u not in graph:
        graph[u] = {}
    graph[u][v] = weight

def mtx2graph(matrix, w_del=100, w_ins=49):

    graph = {}
    rows, cols = len(matrix), len(matrix[0])

    for i in range(rows):
        for j in range(cols):
            current_node = (i, j)
            graph[current_node] = {}

            if j < cols - 1:  # Right neighbor
                weight = 100 if matrix[i][j + 1] != matrix[i][j] else 0
                graph[current_node][(i, j + 1)] = weight

            if i < rows - 1:  # Down neighbor
                weight = 49 if matrix[i + 1][j] != matrix[i][j] else 0
                graph[current_node][(i + 1, j)] = weight

            if i < rows - 1 and j < cols - 1:  # Diagonal down-right neighbor
                weight = 0 if matrix[i + 1][j + 1] == matrix[i][j] else None
                if weight is not None:
                    graph[current_node][(i + 1, j + 1)] = weight

    return graph

    return graph

def dijkstra(graph, start, end):
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
