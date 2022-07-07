"""
Quantify sound correspondences from etymological data.
"""

from ast import literal_eval
from collections import Counter
from functools import partial
from pathlib import Path

from ipatok import clusterise
from lingpy.align.pairwise import Pairwise
from lingpy.sequence.sound_classes import token2class
from numpy import isnan
from pandas import DataFrame, concat, read_csv
from panphon import __file__ as path2panphon
from panphon.distance import Distance
from tqdm import tqdm

from loanpy.helpers import clusterise, tokenise, edit_distance_with2ops, pick_minmax

class WrongModeError(Exception):
    """Raised in loanpy.qfysc.read_mode if mode is neither \
"adapt" nor "reconstruct" nor None/""/False/[]/0/ etc"""
    pass

class Etym:
    """
    Read etymological data and customise the way in which to \
quantify it. Has 9 parameters and initiates 12 attributes.

    These 5 params will be passed on to loanpy.helpers.Etym \
to inherit its 8 attributes:

    :param forms_csv: The path to CLDF's forms.csv. For more details see \
loanpy.helpers.read_forms, loanpy.helpers.cldf2pd and \
loanpy.helpers.forms2list. If set to None, no etymological data will be read.
    :type forms_csv: pathlib.PosixPath | str | None, default=None

    :param source_language: The computational source language \
(can differ from linguistic \
source). This is the data **from** which predictions are made. \
For more details see loanpy.helpers.cldf2pd.
    :type source_language: str (options are listed in column "ID" in \
cldf / etc / languages.tsv), default=None

    :param target_language: The computational target language \
(can again differ from \
linguistic one). This is the language **into** which predictions are made. \
For more details see loanpy.helpers.cldf2pd.
    :type target_language: str (options are listed in column "ID" in \
cldf / etc / languages.tsv), default=None

    :param most_frequent_phonotactics: The n most frequent structures \
to accept into the phonotactic inventory of the \
target language. \
Sometimes a good idea \
to omit rare ones. For more details see loanpy.helpers.read_phonotactic_inv.
    :type most_frequent_phonotactics: int, default=9999999

    :param phonotactic_inventory: All possible phonotactic \
structures in the target \
language. Will be extracted from target language if set to None. \
For more details \
see loanpy.helpers.Etym.read_phonotactic_inv.
    :type phonotactic_inventory: None | set | list, default=None

    These 4 params are used in own __init__ function to define 4 attributes:

    :param mode: The mode in which sound correspondences will be \
extracted. Differences between the two modes: Different connectors, \
source and target gets flipped, different alignment. No phonotactic \
correspondences extracted if mode="reconstruct". \
Flows into attribute loanpy.qfysc.Qfy.mode. \
For more details see loanpy.qfysc.read_mode.
    :type mode: "adapt" | "reconstruct", default="adapt"

    :param connector: The strings that connect the linguistic (!) source word \
with the target adapted or reconstructed one. \
Flows into attribute loanpy.qfysc.Qfy.connector. Set to None if \
default settings ("<" and "<\*") should be used. For more details see \
loanpy.qfysc.read_connector.
    :type connector: tuple, default=None

    :param scdictbase: The sound correspondence dictionary base, \
a heuristic approach \
for predicting sound substitutions. loanpy.qfysc.Qfy.get_sound_corresp \
will combine sound substitutions gathered from etymological data with \
this dictionary. If combination should be skipped, set to None or {}. \
Flows into attribute loanpy.qfysc.Qfy.scdictbase. \
For more details see loanpy.helpers.Etym.get_scdictbase.
    :type scdictbase: None | dict | pathlib.PosixPath, default=None

    :param vfb: Placeholders for "any vowel", "any front vowel", "any \
back vowel", as these can occur in etymological dictionaries. \
Tokeniser can only handle IPA-characters. Therefore, placeholders \
have to be IPA-characters as well. Best is to choose IPA-characters that \
don't occur in the phoneme inventory. By default, no placeholders \
are used. For a list \
of available ipa characters see ipa_all.csv's column "ipa"
    :type vfb: None | iterable, default=None, example: "əœʌ"

    :Example:

    >>> from pathlib import Path
    >>> from loanpy.qfysc import Qfy, __file__
    >>> path2forms = Path(__file__).parent / "tests" \
/ "input_files" / "forms.csv"
    >>> qfy_obj = Qfy(mode="reconstruct", connector=["from", "from *"], \
scdictbase={"a": ["e", "o"], "b": ["p", "v"]}, vfb="əœʌ")
    >>> qfy_obj.mode
    "reconstruct"
    >>> qfy_obj.connector
    'from *'
    >>> qfy_obj.scdictbase
    {"a": ["e", "o"], "b": ["p", "v"]}
    >>> qfy_obj.vfb
    'əœʌ'
    >>> len(qfy_obj.__dict__)  # 4 own +7 attributes inherited \
from loanpy.helpers.Etym
    12

    """
    def __init__(self,
                 # to inherit from loanpy.helpers.Etym
                 forms_csv=None,
                 source_language=None,
                 target_language=None,
                 # to define here.
                 mode="adapt",  # or: "reconstruct"
                 connector=None,  # will automatically get defined
                 scdictbase=None,  # big file, so not generated every time
                 distance_measure="weighted_feature_edit_distance",
                 vfb=None):  # etymological data sometimes has placeholders
                    # for "any vowel", "any front vowel", or "any back vowel".
                    # Those have to be designated by ipa characters that are
                    # not used in the language. Because the tokeniser
                    # accepts only IPA-characters.
        self.mode = read_mode(mode)
        self.connector = read_connector(connector, mode)
        self.scdictbase = read_scdictbase(scdictbase)
        self.vfb = vfb
        self.distance_measure = read_dst(distance_measure)
        # read data frame forms, turn words of target language to list
        # conclude dfety from dff
        self.dfety = cldf2pd(forms_csv, source_language, target_language)
        # do NOT extract self.inventories this from dfety but from forms.csv
        # b/c dfety extracts only from cogset where src and tgt lg are present
        self.inventories = get_inventories(forms_csv, target_language)

    def get_sound_corresp(self, write_to=None):

        """
        Convert an etymological dictionary to a dictionary of sound (cluster) \
and phonotactic correspondences, \
their number of occurrences, and IDs of cognate sets in which they occur. \
If loanpy.qfysc.Qfy.mode=="reconstruct" phonotactic correspondences \
will not be extracted \
because that dimension is already captured through the alignment. \
Since loanpy.adrc.Adrc.adapt does not capture this, phonotactic \
correspondences need to be extracted from the data to \
later repair the structures \
before substituting. This has to do with the different nature of lateral \
vs horizontal transfers: loanwords meet certain constraints immediately \
and need to be repaired immediately. While historical sound changes happen \
over a long period of time. (If there was an optimality theory based \
model with constraint-changes for historical \
linguistics, vertical predictions with loanpy.adrc.Adrc.adapt would \
be possible.)

        :param write_to: Indicate if results should be written to a \
text file. If yes, provide the path. None means that no file will be written.
        :type write_to: None | pathlib.PosixPath | str, default=None

        :returns: list of 6 dicts. Dicts 0, 1, 2 capture phonological \
correspondences, dicts 3, 4, 5 phonotactic ones. dict0/dict3: the actual \
correspondences, dict1/dict4: How often each \
correspondence occurs in the data, \
dict2/dict5: list of cognates in which each correspondence occurs. \
Dicts 4, 5, 6 will be empty if loanpy.qfysc.Qfy.mode=="reconstruct". \
Set mode in \
loanpy.qfysc.Qfy. Note: dictionary 5 contains some randomness because set() \
is involved, for details see loanpy.qfysc.Qfy.get_phonotactics_corresp.
        :rtype: [dict, dict, dict, dict, dict, dict]

        :Example:

        >>> from pathlib import Path
        >>> from loanpy.qfysc import Qfy, __file__
        >>> path2forms = Path(__file__).parent / "tests" \
/ "input_files" / "forms.csv"
        >>> qfy_obj = Qfy(forms_csv=path2forms, \
source_language=1, target_language=2)
        >>> qfy_obj.get_sound_corresp()
        [{'C': ['x'], 'a': ['y'], 'b': [''], \
'c': ['z']}, {'C<b': 1, 'x<C': 1, \
'y<a': 1, 'z<c': 1}, {'C<b': [1], 'x<C': [1], 'y<a': [1], 'z<c': [1]}, \
{'VCC': ['CVC']}, {'CVC<VCC': 1}, {'CVC<VCC': [1]}]

        >>>  # now reconstruct instead of adapt, and write file
        >>> from ast import literal_eval
        >>> from os import remove
        >>> path2scdict = Path(__file__).parent / "example_scdict2delete.txt"
        >>> qfy_obj = Qfy(forms_csv=path2forms, \
source_language=1, target_language=2, mode="reconstruct")
        >>> qfy_obj.get_sound_corresp(write_to=path2scdict)
        [{'#x': ['-'], '-#': ['-'], 'y': ['a'], 'z#': ['bc']}, \
{'#x<*-': 1, '-#<*-': 1, 'y<*a': 1, 'z#<*bc': 1}, \
{'#x<*-': [1], '-#<*-': [1], 'y<*a': [1], 'z#<*bc': [1]}, {}, {}, {}]
        >>> literal_eval(open(path2scdict, "r", encoding="utf-8").read())
        [{'#x': ['-'], '-#': ['-'], 'y': ['a'], 'z#': ['bc']}, \
{'#x<*-': 1, '-#<*-': 1, 'y<*a': 1, 'z#<*bc': 1}, \
{'#x<*-': [1], '-#<*-': [1], 'y<*a': [1], 'z#<*bc': [1]}, {}, {}, {}]
        >>> remove(path2scdict)

        """

        soundchange = []
        wordchange = []
        # align every word and append it to a list of data frames for concat
        #define type of tokenisation depending on self.mode
        tgtsrs, srcsrs = (
        self.dfety["Segments_tgt"], self.dfety["Segments_src"]
        ) if self.mode == "adapt" else (
        self.dfety["CV_Segments_tgt"], self.dfety["CV_Segments_src"])

        #start looping through source-target word pairs
        for left, right, cog in zip(tgtsrs, srcsrs, self.dfety["Cognacy"]):
            dfalign = self.align(left, right)
            soundchange.append(dfalign)
            wordchange += [cog]*len(dfalign)  # col 3 after concat

        dfsoundchange = concat(soundchange)  # one big df of sound corresp
        # cognate set where it happened
        dfsoundchange["wordchange"] = wordchange
        dfsoundchange["e"] = 1  # every sound corr. occurs once. will be added

        # flip keys and vals if adapting!
        # important! since backwards predictions for rc
        if self.mode == "adapt":
            dfsoundchange["soundchange"] = (dfsoundchange["vals"] +
                                            self.connector +
                                            dfsoundchange["keys"])
            #  join source&target with connector
        else:
            dfsoundchange["soundchange"] = (dfsoundchange["keys"] +
                                            self.connector +
                                            dfsoundchange["vals"])
            # join source and target with connector

# create the first 3 elements of the output from the big df of sound corresp
# create 1st element of output. Sort correspondence list by frequency
        dfsc = dfsoundchange.groupby("keys")["vals"].apply(
            lambda x: [n[0] for n in Counter(x).most_common()]).reset_index()
# create 2nd element of output. Sum up how often each corresp occurred
        dfse = dfsoundchange.groupby("soundchange")["e"].sum().reset_index()
# create 3rd elem. of output. List up cognate sets where each corresp occurred
        dfe = dfsoundchange.groupby("soundchange")[
            "wordchange"].apply(lambda x: sorted(set(x))).reset_index()

# turn the 3 pandas dataframes into dictionaries
        scdict = dict(zip(dfsc["keys"], dfsc["vals"]))
        sedict = dict(zip(dfse["soundchange"], dfse["e"]))
        edict = dict(zip(dfe["soundchange"], dfe["wordchange"]))

# insert placeholder vowels. This was necessary for uralic data.
        if self.vfb:  # "əœʌ"
            for i in scdict:
                if (any(self.phon2cv.get(j, "") == "V" for j in scdict[i]) and
                        self.vfb[0] not in scdict[i]):
                    scdict[i].append(self.vfb[0])
                    if (any(self.vow2fb.get(j, "") == "F"
                            for j in scdict[i]) and
                            self.vfb[1] not in scdict[i]):
                        scdict[i].append(self.vfb[1])
                    if (any(self.vow2fb.get(j, "") == "B"
                            for j in scdict[i]) and
                            self.vfb[2] not in scdict[i]):
                        scdict[i].append(self.vfb[2])

# in loanpy.qfysc.Qfy.align_lingpy "C" and "V" instead of "-" used
# to mark that a sound disappeared. So has to be removed here again.
        if self.mode == "adapt":
            for k in scdict:
                scdict[k] = ["" if j == "C" or j == "V" else j
                             for j in scdict[k]]
# if adapting, merge data with heuristics
            # loop through keys of both dicts combined
            for i in self.scdictbase | scdict:
                # combine keys that are in both
                if i in self.scdictbase and i in scdict:
                    scdict[i] = list(dict.fromkeys(scdict[i] +
                                                   self.scdictbase[i]))
                # if key missing from scdict but is in scdictbase
                elif i in self.scdictbase:
                    scdict[i] = self.scdictbase[i]  # then add it to scdict
# like this it is ensured that no non-ipa chars are taken

        out = [scdict, sedict, edict]  # first 3 elements of output
        # the other 3 are only generated if adapting
        out += self.get_phonotactics_corresp() if self.mode == "\
adapt" else [{}, {}, {}]

        if write_to:  # write to file if indicated so
            with open(write_to, "w", encoding="utf-8") as data:
                data.write(str(out))

        return out  # always return the output

    def get_phonotactics_corresp(self, write_to=None):

        """
        Called by loanpy.qfysc.Qfy.get_sound_corresp. \
Similar to loanpy.qfysc.get_sound_corresp but here, no alignment \
is needed. Just capture which phonotactic profile turns into which \
in the data, how often that happens and in which cognate sets.

        :param write_to: Indicate if results should be written to a \
text file. If yes, provide the path. None means that no file will be written.
        :type write_to: None | pathlib.PosixPath | str, default=None

        :returns: list of 3 dicts that capture phonotactic correspondences, \
how often each correspondence occurs in the data and in which cognate sets \
each correspondence occurs.
        :rtype: [dict, dict, dict]

        :Example:

        >>> from pathlib import Path
        >>> from loanpy.qfysc import Qfy, __file__
        >>> path2forms = Path(__file__).parent / "tests" \
/ "input_files" / "forms.csv"
        >>> qfy_obj = Qfy(forms_csv=path2forms, source_language=1, \
target_language=2)
        >>> qfy_obj.get_phonotactics_corresp()
        [{'VCC': ['CVC']}, {'CVC<VCC': 1}, {'CVC<VCC': [1]}]

        >>>  # now reconstruct instead of adapt, and write file
        >>> from ast import literal_eval
        >>> from os import remove
        >>> path2scdict = Path(__file__).parent / "example_scdict2delete.txt"
        >>> qfy_obj = Qfy(forms_csv=path2forms, source_language=1, \
target_language=2, mode="reconstruct")
        >>> qfy_obj.get_phonotactics_corresp(write_to=path2scdict)
        [{'VCC': ['CVC']}, {'VCC<*CVC': 1}, {'VCC<*CVC': [1]}]
        >>> literal_eval(open(path2scdict, "r", encoding="utf-8").read())
        [{'VCC': ['CVC']}, {'VCC<*CVC': 1}, {'VCC<*CVC': [1]}]
        >>> remove(path2scdict)

        """
        # create one big data frame out of structural changes
        # column three captures the cognate sets where the change happened
        dfstrucchange = DataFrame(zip(
        self.dfety["ProsodicStructure_src"],
        self.dfety["ProsodicStructure_tgt"],
        self.dfety["Cognacy"]),
                                  columns=["keys", "vals", "wordchange"])
        dfstrucchange["e"] = 1  # each change happened one time. add later.

        #  important to flip keys and vals if adapting!
        if self.mode == "adapt":
            dfstrucchange["strucchange"] = (dfstrucchange["vals"] +
                                            self.connector +
                                            dfstrucchange["keys"])
        else:
            dfstrucchange["strucchange"] = (dfstrucchange["keys"] +
                                            self.connector +
                                            dfstrucchange["vals"])

# create the first 3 elements of the output from the big df of sound corresp
# create 1st element of output. Sort correspondence list by frequency
        dfsc = dfstrucchange.groupby("keys")[
            "vals"].apply(lambda x: [n[0]
                          for n in Counter(x).most_common()]).reset_index()
# create 2nd element of output. Sum up how often each corresp occurred
        dfse = dfstrucchange.groupby("strucchange")["e"].sum().reset_index()
# create 3rd elem. of output. List up cognate sets where each corresp occurred
        dfe = dfstrucchange.groupby("strucchange")["wordchange"].\
            apply(list).reset_index()

# turn the dataframes to dictionaries
        scdict = dict(zip(dfsc["keys"], dfsc["vals"]))
        sedict = dict(zip(dfse["strucchange"], dfse["e"]))
        edict = dict(zip(dfe["strucchange"], dfe["wordchange"]))

# merge data with heuristics: sort phonotactic inventory
# by similarity to each structure
# and append it to the data.
        for i in scdict:  # this involves some randomness:
            # rank_closest picks a random struc if 2 are equally close!
            scdict[i] = list(dict.fromkeys(
                scdict[i] + self.rank_closest_phonotactics(i).split(", ")))

        if write_to:  # write file if indicated so
            with open(write_to, "w", encoding="utf-8") as data:
                data.write(str([scdict, sedict, edict]))

        return [scdict, sedict, edict]  # return list of 3 dictionaries

    def get_scdictbase(self, write_to=None):
        """
        Call manually in the beginning. \
Loop through ipa_all.csv and rank most similar phonemes \
from phoneme_inventory. \
Could also turn ipa_all.csv into a square of 6358*6358 phonemes and just use \
that file for all future cases but that would use an estimated 500MB per \
type of distance measure. So more economical to calculate it this way. \
Will still, depending on size of phoneme inventory, \
take up about 2MB. \
The result is returned, assigned to loanpy.helpers.Etym.scdictbase \
and optionally also written. \
Usually there is very little data available \
on sound substitutions and the ones available give only very small insight \
into all possibilities. \
The idea here is therefore that any sound \
that is not contained in a language's phoneme inventory \
will be replaced by \
the most similar available one(s). The available sound substitutions \
based on etymological data can optionally be combined with \
this heuristics in a way that heuristics are only \
applied if for a particular sound (cluster) no more data is available any more.

        :param write_to: If or where the output should be written.
        :type write_to: None | pathlib.PosixPath | str, default=None

        :param most_common: Add only this many most similar phonemes to \
scdictbase. By default, the entire phoneme inventory will be ranked.
        :type most_common: int | float, default=float("inf")

        :returns: A heuristic approach to sound substitution in loanword \
adaptation
        :rtype: dict

        :Example:

        >>> from pathlib import Path
        >>> from loanpy.helpers import Etym, __file__
        >>> etym_obj = Etym(forms_csv=Path(__file__).parent / "tests" / \
"integration" / "input_files" / "forms.csv", source_language=1, \
target_language=2)
        >>> etym_obj.get_scdictbase()
        (returns the entire dictionary with phoneme_inventory \
ranked according to similarity)
        >>> etym_obj.scdictbase["i"]
        ["y", "x", "z"]
        """

        ipa_all = read_csv(Path(path2panphon).parent / "data" / "ipa_all.csv")
        ipa_all["substi"] = [self.rank_closest(ph)
                             for ph in tqdm(ipa_all["ipa"])]
        scdictbase = dict(zip(ipa_all["ipa"],
                              ipa_all["substi"].str.split(", ")))

        for cv in "CV":  # add "C" and "V" to scdictbase, most unmarked
            scdictbase[cv] = [i for i in scdictbase["ə"] if token2class(i, "cv") == cv]
        #add "F" and "B" to scdictbase (most umarked front and back vowels)
        scdictbase["F"] = [i for i in scdictbase["V"] if token2class(i, "asjp") in "ieE"]
        scdictbase["B"] = [i for i in scdictbase["V"] if token2class(i, "asjp") in "ou"]

        self.scdictbase = scdictbase

        if write_to:
            with open(write_to, "w", encoding="utf-8") as f:
                f.write(str(scdictbase))

        return scdictbase

    def rank_closest(self, ph, howmany=float("inf")):
        """
        Called by loanpy.helpers.Etym.get_scdictbase. \
Sort self.phoneme_inventory by distance to input-phoneme.

        :param ph: phoneme to which to rank the phoneme inventory
        :type ph: str (valid chars: col "ipa" in ipa_all.csv)

        :param howmany: howmany of the most similar phonemes to pick \
for the ranking.
        :type howmany: int | float("inf"), default=float("inf")

        :param inv: To plug in phoneme inventory manually if necessary
        :type inv: None | list | set, default=None

        :returns: the phoneme inventory \
ranked by similarity (most similar \
first)
        :rtype: str (elements separates by ", ")

        :Example:

        >>> from pathlib import Path
        >>> from loanpy.helpers import Etym, __file__
        >>> etym_obj = Etym()
        >>> etym_obj.rank_closest(ph="d", inv=["r", "t", "l"], howmany=1)
        't'
        >>> etym_obj = Etym(phoneme_inventory=["a", "b", "c"])
        >>> etym_obj.rank_closest(ph="d")
        'b, c, a'

        """
        try:
            phons_and_dist = [(i, self.distance_measure(ph, i))
            for i in self.inventories["Segments"]]
        except TypeError:
            return None
        return ", ".join(pick_minmax(phons_and_dist, howmany))

    # DONT merge this func into rank_closest. It makes things more complicated
    def rank_closest_phonotactics(self, struc, howmany=9999999):
        """
        Called by loanpy.qfysc.Qfy.get_phonotactics_corresp. \
Sort loanpy.helpers.Etym.phonotactic_inventory by distance to given \
phonotactic structure using loanpy.helpers.edit_distance_with2ops \
(cost for insertion: 49, cost for deletion: 100).

        :param struc: The phonotactic structure to which \
to rank the phoneme_inventory
        :type struc: str (consisting of "C"s and "V"s only)

        :param howmany: How many of the most similar \
profiles should be picked
        :type howmany: int | float("inf"), default=float("inf")

        :param inv: To plug in the phonotactic inventory \
manually if necessary
        :type inv: None | list | set, default=None

        :returns: the phonotactic inventory ranked \
by similarity (most similar \
first)
        :rtype: str (elements separates by ", ")

        >>> from pathlib import Path
        >>> from loanpy.helpers import Etym, __file__
        >>> etym_obj = Etym(phonotactic_inventory=\
["CVC", "CVCVV", "CCCC", "VVVVVV"])
        >>> etym_obj.rank_closest_phonotactics(struc="CVCV", howmany=1)
        'CVCVV'
        >>> etym_obj = Etym()
        >>> etym_obj.rank_closest_phonotactics(struc="CVCV", howmany=3,\
inv=["CVC", "CVCVV", "CCCC", "VVVVVV"])
        "CVCVV, CVC, CCCC"

        """

        strucs_and_dist = [(i, edit_distance_with2ops(struc, i))
        for i in self.inventories["ProsodicStructure"]]
        return ", ".join(pick_minmax(strucs_and_dist, howmany))

    def align(self, left, right):
        """
        Called by loanpy.qfysc.Qfy.get_sound_corresp. \
Selects alignment with lingpy if adapting and its own alignment \
if reconstructing. The alignment function/wrapper can be looked up at \
loanpy.qfysc.Qfy.align_lingpy and loanpy.qfysc.Qfy.align_clusterwise

        :param left: The string on the left side of the etymology to align.
        :type left: str

        :param right: The string on the right side of the etymology to align.
        :type right: str

        Note: In an earlier version, some additional \
parameters were passed on to \
lingpy.align.pairwise.Pairwise and \
lingpy.align.pairwise.Pairwise.align. \
That feature is not supported in the current version \
because they bloat the script and \
find only little practical use at the moment. If necessary, \
they have to be inserted \
directly in the source code, where Pairwise() gets initiated and \
Pairwise.align() called.

        :returns: a pandas data frame with \
two columns named "keys" and "vals" \
with one phoneme (cluster) and its aligned counterpart in each row.
        :rtype: pandas.core.frame.DataFrame

        :Example:

        >>> from loanpy.qfysc import Qfy
        >>> qfy_obj = Qfy()  # default mode is "adapt", so lingpy aligns
        >>> qfy_obj.align("budapest", "budimpeʃta")
          keys vals
        0    b    b
        1    u    u
        2    d    d
        3    i    a
        4    m    C
        5    p    p
        6    e    e
        7    ʃ    s
        8    t    t
        9    a    V


        >>> qfy_obj = Qfy(mode="reconstruct")  # use own alignment
        >>> qfy_obj.align("budapest", "budimpeʃta")
          keys vals  # left&right col is flipped b/c source&target is flipped
        0   #-    -
        1   #b    b
        2    u    u
        3    d    d
        4    a    i
        5    p   mp
        6    e    e
        7  st#   ʃt
        8   -#    a
        """

        if self.mode == "reconstruct":
            return self.align_clusterwise(left, right)
        elif self.mode == "adapt":
            return self.align_lingpy(left, right)

    def align_lingpy(self, left, right):
        """
        Called by loanpy.qfysc.Qfy.align. \
Initiate a lingpy.align.pairwise.Pairwise object with the two strings \
to align. Turn the resulting string into two lists and insert them into two \
columns of a pandas data frame. \
The columns are called "keys" and "vals" because these \
are going to be the future keys and values in the \
sound correspondence dictionary. \
This alignment \
is intended for predicting loanword adaptation. Therefore the keys are equal \
to the phonemes of the donor word, which usually stands on the right side \
in traditional etymological notation (e.g. in "kiki<hihi" "hihi" is \
the donor word). \
One difference to lingpy is that "-" for "no phoneme" is replace by "C" \
if the corresponding other sound is a consonant and "V" if it's a vowel.

        :param left: The word that stands on the left side of the connector
        :type left: str

        :param right: The word that stands on the right side of the connector
        :type right: str

        :returns: data frame where the phonemes of the word on the right \
go to the column on the left ("keys") because those are the phonemes \
to look up later in the sound correspondence dict to make predictions, i.e. \
computational source \
is on the right, target on the left. (An alternative \
solution for this problem \
would have been to flip the connector and have the computational source \
always on the left, already when inputting. But the problem with this is that \
the star would have to move \
in the reconstructions: "kiki<\*hihi" is ok but to flip this, \
left and right can't be just flipped and the connector mirrored because \
"hihi\*>kiki" would be wrong notation. It would have to be "\*hihi>kiki". \
And moving around this star is unexpectedly tricky. That's why the \
computational source is once on the left side, once on the right, and \
gets flipped internally.)
        :rtype: pandas.core.frame.DataFrame

        :Example:

        >>> from loanpy.qfysc import Qfy
        >>> qfy_obj = Qfy()
        >>> qfy_obj.align_lingpy("budapest", "budimpeʃta")
          keys vals
        0    b    b
        1    u    u
        2    d    d
        3    i    a
        4    m    C
        5    p    p
        6    e    e
        7    ʃ    s
        8    t    t
        9    a    V
        >>> qfy_obj.align_lingpy("budimpeʃta", "budapest")
          keys vals
        0    b    b
        1    u    u
        2    d    d
        3    a    i
        4    C    m
        5    p    p
        6    e    e
        7    s    ʃ
        8    t    t
        9    V    a

        """
        #all input types work here: "abc", "a b c", "a b.c", ["a", "b", "c"]
        pw = Pairwise(seqs=left, seqB=right, merge_vowels=False)
        pw.align()
        leftright = [pw.alignments[0][0], pw.alignments[0][1]]
        leftright[0] = ["C" if new == "-" and token2class(old, "cv") == "C"
                        else "V" if (new == "-" and
                                     token2class(old, "cv")) == "V"
                        else new for new, old in zip(leftright[0],
                                                     leftright[1])]
        leftright[1] = ["C" if old == "-" and token2class(new, "cv") == "C"
                        else "V" if (old == "-" and
                                     token2class(new, "cv")) == "V"
                        else old for new, old in zip(leftright[0],
                                                     leftright[1])]

        # the word on the right has to go into the keys
        # b/c it's the phonemes of the donor word (right) to look up
        # in the scdict later.
        return DataFrame({"keys": leftright[1], "vals": leftright[0]})

    def align_clusterwise(self, left, right):
        """
        Called by loanpy.qfysc.Qfy.align. Align with own formula: \
        1. split string into consonant and vowel clusters. \
        2. Tag first and last cluster with "#" to indicate its word initial \
        or word final position. \
        3. Add "#-" and "-#" to front and back of list of clusters \
        to capture affixes that might have disappeared or appeared. \
        4. If one string starts with a consonant and the other with a vowel, \
        shift the one \
        starting with a consonant by one, so that the first vowel cluster \
        serves as an anchor. \
        5. Sequentially align the upcoming clusters \
        with each other until the shorter \
        word ends. \
        6. Squeeze leftover phonemes into one string.

        :param left: The string on the left side of the connecting symbol \
        of an etymology, e.g. "kiki" if the etymology is "kiki<\*hihi".
        :type left: str

        :param right: The string on the right side of the connecting symbol \
        of an etymology, e.g. "kiki" if the etymology is "hihi<kiki".
        :type left: str

        :returns: data frame where the phonemes of the word on the left \
        go to the column on the left ("keys") because those are the phonemes \
        to look up later in the sound correspondence dict \
        to make predictions, \
        i.e. computational source \
        is on the left, target on the right.
        :rtype: pandas.core.frame.DataFrame

        :Example:

        >>> from loanpy.qfysc import Qfy
        >>> qfy_obj = Qfy()
        >>> qfy_obj.align_clusterwise("budapestt", "uadast")
        keys vals
        0     #b    -
        1      u   ua
        2      d    d
        3      a    a
        4      p   st
        5  estt#    -
        """
        keys, vals = left.split(" "), right.split(" ")

        # tag word initial and word final cluster_inventory, only in left word
        # only keys get this!
        keys[0], keys[-1] = "#" + keys[0], keys[-1] + "#"
        # create empty start character
        keys, vals = ["#-"] + keys, ["-"] + vals  # nut keys AND vals get this
        # if one starts with C and the other with V, move the C-cluster
        # into the empty start character created above
        # check if e.g. the "t͡ʃː" in ["#-", "#t͡ʃːr", "o"] is a "C" or a "V":
        # note that this almost never happens in our current data
        # only imad-vimad, öt-wöt, etc
        if (token2class(keys[1].split(".")[0].replace("#", ""), "cv") == "V" and
                token2class(vals[1].split(".")[0], "cv") == "C"):
            vals = vals[1:]
        # now check if e.g.
        # the "t͡ʃː" in ["-", "t͡ʃːr", "o"] (!) is a "C" or a "V":
        elif (token2class(tokenise(keys[1][1:])[0], "cv") == "C" and
                token2class(tokenise(vals[1])[0], "cv") == "V"):
              keys = keys[1:]

        # go sequentially and squeeze the leftover together to one suffix
        # e.g. "a,b","c,d,e,f,g->"a,b,-#","c,d,efg
        diff = abs(len(vals) - len(keys))
        if len(keys) < len(vals):
            keys += ["-#"]
            vals = vals[:-diff] + [" ".join(vals[-diff:])]
        elif len(keys) > len(vals):
            vals += ["-"]
            keys = keys[:-diff] + [" ".join(keys[-diff:])]
        else:
            keys, vals = keys + ["-#"], vals + ["-"]

        return DataFrame({"keys": keys, "vals": vals})

def cldf2pd(dfforms, source_language=None, target_language=None):
    """
    Called by loanpy.helpers.Etym.__init__; \
Converts a CLDF based forms.csv to a pandas data frame. \
Returns None if dfforms is None, so class can be initiated without args too. \
Runs through forms.csv and creates a new data frame the following way: \
Checks if a cognate set contains words from both, source and target language. \
If yes: word from source lg goes to column "Source_Form", \
word from target lg goes to column "Target_Form" and \
the number of the cognate set goes to column "Cognacy". \
Note that if a cognate set doesn't contain words from source and target \
language, \
that cognate set is skipped.

    :param dfforms: Takes the output of read_forms() as input
    :type dfforms: pandas.core.frame.DataFrame | None

    :param source_language: The language who's cognates go to \
column "Source_Forms"
    :type source_language: str, default=None

    :param target_language: The language who's cognates go to \
column "Target_Forms"
    :type target_language: str, default=None

    :returns: forms.csv data frame with re-positioned information
    :rtype: pandas.core.frame.DataFrame | None

    :Example:

    >>> from pathlib import Path
    >>> from loanpy.helpers import __file__, cldf2pd, read_forms
    >>> path2forms = Path(__file__).parent / "tests" \
/ "input_files" / "forms.csv"
    >>> forms = read_forms(path2forms)
    >>> cldf2pd(forms, source_language=1, target_language=2)
          Target_Form Source_Form  Cognacy
    0         xyz         abc        1

    """

    if dfforms is None:
        return None
    dfforms = read_csv(dfforms, usecols=["Segments", "CV_Segments",
                                         "Cognacy", "Language_ID",
                                         "ProsodicStructure"])
    dfetymology = {k: [] for k in[
    "Segments_tgt", "Segments_src",
    "CV_Segments_tgt", "CV_Segments_src",
    "ProsodicStructure_tgt", "ProsodicStructure_src",
    "Cognacy"
    ]}

    # bugfix: col Cognacy is sometimes empty. if so, fill it
    if all(isnan(i) for i in dfforms.Cognacy):
        dfforms["Cognacy"] = list(range(len(dfforms)))

    for cogid in range(1, int(list(dfforms["Cognacy"])[-1])+1):
        cogset = dfforms[dfforms["Cognacy"] == cogid]
        try:  # both src and tgt lg have to be present in cogset
            dfetymology["Segments_tgt"].append(cogset[cogset["Language_ID"
            ] == target_language].iloc[0]["Segments"])
            dfetymology["Segments_src"].append(cogset[cogset["Language_ID"
            ] == source_language].iloc[0]["Segments"])
            dfetymology["CV_Segments_tgt"].append(cogset[cogset["Language_ID"
            ] == target_language].iloc[0]["CV_Segments"])
            dfetymology["CV_Segments_src"].append(cogset[cogset["Language_ID"
            ] == source_language].iloc[0]["CV_Segments"])
            dfetymology["ProsodicStructure_tgt"].append(cogset[cogset[
            "Language_ID"] == target_language].iloc[0]["ProsodicStructure"])
            dfetymology["ProsodicStructure_src"].append(cogset[cogset[
            "Language_ID"] == source_language].iloc[0]["ProsodicStructure"])
            dfetymology["Cognacy"].append(cogid)
        except IndexError:
            continue

    return DataFrame(dfetymology)


def read_mode(mode):
    """
    Called by loanpy.qfysc.Qfy.__init__

    :param mode: The mode in which the data should be quantified. If set \
to "None", default mode jumps to "adapt". This option is useful if there \
is no time to think so all params are quickly set to None.
    :type mode: None | "adapt" | "reconstruct"

    :raises WrongModeError: The mode can only be "adapt" or "reconstruct"

    :returns: "adapt" | "reconstruct"
    :rtype: str

    :Example:

    >>> from loanpy.qfysc import read_mode
    >>> read_mode("adapt")
    "adapt"
    >>> read_mode("reconstruct")
    "reconstruct"
    >>> read_mode(None)
    "adapt"
    >>> read_mode("")
    "adapt"
    >>> read_mode("bla")
    loanpy.qfysc.WrongModeError: parameter <mode> \
must be 'adapt' or 'reconstruct'

    """
    if mode and mode not in ["adapt", "reconstruct"]:
        raise WrongModeError("parameter <mode> \
must be 'adapt' or 'reconstruct'")
    return mode if mode else "adapt"


def read_connector(connector, mode):
    """
    Called by loanpy.qfysc.Qfy.__init__

    :param connector: An iterable that defines the two symbols that connect \
the words on the left and the right side of the etymology when adapting \
vs. reconstructing. If None is passed, \
"<" is used for adapting and \
"<\*" for reconstructing.
    :type connector: iterable of str

    :param mode: the mode to choose the connector for, if "reconstruct", \
then the second element of the iterable will be chosen. If "adapt", the 1st.
    :type mode: "adapt" | "reconstruct"

    :returns: The string that connects the left and right side of an etymology.
    :rtype: str

    :Example:

    >>> from loanpy.qfysc import read_connector
    >>> read_connector(connector=None, mode="adapt")
    "<"
    >>> read_connector(connector=None, mode=None)
    "<"
    >>> read_connector(connector=None, mode="reconstruct")
    "<*"
    >>> read_connector(connector=(" from ", " from *"), mode="reconstruct")
    " from *"
    """

    if connector is None:
        connector = ("<", "<*")
    return connector[1] if mode == "reconstruct" else connector[0]


def read_scdictbase(scdictbase):
    """
    Called by loanpy.qfysc.Qfy.__init__

    :param scdictbase: The sound correspondence dictionary base. \
Has to be generated \
with loanpy.helpers.Etym.get_scdictbase first. Can be plugged in via a file, \
by directly providing a dictionary, or accessing loanpy.qfysc.Qfy.scdictbase \
(since loanpy.helpers.Etym.get_scdictbase always assigns the dictionary to \
its attribute scdictbase, which is then inherited by loanpy.qfysc.Qfy.) \
The preferred setting is to provide the path to the file, since \
it is rather large (~1.6MB) and should therefore be generated \
only once for any target language.
    :type scdictbase: None | pathlib.PosixPath | str

    :returns: A dictionary representing a heuristic approach to sound \
substitution. Returns empty dictionary if set to None. \
For more details see loanpy.helpers.Etym.get_scdictbase.
    :rtype: dictionary

    :Example:

    >>> from loanpy.qfysc import read_scdictbase
    >>> base = {"a": ["e", "o"], "b": ["p", "v"]}
    >>> read_scdictbase(base)  # plug in dictionary directly
    {"a": ["e", "o"], "b": ["p", "v"]}
    >>> from loanpy.qfysc import __file__
    >>> from pathlib import Path
    >>> from os import remove
    >>> path = Path(__file__).parent / "test_read_scdictbase.txt"
    >>> with open(path, "w", encoding="utf-8") as f: f.write(str(base))  \
# write test file
    >>> read_scdictbase(path)  # read dictionary from file
    {"a": ["e", "o"], "b": ["p", "v"]}
    >>> remove(path)  # delete the test file again

    """
    # needed by get_sound_corresp for substitutions
    if scdictbase is None:
        return {}
    if isinstance(scdictbase, dict):
        return scdictbase
    with open(scdictbase, "r", encoding="utf-8") as f:
        return literal_eval(f.read())

def get_inventories(dff, target_language):
    """
    Called by loanpy.helpers.Etym.__init__; \
Get a list of words of a language from a forms.csv file.

    :param dff: forms.csv data frame (cldf)
    :type dff: pandas.core.frame.DataFrame

    :param target_language: The language from which the phoneme, \
phoneme cluster and phonotactic inventories will be extracted.
    :type target_language: str

    :returns: a list of words in the target language
    :rtype: list | None

    :Example:

    >>> from pathlib import Path
    >>> from loanpy.helpers import __file__, forms2list, read_forms
    >>> path2forms = Path(__file__).parent / "tests" \
/ "input_files" / "forms.csv"
    >>> forms = read_forms(path2forms)
    >>> forms2list(forms, target_language=2)
    ['xyz']
    """
    if dff is None:
        return {}
    dff = read_csv(dff, usecols=["Segments", "CV_Segments",
                                 "Language_ID", "ProsodicStructure"])
    df_tgt = dff[dff["Language_ID"] == target_language]

    invdict = {}
    for col in ["Segments", "CV_Segments", "ProsodicStructure"]:
        invdict[col] = set()
        [invdict[col].update(i.split(" ")) for i in df_tgt[col]]

    return invdict

def read_dst(dst_msr):
    """
    Called by loanpy.helpers.Etym.__init__; \
Returns a function that calculates the phonological distance between strings \
from panphon.distance.Distance. This will be used to calculate the most \
similar phonemes of the phoneme inventory compared to \
a given phoneme from ipa_all.csv

    :param dst_msr: The name of the distance measure, which has to be \
a method \
of panphon.distance.Distance
    :type dst_msr: None, \
"doglo_prime_distance" | \
"dolgo_prime_distance_div_maxlen" | \
"fast_levenshtein_distance" | \
"fast_levenshtein_distance_div_maxlen" | \
"feature_difference" | \
"feature_edit_distance" | \
"feature_edit_distance_div_maxlen" | \
"hamming_feature_edit_distance" | \
"hamming_feature_edit_distance_div_maxlen" | \
"hamming_substitution_cost" | \
"jt_feature_edit_distance" | \
"jt_feature_edit_distance_div_maxlen" | \
"jt_hamming_feature_edit_distance" | \
"jt_hamming_feature_edit_distance_div_maxlen" | \
"jt_weighted_feature_edit_distance" | \
"jt_weighted_feature_edit_distance_div_maxlen" | \
"levenshtein_distance"

    :returns: a function that calculates the phonological distance between \
IPA-strings
    :rtype: function | None

    :Example:

    >>> from loanpy.helpers import read_dst
    >>> read_dst("fast_levenshtein_distance")
    <bound method Distance.fast_levenshtein_distance of \
<panphon.distance.Distance object at 0x7f7f21fe95b0>>

    For more information see PanPhon's documentation:

    >>> from panphon.distance import Distance
    >>> help(Distance)

    """
    return None if not dst_msr else getattr(Distance(), dst_msr)
