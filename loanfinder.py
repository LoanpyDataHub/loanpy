"""
takes two wordlists as input, one in the tentative recipient language (recipdf) \
and one in the tentative donor language (donordf) and returns \
candidates for potential loanwords.
"""

from ast import literal_eval
from functools import partial
from logging import getLogger

from pandas import DataFrame, Series, concat, read_csv
from tqdm import tqdm
from panphon.distance import Distance

from loanpy.helpers import gensim_multiword
from loanpy.adrc import Adrc

logger = getLogger(__name__)

class NoPhonMatch(Exception):
    pass

def read_data(path, colname, explosion): #explosion means explode
    if path is None: return None
    todrop = "wrong clusters|wrong phonotactics" if explosion is True else "not old|wrong phonotactics|wrong vowel harmony"
    donordf = read_csv(path, encoding="utf-8", usecols=[colname]).fillna("")  # save RAM
    donordf = donordf[~donordf[colname].str.contains(todrop)]
    if explosion is True:
        donordf[colname] = donordf[colname].str.split(", ")
        donordf = donordf.explode(colname)  # one word per row
    return donordf[colname]  # pd series

def gen(iterable1, iterable2, function, prefix="Calculating", *args):
    """applies a function to two iteratbles, incl. progressbar with prefix"""
    for ele1, ele2 in zip(tqdm(iterable1, prefix), iterable2):
        yield function(ele1, ele2, *args)

class Search():
    def __init__(self, path2donordf=None, path2recipdf=None, donorcol="ad", recipcol="rc",
                 phondist=0, phondist_msr="hamming_feature_edit_distance",
                 semsim=1 , semsim_msr=gensim_multiword,
                 scdictlist_ad=None, scdictlist_rc=None):
        """
        Searches for phonetic matches in a wordlist.

        :param donordf: The name of the dataframe containing the \
        wordlist of the tentative donor language

        :type donordf: str

        :param donorcol: The name of the column in the dataframe containing the \
        wordlist of the tentative recipient language

        :type donordf: str

        :param recipdf: The name of the input-csv that contains the input column for recipdf.
        :type recipdf: str

        # :param recipcol: The name of the input column that contains the input words for recipdf.
        :type recipcol: str

        :param donordf: The name of the input-csv that contains the input column for donordf.
        :type donordf: str, default

        :param donorcol: The name of the input column that contains the input words for donordf.
        :type donorcol: str

        :param sedict: Indicate the name of the file containing the sum of examples \
        for each sound change in the etymological dictionary of recipdf. This file is \
        generated by loanpy.reconstructor.dfetymology2dict
        :type sedict: str, default="sedict.txt"

        :param edict: Indicate the name of the file containing the examples for each sound \
        change in the etymological dictionary of recipdf. This file is generated by \
        loanpy.reconstructor.dfetymology2dict
        :type edict: str, default="edict.txt"

        :param sedict_ad: Indicate the name of the file containing the sum of examples \
        for each substitution. This file is \
        generated by loanpy.qfysc.Qfy().dfetymology2dict()
        :type sedict_ad: str, default="sedict_ad.txt"

        :param edict_ad: Indicate the name of the file containing the examples \
        for each substitution. This file is \
        generated by loanpy.qfysc.Qfy().dfetymology2dict()
        :type edict_ad: str, default="edict_ad.txt"
        """

        self.search_in = read_data(path2donordf, donorcol, True)
        self.search_for = read_data(path2recipdf, recipcol, False)
        self.donpath, self.recpath = path2donordf, path2recipdf
        self.doncol, self.reccol = donorcol, recipcol #has to be reused in postprocessing

        self.phondist = phondist
        self.phondist_msr = getattr(Distance(), phondist_msr)
        self.semsim = semsim
        self.semsim_msr = semsim_msr

        self.get_nse_ad = Adrc(scdictlist=scdictlist_ad, mode="adapt").get_nse
        self.get_nse_rc = Adrc(scdictlist=scdictlist_rc, mode="reconstruct").get_nse

    def phonmatch(self, search_for, index, dropduplicates=True):

        """
        Check if a regular expression is contained \
        in a wordlist and replace it with a number

        :param searchfor: The regular expression for which to search in the wordlist
        :type searchfor: str

        :param index: The number with which to replace a match. \
        (This number will be \
        used to merge the rest of the recipdf data frame, so it should represent \
        the index in the recipdf data frame. Subtract 2 from the index that Excel shows \
        because Python starts counting at zero and does not count headers.)
        :type index: str

        :param dropduplicates: If set to True, this will drop matches that have the same \
        index in the wordlist \
        (There's one adapted donordf-word per row, but its index \
        is the same as the original donordf word's from which it was adapted. \
        Therefore one recipdf word can match with the same donordf word through multiple \
        adaptations. Since the semantics are the same for all of those matches, duplicates can be dropped. \
        For a more precise search, e.g. to find out \
        which of all possible matches are the most likely, set dropduplicates=False)
        :type dropduplicates: bool, default=True

        :return: a pandas data frame containing phonetic matches. The index \
        indicates the position of the word in the donordf word list. \
        The column "L1_idx" indicates \
        the position of the word in the recipdf word list.
        :rtype: pandas.core.frame.DataFrame

        :Examples:

        >>> import pandas as pd
        >>> from loanpy import loanfinder as lf
        >>> pho = lf.Phonetix("dfgot_wiktionary.csv", "L2_latin")
        >>> pho.findphoneticmatches("^anna$", 5)
        +---+----------------+-----------+
        |   |L2_latin_match  |  L1_idx   |
        +---+----------------+-----------+
        |288| anna           |     5     |
        +---+----------------+-----------+

        >>> import pandas as pd
        >>> from loanpy import loanfinder as lf
        >>> pho = lf.Phonetix("dfgot_wiktionary.csv", "L2_latin")
        >>> pho.findphoneticmatches("^abraham$|^anna$", 123)
        +---+----------------+-----------+
        |   |L2_latin_match  |  L1_idx   |
        +---+----------------+-----------+
        |6  |      abraham   |     123   |
        +---+----------------+-----------+
        |288|      anna      |     123   |
        +---+----------------+-----------+

        >>> import pandas as pd
        >>> from loanpy import loanfinder as lf
        >>> pho = lf.Phonetix("dfgot_wiktionary.csv", "L2_latin")
        >>> pho.findphoneticmatches("^a(nn|br)a(ham)?$", 456)
        +---+----------------+-----------+
        |   |L2_latin_match  |  L1_idx   |
        +---+----------------+-----------+
        |6  |      abraham   |     456   |
        +---+----------------+-----------+
        |288|      anna      |     456   |
        +---+----------------+-----------+

        """
        if self.phondist == 0:
            matched = self.search_in[self.search_in.str.match(search_for)]
        else:
            self.phondist_msr = partial(self.phondist_msr, target=search_for)
            matched = self.search_in[self.search_in.apply(self.phondist_msr) <= self.phondist]

        dfphonmatch = DataFrame({"match": matched, "recipdf_idx": index})

        if dropduplicates is True:
            dfphonmatch = dfphonmatch[~dfphonmatch.index.duplicated(keep='first')]
        return dfphonmatch

    def loans(self, write_to=False, postprocess=False, merge_with_rest=False):

        #find phonetic matches
        dfmatches = concat(gen(self.search_for, self.search_for.index, self.phonmatch,
                               "searching for phonetic matches: "))
        #raise exception if no matches found
        if len(dfmatches) == 0: raise NoPhonMatch("no phonetic matches found")

        #add translations for semantic comparison
        dfmatches = dfmatches.merge(read_csv(self.recpath, encoding="utf-8", usecols=["Meaning"]).fillna(""), left_on="recipdf_idx", right_index=True)
        dfmatches = dfmatches.merge(read_csv(self.donpath, encoding="utf-8", usecols=["Meaning"]).fillna(""), left_index=True, right_index=True)

        #calculate semantic similarity of phonetic matches
        dfmatches[self.semsim_msr.__name__] = list(
        gen(dfmatches["Meaning_x"], dfmatches["Meaning_y"], self.semsim_msr,
        "calculating semantic similarity of phonetic matches: "))

        logger.warning(f"cutting off by semsim ({self.semsim}) and ranking by semantic similarity, ...")
        dfmatches = dfmatches[dfmatches[self.semsim_msr.__name__] >= self.semsim]
        dfmatches = dfmatches.sort_values(by=self.semsim_msr.__name__, ascending=False)

        if postprocess: dfmatches = self.postprocess(dfmatches)
        if merge_with_rest: dfmatches = self.merge_with_rest(dfmatches)
        if write_to:
            dfmatches.to_csv(write_to, encoding="utf-8", index=False)
            logger.warning(f"file written to {write_to}")

        logger.warning(f"done. Insert date and time later here.")
        return dfmatches

    def postprocess(self, dfmatches):
        logger.warning(f"postprocessing...")
        #read in data for likeliestphonmatch
        dfmatches = dfmatches.merge(read_csv(self.recpath, encoding="utf-8", usecols=["Segments", self.reccol]).fillna(""),left_on="recipdf_idx", right_index=True)
        dfmatches = dfmatches.merge(read_csv(self.donpath, encoding="utf-8", usecols=["Segments", self.doncol]).fillna(""),left_index=True, right_index=True)
        dfmatches["Segments_x"] = [i.replace(" ", "") for i in dfmatches["Segments_x"]]
        dfmatches["Segments_y"] = [i.replace(" ", "") for i in dfmatches["Segments_y"]]
        #calculate likeliest phonetic matches
        newcols = concat([
        self.likeliestphonmatch(ad, rc, segd, segr) for ad, rc, segd, segr
        in zip(dfmatches[self.doncol], dfmatches[self.reccol],
               dfmatches["Segments_y"], dfmatches["Segments_x"])])
        del dfmatches["match"] # delete non-likeliest matches
        newcols.index = dfmatches.index # otherwise concat wont work

        dfmatches = concat([dfmatches, newcols], axis=1) #add new cols
        #delete redundant data
        del (dfmatches["Segments_x"], dfmatches[self.reccol],
            dfmatches["Segments_y"], dfmatches[self.doncol])

        return dfmatches

    def likeliestphonmatch(self, donor_ad, recip_rc, donor_segment, recip_segment):
        """
        Calculates the nse of recip_rc-recip_orig and donor_ad-donor_orig, adds them together\
        and picks the word pair with the highest sum.

        :param recip_rc: a reconstructed recipdf-root
        :type recip_rc: regular expression

        :param donor_ad: adapted donordf-words, separated by ", "
        :type donor_ad: str

        :param recip_orig: a documented recipdf-reflex
        :type recip_orig: str

        :param donor_orig: the donor word
        :type donor_orig: str

        :return: The likeliest phonetic match
        :rtype: pandas.core.frame.DataFrame

        """
        dfph = self.phonmatch_small(Series(donor_ad.split(", "), name="match"), recip_rc, dropduplicates=False)
        dfph = DataFrame([
        (wrd,)+self.get_nse_rc(recip_segment, wrd, True, True)+self.get_nse_ad(donor_segment, wrd, True, True)
        for wrd in dfph["match"]], columns=["match", "nse_rc", "se_rc", "lst_rc",
        "nse_ad", "se_ad", "lst_ad"])
        #add combined nse
        dfph["nse_combined"] = dfph["nse_rc"] + dfph["nse_ad"]
        #get idx of max combined, keep only that idx
        dfph = dfph[dfph.index == dfph["nse_combined"].idxmax()]
        #add examples
        dfph["e_rc"] = [self.get_nse_rc(recip_segment, wrd, False, False) for wrd in dfph["match"]]
        dfph["e_ad"] = [self.get_nse_ad(donor_segment, wrd, False, False) for wrd in dfph["match"]]

        return dfph

    def phonmatch_small(self, search_in, search_for, index=None, dropduplicates=True):

        """
        Same as phonmatch() but search_in has to be added as a parameter. Found this \
        to be the most elegant solution b/c likeliestphonmatch() inputs lots of \
        small and very different search_in-dfs, while loans() inputs one big df \

        """
        if self.phondist == 0:
            matched = search_in[search_in.str.match(search_for)]
        else:
            self.phondist_msr = partial(self.phondist_msr, target=search_for)
            matched = search_in[search_in.apply(self.phondist_msr) <= self.phondist]

        dfphonmatch = DataFrame({"match": matched, "recipdf_idx": index})

        if dropduplicates is True:
            dfphonmatch = dfphonmatch[~dfphonmatch.index.duplicated(keep='first')]
        return dfphonmatch

    def merge_with_rest(self, dfmatches):
        logger.warning(f"Merging with remaining columns from input data frames")
        dfmatches = dfmatches.drop(["Meaning_x", "Meaning_y"], axis=1)  # avoid duplicates
        dfmatches = dfmatches.merge(read_csv(self.donpath, encoding="utf-8").fillna(""),left_index=True, right_index=True)
        dfmatches = dfmatches.merge(read_csv(self.recpath, encoding="utf-8").fillna(""),left_on="recipdf_idx", right_index=True)
        dfmatches = dfmatches.sort_values(by=self.semsim_msr.__name__, ascending=False) #bc unsorted by merge
        return dfmatches