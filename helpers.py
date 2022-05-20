"""
Contains helper functions and class Etym, which are called by other modules.

"""

from ast import literal_eval
from collections import Counter
from datetime import datetime
from functools import partial
from itertools import product
from logging import getLogger
from pathlib import Path

from gensim.downloader import load
from ipatok import clusterise, tokenise
from networkx import DiGraph, all_shortest_paths, shortest_path
from numpy import array_equiv, isnan, subtract, zeros
from pandas import DataFrame, read_csv
from panphon.distance import Distance
from tqdm import tqdm

logger = getLogger(__name__)
model = None
tokenise = partial(tokenise, replace=True)
clusterise = partial(clusterise, replace=True)

class InventoryMissingError(Exception):
    """
    Called by rank_closest() and rank_closest_struc() if neither forms.csv \
is defined nor the phonotactic/phoneme inventory plugged in.
    """
    pass

def plug_in_model(word2vec_model):
    """
    allows to plug in a word2vec model into global variable <model>. \
This is useful if you want to use vectors that can't be loaded with gensim's \
api. Vectors could be plugged in without this function as well, but this way \
debugging is easier.

    :param word2vec_model: The word2vec model to use
    :type word2vec: {<class 'gensim.models.keyedvectors.KeyedVectors'>)

    :returns: global variable <model> gets defined
    :rtype: None (global model = word2vec_model)

    :Example:

    >>> from loanpy import helpers as hp
    >>> from gensim.test.utils import common_texts
    >>> from gensim.models import word2vec
    >>> hp.plug_in_model(word2vec.Word2Vec(common_texts, min_count=1).wv)
    >>> hp.model
    <gensim.models.keyedvectors.KeyedVectors object at 0x7f85fe36d9d0>

    #this one has to be verified in practice first:
    >>> from loanpy import helpers as hp
    >>> from gensim.downloader import load
    >>> hp.plug_in_model(load("modelname"))
    >>> hp.model
    <gensim.models.keyedvectors.KeyedVectors object at 0x7f85fe36d9d0>

    """

    global model
    model = word2vec_model

def read_cvfb():
    """
    read file cvfb.txt that was generated based on ipa_all.csv. \
Its a tuple of two dictionaries. Keys are same as col "ipa" in ipa_all.csv. \
Vals of first dict are "C" if consonant and "V" if vowel (6358 keys). \
Vals of 2nd dict are "F" if front vowel and "B" if back vowel (1240 keys). \
Only called by Etym.__init__ to define self.phon2cv and self.vow2fb, \
which in turn is used by word2struc and many others. \
This file could be read directly when importing, but this way debugging is \
easier.

    :returns: two dictionaries, the first defining consonants and vowels (cv), \
the second defining front and back vowels (fb).
    :rtype: (dict, dict)

    :Example:

    >>> from loanpy.helpers import read_cvfb
    >>> read_cvfb()

    """
    #todo: document the changes from this ipa_all.csv to the original in panphon.
    path = Path(__file__).parent / "cvfb.txt"
    with open(path, "r", encoding="utf-8") as f:
        cvfb = literal_eval(f.read())
    return cvfb[0], cvfb[1]

def read_forms(dff):
    """
    reads forms.csv (cldf), keeps only columns Segement, Cognacy and \
Language ID, drops spaces in Segments to internally re-tokenise later. \
Only called by Etym.__init__ to create local variable dff (data frame forms). \
Returns None if dff is None. So that class can be initiated without args too.

    :param dff: path to forms.csv
    :type dff: <class 'pathlib.PosixPath'> | str | None

    :returns: a workable version of forms.csv as a pandas data frame
    :rtype: <class 'pandas.core.frame.DataFrame'> | None

    :Example:

    >>> from pathlib import Path
    >>> from loanpy.helpers import __file__, read_forms
    >>> read_forms(Path(__file__).parent / "tests" / "integration" / "input_files" / "forms.csv")

    """

    if not dff: return None
    dff = read_csv(dff, usecols=["Segments", "Cognacy", "Language_ID"])
    dff["Segments"] = [i.replace(" ", "") for i in dff.Segments]
    return dff

def cldf2pd(dfforms, srclg=None, tgtlg=None):
    """
    Converts a cldf-csv to a pandas data frame. \
Only called by Etym.__init__. \
Returns None if dfforms is None, so class can be initiated without args too. \
Runs through forms.csv and creates a new data frame the following way: \
Checks if a cognate set contains words from both, source and target language. \
If yes: word from source lg goes to column "Source_Form", \
word from target lg goes to column "Target_Form" and \
the number of the cognate set goes to column "Cognacy". \
Note that if a cognate set doesn't contain words from src and tgt lg, \
that cognate set is skipped.

    :param dfforms: Takes the output of read_forms() as input
    :type dfforms: <class 'pandas.core.frame.DataFrame'> | None

    :param srclg: The languages who's cognates go to column "Source_Forms"
    :type srclg: <str>

    :param tgtlg: The languages who's cognates go to column "Target_Forms"
    :type tgtlg: <str>

    :returns: forms.csv data frame with re-positioned information
    :rtype: <class 'pandas.core.frame.DataFrame'> | None

    :Example:

    >>> from pathlib import Path
    >>> from loanpy.helpers import __file__, cldf2pd, read_forms
    >>> cldf2pd(read_forms(Path(__file__).parent / "tests" / "integration" / "input_files" / "forms.csv"), srclg=1, tgtlg=2)

    """

    if dfforms is None: return None
    target_form, source_form, cognacy, dfetymology = [], [], [], DataFrame()

    #bugfix: col Cognacy is sometimes empty. if so, fill it
    if all(isnan(i) for i in dfforms.Cognacy): dfforms["Cognacy"] = list(range(len(dfforms)))

    for cog in range(1, int(list(dfforms["Cognacy"])[-1])+1):
        dfformsdrop = dfforms[dfforms["Cognacy"] == cog]
        if all(lg in list(dfformsdrop["Language_ID"]) for lg in [tgtlg, srclg]):
            cognacy.append(cog)
            for idx, row in dfformsdrop.iterrows():
                if row["Language_ID"] == tgtlg:
                    target_form.append(row["Segments"])
                if row["Language_ID"] == srclg:
                    source_form.append(row["Segments"])

    dfetymology["Target_Form"] = target_form
    dfetymology["Source_Form"] = source_form
    dfetymology["Cognacy"] = cognacy
    return dfetymology

def read_inventory(inv, forms, func=tokenise):
    """
    calculates and returns phoneme inventory from a list of words. \
Only called by Etym.__init__. \
Param <inv> is if inventory should not be calculated but manually plugged in.

    :param inv: a set of phonemes that occure in given language. \
if inv is None, inv will be calculated from forms else inv will be returned.
    :type inv: set

    :param forms: a list of words occuring in giving language
    :type forms: list of str

    :param func: the tokeniser to split words into phonemes
    :type func: function

    :returns: The phoneme inventory of the language
    :rtype: set | None | same as input type

    """
    return inv if inv else set(func("".join(forms))) if forms else None

def read_dst(dst_msr):
    """
    Returns a function that calculates the phonetic distance between strings \
from panphon.distance.Distance. This will be used to calculate the most \
similar phonemes of the inventory compared to a given phoneme from ipa_all.csv

    :param dst_msr: The name of the distance measure, for options see first \
example
    :type dst_msr: str | None

    :returns: a function that calculates the phonological distance between \
ipa-strings
    :rtype: function | None

    :Example:

    >>> from panphon.distance import Distance
    >>> help(Distance)
    doglo_prime_distance, dolgo_prime_distance_div_maxlen, \
fast_levenshtein_distance, fast_levenshtein_distance_div_maxlen, \
feature_difference,  feature_edit_distance, feature_edit_distance_div_maxlen, \
hamming_feature_edit_distance, hamming_feature_edit_distance_div_maxlen, \
hamming_substitution_cost, jt_feature_edit_distance, ...\


    >>> from loanpy.helpers import read_dst
    >>> read_dst("fast_levenshtein_distance")
    <bound method Distance.fast_levenshtein_distance of \
<panphon.distance.Distance object at 0x7f7f21fe95b0>>
    """
    return None if not dst_msr else getattr(Distance(), dst_msr)

def flatten(nested_list):
    """
    Flatten a nested list, discard empty strings

    :param t: a nested list
    :type t: list of lists

    :return: flattened list without empty strings as elements
    :rtype: list
    """
    #empty strings would trigger an error in the tokeniser
    # sometimes both phonemes of a 2-phoneme-word can be replaced with "".
    # so some entire words can be substituted by "". Discard those.
    return [item for sublist in nested_list for item in sublist if item]

def combine_ipalists(wrds):
    """
    Combine list of sound change lists.

    :param wrds: list of words consisting of sound change lists
    :type wrds: list of lists of lists

    :returns: a list of words without empty strings as elements
    :rtype: list of strings

    :Example:

    >>> from loanpy.helpers import combine_ipalists
    >>> combine_ipalists([[["a", "b"], ["c"], ["d"]], [["e", "f"], ["g"], ["h"]]])
    ['acd', 'bcd', 'egh', 'fgh']
    """

    return flatten([list(map("".join, product(*wrd))) for wrd in wrds])

def forms2list(dff, tgtlg):
    """
    Get a list of words of a language from a forms.csv. \
Only called by Etym.__init__

    :param dff: forms.csv data frame (cldf)
    :type dff: <class 'pandas.core.frame.DataFrame'>

    :returns: a list of words in the target language
    :rtype: list | None

    :Example:

    >>> from pathlib import Path
    >>> from loanpy.helpers import, __file__, forms2list, read_forms
    >>> forms2list(read_forms(Path(__file__).parent / "tests" / "integration" / "input_files" / "forms.csv"), tgtlg=2)
    ['xyz']
    """

    return None if dff is None else list(dff[dff["Language_ID"]==tgtlg]["Segments"])

class Etym():
    """
    Class that is based on 2 datasets: The first is static, and is ipa_all.csv \
from panphon, together with its "spinoff" cvfb.txt. The second has to be \
defined through the init args and will be data extracted from a forms.csv \
(cldf data standard, insert link here later). \
The class methods eventually all rely on panphon / data / "ipa_all.csv". \
loanpy's ipa_all.csv is slightly modified but I didn't keep track of the modifications. \
I remember that I changed the status of the glottal stop at least. \
And added "C", "V" to the bottom. Todo: Plug back in the original ipa_all.csv.\
Define consonants, vowels, front vowels, and back vowels \
based on David R. Mortensen, Patrick Littell, Akash Bharadwaj, Kartik Goyal, Chris Dyer, \
Lori Levin (2016). "PanPhon: A Resource for Mapping IPA Segments to Articulatory Feature \
Vectors." Proceedings of COLING 2016, the 26th International Conference on Computational \
Linguistics: Technical Papers, pages 3475–3484, Osaka, Japan, December 11-17 2016. \
(Based on SPE by Chomsyk&Halle). \
Turn forms.csv into a pandas data frame, \
and extract following information from it: \
phoneme inventory: a set of all phonemes that occur in the language's words, \
clusters: a set of all consonant and vowel clusters occuring in the language, \
struc_inv: a list of phonotactic structures that occur in the language, \
sorted according to their frequency

    :param formscsv: a forms.csv of the cldf data standard (insert link)
    :type formscsv: <class 'pathlib.PosixPath'> | str | None

    :param srclg: The technical source language as defined in \
cldf's etc / "languages.tsv". \
This can be confusing, as sometimes \
the technical source language for the predictions can be the linguistic \
target language, e.g. when we are backward reconstructing. But when we are \
adapting loanwords the technical and the linguistic source word are usually \
the same.
    :type srclg: str

    :param tgtlg: The technical target language as defined in \
cldf's etc / "languages.tsv". For caveats see param srclg
    :type tgtlg: str

    :param inventory: The phoneme inventory. If None, it will be extracted \
automatically from forms.csv
    :type inventory: None | list | set

    :param clusters: All consonant and vowel clusters that occur \
in the language. If None, will be automatically extracted from forms.csv
    :type clusters: None | list | set

    :param struc_inv: All phonetic structures ("CVCV") that occur in the \
language
    :type struc_inv: None | list | set

    :param distance_measure: The distance measure. See help(read_dst)
    :type distance_measure: function

    :param struc_most_frquent: The how many most frequently occuring phonotactic \
structures should we allow to be part of the inventory.
    :type struc_most_frquent: int

    :Example:

    >>> from pathlib import Path
    >>> from loanpy.helpers import Etym, __file__
    >>> etym_obj = Etym(formscsv=Path(__file__).parent / "tests" / \
"integration" / "input_files" / "forms.csv", srclg=1, tgtlg=2)
    >>> etym_obj.phon2cv["k"]
    'C'
    >>> etym_obj.vow2fb["e"]
    'F'
    >>> etym_obj.distance_measure("p", "b")
    0.25
    >>> etym_obj.dfety

    >>> etym_obj.phoneme_inventory
    {'y', 'z', 'x'}
    >>> etym_obj.clusters
    {'y', 'z', 'x'}
    >>> etym_obj.struc_inv
    {'CVC'}

    """
    def __init__(self, formscsv=None, srclg=None, tgtlg=None,
                 inventory=None, clusters=None, struc_inv=None,
                 distance_measure="weighted_feature_edit_distance",
                 struc_most_frequent=9999999):
        #local vars
        dff = read_forms(formscsv)
        forms = forms2list(dff, tgtlg)

        #based on no local vars
        self.phon2cv, self.vow2fb = read_cvfb()
        self.distance_measure = read_dst(distance_measure)
        #based on local var dff
        self.dfety = cldf2pd(dff, srclg, tgtlg)
        #based on local var forms
        self.phoneme_inventory = read_inventory(inventory, forms)
        self.clusters = read_inventory(clusters, forms, clusterise)  #needed in adrc.py for only_allowed_clusters
        self.struc_inv = self.read_strucinv(struc_inv, forms, struc_most_frequent)

    def read_strucinv(self, struc_inv=None, forms=None, howmany=9999999):
        """
        returns inventory of the most frequent x phonotactic structures

        :param struc_inv: Possibility to plug in the inventory manually.
        :type struc_inv: None | list | set | same type as input

        :param forms: a list of words in a language
        :type forms: list | None

        :param howmany: howmany most frequent structures should be added to \
inventory
        :type howmany: int

        :returns: all possible phonotactic structures documented in the data
        :rtype: list

        :Note:

        The map function seems to swallow errors that would be otherwise \
triggered by Counter. E.g. if you use a float \
(including float("inf")) for param <howmany>, an empty string \
will be returned.

        """

        if struc_inv: return struc_inv
        if forms is None: return None
        strucs = list(map(self.word2struc, forms))
        if howmany == 9999999: return set(strucs)
        return list(map(lambda x: x[0], Counter(strucs).most_common(howmany)))

    def word2struc(self, ipa_in):
        """
        Returns the phonotactic profile of an ipa-string.

        :param ipa_in: a string or list consisting of IPA-characters. \
if input is string, it will be tokenised.
        :type ipa_in: str | list (IPA chars)

        :returns: the phonotactic profile of the word
        :rtype: str

        :Example:

        >>> from loanpy import helpers
        >>> hp = helpers.Etym()
        >>> hp.word2struc("lol")
        'CVC'

        """
        if isinstance(ipa_in, str):
            ipa_in = tokenise(ipa_in)

        return "".join([self.phon2cv.get(i, "") for i in ipa_in])


    def word2struc_keepcv(self, ipa_in):
        """
        Returns the phonotactic profile of an ipa-string while keeping \
Cs and Vs. Originally written for sanity.py but currently not used anywhere.

        :Example:

        >>> from loanpy import helpers
        >>> hp = helpers.Etym()
        >>> hp.word2struc_keepcv("CloVl")
        'CCVVC'

        """
        return "".join([self.phon2cv.get(i, "") if i not in "CV" else i for i in ipa_in])

    def harmony(self, ipalist):
        """
        Tells if a word has front-back vowel harmony or not

        :param ipalist: the word that should be analysed
        :type ipalist: {list of str, str}

        :returns: Does the word have front-back vowelharmony?
        :rtype: bool

        :Example:

        >>> from loanpy import helpers
        >>> hp = helpers.Etym()
        >>> hp.harmony("bot͡sibot͡si")
        False

        >>> from loanpy import helpers
        >>> hp = helpers.Etym()
        >>> hp.harmony(["t", "ɒ", "r", "k", "ɒ"])
        True

        """
        if isinstance(ipalist, str):
            ipalist = tokenise(ipalist)
        vowels = set(j for j in [self.vow2fb.get(i,"") for i in ipalist] if j)
        return vowels in ({"F"}, {"B"}, set())

    def adapt_harmony(self, ipalist):
        """
        Adapts the vowel harmony of a word by replacing wrong vowels by a \
"F" for any front vowel or "B" for any back vowel.

        :param ipalist: a list or a string of phonemes
        :type ipalist: {list of str, str}

        :returns: a tokenised word with repaired vowelharmony
        :rtype: list of str

        :Example:

        >>> from loanpy import helpers
        >>> hp = helpers.Etym()
        >>> hp.adapt_harmony('kɛsthɛj')
        ['k', 'ɛ', 's', 't', 'h', 'ɛ', 'j']

        >>> from loanpy import helpers
        >>> hp = helpers.Etym()
        >>> hp.adapt_harmony(['ɒ', 'l', 'ʃ', 'oː', 'ø', 'r', 'ʃ'])
        ['ɒ', 'l', 'ʃ', 'oː', 'B', 'r', 'ʃ']

        >>> from loanpy import helpers
        >>> hp = helpers.Etym()
        >>> hp.adapt_harmony(['b', 'eː', 'l', 'ɒ', 't', 'ɛ', 'l', 'ɛ', 'p'])
        ['b', 'eː', 'l', 'F', 't', 'ɛ', 'l', 'ɛ', 'p']

        >>> from loanpy import helpers
        >>> hp = helpers.Etym()
        >>> hp.adapt_harmony(['b', 'ɒ', 'l', 'ɒ', 't', 'o', 'n', 'k', 'ɛ', 'n', 'ɛ', 'ʃ', 'ɛ'])
        [['b', 'F', 'l', 'F', 't', 'F', 'n', 'k', 'ɛ', 'n', 'ɛ', 'ʃ', 'ɛ'], \
['b', 'ɒ', 'l', 'ɒ', 't', 'o', 'n', 'k', 'B', 'n', 'B', 'ʃ', 'B']]

        """
        if isinstance(ipalist, str):
            ipalist = tokenise(ipalist)

        if self.harmony(ipalist) and "V" not in ipalist:
            return [ipalist]

        out = [j for j in [self.vow2fb.get(i,"") for i in ipalist] if j]
        if out.count("F") > out.count("B"):
            out = [self.get_fb(ipalist, turnto="F")]
        elif out.count("B") > out.count("F"):
            out = [self.get_fb(ipalist, turnto="B")]
        else:
            out = [self.get_fb(ipalist, "F"), self.get_fb(ipalist, "B")]

        return out

    def get_fb(self, ipalist, turnto="F"):
        """
        Turns front vowels to back ones if turnto="B", \
but turns back vowels to front ones if turnto="F"

        :param ipalist: a tokenised ipa-string
        :type ipalist: list

        :param turnto: turn back vowels to front ones or vice verse
        :type turnto: {"F", "B"}

        :returns: a tokenised word with some vowels replaced by "F" or "B".
        :rtype: list

        :Example:

        >>> from loanpy import helpers
        >>> hp = helpers.Etym()
        >>> hp.get_fb(['ɒ', 'l', 'ʃ', 'oː', 'ø', 'r', 'ʃ'], turnto="B")
        ['ɒ', 'l', 'ʃ', 'oː', 'B', 'r', 'ʃ']
        """

        checkfor = "F" if turnto == "B" else "B"

        return [turnto if self.vow2fb.get(i,"") == checkfor or i=="V"
                else i for i in ipalist]

    def get_scdictbase(self, write_to=None, most_common=float("inf")):
        """
        Loop through ipa_all.csv and rank most similar phonemes from inventory. \
Could also turn ipa_all.csv into a square of 6358*6358 phonemes and just use \
that file for all future cases but that would use an estimated 500MB per \
type of distance measure. So more economical to calculate it this way. \
Will still, depending on size of phoneme inventory, take up about 2MB. \
result is returned, assigned to self.scdictbase and optionally written. \
Usually there is very little data available \
on sound substitutions and the ones available give only very small instight \
into all possibilities. \
The idea here is therefore that any sound \
that is not contained in a language's phoneme inventory will be replaced by \
the most similar available one(s). The available sound substitutions \
based on etymological data will be combined with \
this heuristics, if available.

        :param write_to: If or where the output should be written.
        :type write_to: None | <class 'pathlib.PosixPath'> | str

        :param most_common: Add only this many most similar phonemes to \
scdictbase. By default the entire phoneme inventory will be ranked.

        :returns: A heuristic approach to sound substitution in loanword \
adaptation
        :rtype: dict

        :Example:

        >>> from pathlib import Path
        >>> from loanpy.helpers import Etym, __file__
        >>> etym_obj = Etym(formscsv=Path(__file__).parent / "tests" / \
"integration" / "input_files" / "forms.csv", srclg=1, tgtlg=2)
        >>> etym_obj.get_scdictbase()
        >>> etym_obj.scdictbase["i"]
        ["y", "x", "z"]
        """

        ipa_all = read_csv(Path(__file__).parent / "ipa_all.csv")
        ipa_all["substi"] = [self.rank_closest(ph, most_common) for ph in tqdm(ipa_all["ipa"])]
        scdictbase = dict(zip(ipa_all["ipa"], ipa_all["substi"].str.split(", ")))

        scdictbase["C"] = self.rank_closest("ə", most_common, #pick the most unmarked C
        [i for i in self.phoneme_inventory if self.phon2cv.get(i,"") == "C"]).split(", ")
        scdictbase["V"] = self.rank_closest("ə", most_common, #pick the most unmarked V
        [i for i in self.phoneme_inventory if self.phon2cv.get(i,"") == "V"]).split(", ")
        scdictbase["F"] = [i for i in self.phoneme_inventory if self.vow2fb.get(i,"") == "F"]
        scdictbase["B"] = [i for i in self.phoneme_inventory if self.vow2fb.get(i,"") == "B"]

        self.scdictbase = scdictbase

        if write_to:
            with open(write_to, "w", encoding="utf-8") as f:
                f.write(str(scdictbase))

        return scdictbase

    def rank_closest(self, ph, howmany=float("inf"), inv=None):
        """
        sort self.phoneme_inventory by distance to input-phoneme

        :param ph: phoneme to which to rank the inventory
        :type ph: str (valid chars: col "ipa" in ipa_all.csv)

        :param howmany: howmany of the most similar to pick
        :type howmany: {int, float("inf")}

        :param inv: To plug in phoneme inventory manually if necessary
        :type inv: list | set

        :returns: the phoneme inventory ranked by similarity (most similar \
first)
        :rytpe: str (elements separates by ", ")

        :Example:

        >>> from pathlib import Path
        >>> from loanpy.helpers import Etym, __file__
        >>> etym_obj = Etym()
        >>> etym_obj.rank_closest(ph="d", inv=["r", "t", "l"], howmany=1)
        't'
        >>> etym_obj = Etym(inventory=["a", "b", "c"])
        >>> etym_obj.rank_closest(ph="d")
        'b, c, a'

        """
        if self.phoneme_inventory is None and inv is None:
            raise InventoryMissingError("define phoneme inventory or forms.csv")
        if inv is None: inv = self.phoneme_inventory

        phons_and_dist = [(i, self.distance_measure(ph, i)) for i in inv]
        return pick_mins(phons_and_dist, howmany)

    #DONT merge this func into rank_closest. It makes things more complicated
    def rank_closest_struc(self, struc, howmany=9999999, inv=None):
        """
        sort self.struc_inv by distance to given phonotactic structure

        :param struc: The phonetic structure to which to rank the inventory
        :type struc: str (consisting of "C"s and "V"s only)

        :param howmany: Howmany of the most similar structures should be picked
        :type howmany: {int, float("inf")}

        :param inv: To plug in the phonotactic structure inventory \
manually if necessary
        :type inv: list | set

        :returns: the phonotactic inventory ranked by similarity (most similar \
first)
        :rytpe: str (elements separates by ", ")

        >>> from pathlib import Path
        >>> from loanpy.helpers import Etym, __file__
        >>> etym_obj = Etym(struc_inv=["CVC", "CVCVV", "CCCC", "VVVVVV"])
        >>> etym_obj.rank_closest_struc(struc="CVCV", howmany=1)
        'CVCVV'
        >>> etym_obj = Etym()
        >>> etym_obj.rank_closest_struc(struc="CVCV", howmany=3,
        inv=["CVC", "CVCVV", "CCCC", "VVVVVV"])
        "CVCVV, CVC, CCCC"

        """
        if self.struc_inv is None and inv is None:
            raise InventoryMissingError("define phonotactic inventory or forms.csv")
        if inv is None: inv = self.struc_inv

        strucs_and_dist = [(i, edit_distance_with2ops(struc, i)) for i in inv]
        return pick_mins(strucs_and_dist, howmany)

def gensim_multiword(recip_transl, donor_transl, return_wordpair=False, wordvectors= "word2vec-google-news-300"):
    """

    :param recip_transl: translation of the recipient word
    :type recip_transl: str, words are separated by ", "

    :param donor_transl: translations of the donor word
    :type donor_transl: str, words are separated by ", "

    :param return_wordpair: Indicate whether the word pair itself should be \
returned too.
    :type return_wordpair: bool, default=False

    :param wordvectors: The name of the pretrained wordvector model to use. \
For a complete list of loadable models see gensim's documentation.
    :type wordvectors: str

    :returns: The similarity score of the most similar word pair plus \
the word pair itself if return_wordpair was True.
    :rtype: int or (int, str, str)

    :Example:

    >>> from loanpy import gensim_multiword
    >>> gensim_multiword("hovercraft, full, eels", "nipples, explode, delight",
                          return_wordpair=False)
    0.21005636

    >>> from loanpy import gensim_multiword
    >>> gensim_multiword("drop, panties, William", "cannot, wait, lunchtime",
                           return_wordpair=True)
    (0.54949486, 'house', 'cottage')

    """

    # missing translations = empty cells = nans = floats
    if any(not isinstance(arg, str) for arg in [recip_transl, donor_transl]):
        return (-1, f"!{str(type(recip_transl))}!", f"!{str(type(donor_transl))}!") if return_wordpair else -1
    else: recip_transl, donor_transl = recip_transl.split(', '), donor_transl.split(', ')

    global model
    if model is None:
        logger.warning(f"\r{datetime.now().strftime('%H:%M')} loading vectors")
        try: model = load(wordvectors)
        except MemoryError: logger.warning("Memory Error. Close background processes and use a RAM-saving browser like Opera")
        logger.warning(f"\r{datetime.now().strftime('%H:%M')} Vectors loaded")

    topsim, rtr, dtr = -1, "", ""  # lowest possible similarity score
    for rectr in recip_transl:
        for dontr in donor_transl:  # calculate semantic similarity of all pairs0
            try: modsim = model.similarity(rectr, dontr)
            except KeyError: continue # if word not in KeyedVecors of gensim continue
            if modsim == 1: return (1, rectr, dontr) if return_wordpair else 1
            if modsim > topsim:  topsim, rtr, dtr = modsim, rectr, dontr# replace if more similar than topsim
    return (topsim, rtr, dtr) if return_wordpair else topsim

def list2regex(sclist):
    """
    Turns a list of phonemes into a regular expression

    :param sclist: a list of phonemes
    :type sclist: list of str

    :returns: the same phonemes as a regular expression. "-" is \
removed and replaced with a question mark at the end.
    :rtype: str

    :Example:

    >>> from loanpy.helpers import list2regex
    >>> list2regex(["b", "k", "v"])
    "(b|k|v)"

    >>> from loanpy.helpers import list2regex
    >>> list2regex(["b", "k", "-", "v"])
    "(b|k|v)?"

    """

    if sclist == ["-"]: return ""
    if "-" in sclist: return "("+"|".join([i for i in sclist if i != "-"]) + ")?"
    return "("+"|".join(sclist) + ")"


def edit_distance_with2ops(string1, string2, w_ins=0.49, w_del=1):
    """
    Takes two strings and calculates their similarity by \
only allowing two operations: insertion and deletion. \
In line with the "Threshold Principle" by Carole Paradis and Darlene LaCharité (1997) \
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
costly in terms of the Threshold Principle" (p.385, Preservation and Minimality \
in Loanword Adaptation, \
Author(s): Carole Paradis and Darlene Lacharité, \
Source: Journal of Linguistics , Sep., 1997, Vol. 33, No. 2 (Sep., 1997), \
pp. 379-430, \
Published by: Cambridge University Press, \
Stable URL: http://www.jstor.com/stable/4176422). \
The code is based on a post by ita_c on \
https://www.geeksforgeeks.org/edit-distance-and-lcs-longest-common-subsequence\
 (last access: 11.feb.2021)

    :param string1: The first of two strings to be compared to each other
    :type string1: str

    :param string2: The second of two strings to be compared to each other
    :type string2: str

    :returns: The distance between two input strings
    :rtype: int

    :Example:

    >>> from loanpy.helpers import edit_distance_with2ops
    >>> edit_distance_with2ops("hey","hey")
    0.0

    >>> from loanpy.helpers import edit_distance_with2ops
    >>> edit_distance_with2ops("hey","he")
    1.0

    >>> from loanpy.helpers import edit_distance_with2ops
    >>> edit_distance_with2ops("hey","heyy")
    0.4

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
    return (m - lcs) * w_del + (n - lcs) * w_ins #costs (=distance) are lower for insertions

def get_mtx(target, source):
    """
    From https://www.youtube.com/watch?v=AY2DZ4a9gyk. \
Get the distance matrix of two strings.

    :param target: The target word
    :type target: str

    :param source: The source word
    :type source: str

    :returns: A distance matrix
    :rtype: numpy.ndarray

    """
    target = ['#']+[k for k in target]
    source = ['#']+[k for k in source]
    sol = zeros((len(source), len(target)))

    sol[0] = [j for j in range(len(target))]
    sol[:,0] = [j for j in range(len(source))]

    if target[1] != source[1]:
        sol[1,1] = 2

    for c in range(1, len(target)):
        for r in range(1, len(source)):
            if target[c] != source[r]:
                sol[r,c] = min(sol[r-1,c],sol[r,c-1])+1
            else:
                sol[r,c] = sol[r-1,c-1]

    return sol

def mtx2graph(s1, s2, w_del=100, w_ins=49):
    """
    Takes two strings and turns them to a directed graph object

    :param s1: The first of two strings to be compared to each other
    :type s1: str

    :param s2: The second of two strings to be compared to each other
    :type s2: str

    :param w_del: The weight (cost) of deletions
    :type w_del: int

    :param w_ins: The weight (cost) of insertions
    :type w_ins: int

    :returns: The directed graph object, its hight and its width
    :rtype: (networkx.classes.digraph.DiGraph, int, int)

    """
    mtx = get_mtx(s1, s2)
    s1,s2="#"+s1,"#"+s2
    G = DiGraph()
    h,w = mtx.shape

    for r in reversed(range(h)): #create vertical edges
        for c in reversed(range(w-1)):
            G.add_edge((r,c+1), (r,c), weight=w_del)

    for r in reversed(range(h-1)): #create horizontal edges
        for c in reversed(range(w)):
            G.add_edge((r+1,c), (r,c), weight=w_ins)

    for r in reversed(range(h-1)): #add diagonal edges where cost=0
        for c in reversed(range(w-1)):
            if mtx[r+1,c+1] == mtx[r,c]:
                if s1[c+1] == s2[r+1]:
                    G.add_edge((r+1,c+1), (r,c), weight=0)

    return G, h, w

def tuples2editops(op_list, s1, s2):
    """
    Turns numeric instructions of how to transform string1 to string2 \
into human readable ones.

    :param op_list: The numeric list of edit operations
    :type op_list: list of tuples of 2 int

    :param s1: The first of two strings to be compared to each other
    :type s1: str

    :param s2: The second of two strings to be compared to each other
    :type s2: str

    :returns: list of human readable edit operations
    :rtype: list of strings

    """
    s1, s2 = "#"+s1, "#"+s2
    out = []
    for i, todo in enumerate(op_list):
        if i == 0: #so that i-i won't be out of range
            continue
        #where does the arrow point?
        direction = subtract(todo, op_list[i-1])
        if array_equiv(direction, [1, 1]): #if diagonal
            out.append(f"keep {s1[todo[1]]}")
        elif array_equiv(direction, [0, 1]): #if horizontal
            if i > 1: #if previous was verical -> substitute
                if array_equiv(subtract(op_list[i-1], op_list[i-2]), [1, 0]):
                    out = out[:-1]
                    out.append(f"substitute {s1[todo[1]]} by {s2[todo[0]]}")
                    continue
            out.append(f"delete {s1[todo[1]]}")
        elif array_equiv(direction, [1, 0]): #if vertical
            if i > 1: #if previous was horizontal -> substitute
                if array_equiv(subtract(op_list[i-1], op_list[i-2]), [0, 1]):
                    out = out[:-1]
                    out.append(f"substitute {s1[todo[1]]} by {s2[todo[0]]}")
                    continue
            out.append(f"insert {s2[todo[0]]}")

    return out

def editops(s1, s2, howmany_paths=1, w_del=100, w_ins=49):
    """
    Takes two strings and returns \
the edit operations of all shortest paths between them.

    :param s1: The first of two strings to be compared to each other
    :type s1: str

    :param s2: The second of two strings to be compared to each other
    :type s2: str

    :param howmany_paths: The number of shortest paths that should be returned.
    :type howmany_paths: int

    :param w_del: The weight (cost) of deletions
    :type w_del: int

    :param w_ins: The weight (cost) of insertions
    :type w_ins: int

    """
    G, h, w = mtx2graph(s1, s2, w_del, w_ins)
    paths = [shortest_path(G, (h-1,w-1), (0, 0), weight='weight')] if howmany_paths==1 else all_shortest_paths(G, (h-1,w-1), (0, 0), weight='weight')
    out = [tuples2editops(list(reversed(i)), s1, s2) for i in paths]
    return list(dict.fromkeys(map(tuple,out)))[:howmany_paths]

def apply_edit(word, editops):
    """
    Applies a list of (human readable) edit operations to a string.

    :param word: The input word
    :type word: an iterable (e.g. list of phonemes, or string)

    :param editops: list of (human readable) edit operations
    :type editops: list of strings

    :returns: transformed input word
    :rtype: list of str
    """
    out, letter = [], iter(word)
    for i, op in enumerate(editops):
        if i != len(editops): #to avoid stopiteration
            if "keep" in op: out.append(next(letter))
            elif "delete" in op: next(letter)
        if "substitute" in op:
            out.append(op[op.index(" by ")+4:])
            if i != len(editops)-1: next(letter)
        elif "insert" in op: out.append(op[len("insert "):])
    return out

def get_howmany(step, hm_struc_ceiling, hm_paths_ceiling):
    """
    Put marbles into three pots, one by one, with following conditions: \
the product of the number of marbles per pot can't be higher than var step. \
Don't put more marbles in pot 2 and 3 than the ceiling variables indicate.

    :param step: the product of the three pots over which not to step
    :type step: int

    :param hm_struc_ceiling: The max nr of marbles for pot 2
    :type hm_struc_ceiling: int

    :param hm_struc_ceiling: The max nr of marbles for pot 3
    :type hm_struc_ceiling: int

    :returns: The way the marbles should be split
    :rtype: (int, int, int)

    """
    x, y, z = 1, 1, 1
    while x*y*z < step:
        x+=1
        if x*y*z >= step: return x,y,z
        if y < hm_struc_ceiling:
            y+=1
            if x*y*z >= step: return x,y,z
        if z < hm_paths_ceiling:
            z+=1
            if x*y*z >= step: return x,y,z

    return x, y, z

def pick_mins(inv_and_dist, howmany):
    """
    Pick only the n smallest numbers from a list. Should be cheaper than \
sorting the entire list and then taking only the slice we need.

    :param inv_and_dist: inventories and distances
    :type inv_and_dist: list of tuples

    :param howmany: howmany minimums do we want to pick from input-list
    :type howmany: int

    :returns: The indicated number of minimal values
    :rtype: str (separated by ", ")
    """

    #if we want to have at least as many elements as the list is long
    #then we will just have to sort the entire list
    if howmany >= len(inv_and_dist):
        return ", ".join([i[0] for i in sorted(inv_and_dist, key=lambda tup: tup[1])])
    out = []
    #but if we just want a handful of min values
    for i in range(howmany): #just pick that number of mins thru loop.
        mindisttup = min(inv_and_dist, key=lambda tup: tup[1])
        out.append(inv_and_dist.pop(inv_and_dist.index(mindisttup))[0])
    return ", ".join(out)
