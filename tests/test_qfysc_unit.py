"""unit test for loanpy.qfysc.py (2.0 BETA) for pytest 7.1.1"""

from ast import literal_eval
from inspect import ismethod
from os import remove
from pathlib import Path
from unittest.mock import patch, call

from loanpy import qfysc as qs
from loanpy import helpers as hp
from loanpy.qfysc import (
    Etym,
    InventoryMissingError,
    WrongModeError,
    cldf2pd,
    forms2list,
    read_mode,
    read_connector,
    read_dst,
    read_forms,
    read_scdictbase)

from pytest import raises
from pandas import DataFrame, Series
from pandas.testing import assert_frame_equal, assert_series_equal

# used throughout the module


class EtymMonkey:
    pass

# used in multiple places


class PairwiseMonkey:
    def __init__(self, *args):
        self.alignments = [("kala", "hal-")]
        self.align_called_with = []

    def align(self, *args):
        self.align_called_with.append([*args])

# used in multiple places


class EtymMonkeyGetSoundCorresp:
    def __init__(
            self,
            mode,
            connector,
            alignreturns1,
            alignreturns2,
            vfb=None):
        self.df1 = alignreturns1
        self.df2 = alignreturns2
        self.align_returns = iter([self.df1, self.df2])
        self.align_called_with = []
        self.rank_closest_phonotactics_called_with = []
        self.dfety = DataFrame({"Target_Form": ["kiki", "buba"],
                                "Source_Form": ["hehe", "pupa"],
                                "Cognacy": [12, 13]})
        self.left = "Target_Form"
        self.right = "Source_Form"
        self.mode = mode
        self.connector = connector
        self.scdictbase = {"k": ["h", "c"], "i": ["i", "e"], "b": ["v"],
                           "u": ["o", "u"], "a": ["y", "ü"]}
        self.vfb = vfb
        self.phon2cv = {
            "k": "C",
            "i": "V",
            "b": "C",
            "u": "V",
            "a": "V",
            "e": "V"}
        self.vow2fb = {"i": "F", "e": "F", "u": "B", "a": "B"}

    def align(self, left, right):
        self.align_called_with.append((left, right))
        return next(self.align_returns)

    def rank_closest_phonotactics(self, struc):
        self.rank_closest_phonotactics_called_with.append(struc)
        return "CVC, CVCCC"

    def get_phonotactics_corresp(self, *args):
        return [{"d1": 0}, {"d2": 0}, {"d3": 0}]

def test_read_phonotactic_inv():
    """test if inventory of phonotactic structures is extracted correctly"""

    # set up custom class
    class EtymMonkeyReadstrucinv:
        def __init__(self):
            self.forms_target_language = ["ab", "ab", "aa", "bb", "bb", "bb"]

    # set up rest
    mocketym = EtymMonkeyReadstrucinv()

    # assert with different parameter combinations
    assert Etym.read_phonotactic_inv(self=mocketym, phonotactic_inventory=[
        "a", "b", "c"]) == ["a", "b", "c"]
    mocketym.forms_target_language = None
    assert Etym.read_phonotactic_inv(self=mocketym, phonotactic_inventory=None,
                                     ) is None
    mocketym.forms_target_language = ["ab", "ab", "aa", "bb", "bb", "bb"]
    # now just read the most frquent 2 structures. VV is the 3rd frquent. so
    # not in the output.
    with patch("loanpy.qfysc.prosodic_string",
        side_effect=["VV", "VC", "VC", "CC", "CC", "CC"]) as prosodic_string_mock:
        assert Etym.read_phonotactic_inv(self=mocketym, phonotactic_inventory=None,
                                     howmany=2) == {"CC", "VC"}

    # assert calls
    prosodic_string_mock.assert_has_calls(
        [call(['a', 'b']),
         call(['a', 'b']),
         call(['a', 'a']),
         call(['b', 'b']),
         call(['b', 'b']),
         call(['b', 'b'])]
         )

    # tear down
    del mocketym, EtymMonkeyReadstrucinv

def test_read_inventory():
    """check if phoneme inventory is extracted correctly"""

    class EtymMonkey:
        pass
    etym_monkey = EtymMonkey()
    # assert where no setup needed
    etym_monkey.forms_target_language = "whatever"
    assert Etym.read_inventory(etym_monkey, "whatever2") == "whatever2"
    etym_monkey.forms_target_language = None
    assert Etym.read_inventory(etym_monkey, None) is None

    # set up
    # this is the vocabulary of the language
    etym_monkey.forms_target_language = ["a", "aab", "bc"]
    with patch("loanpy.helpers.tokenise") as tokenise_mock:
        # these are all letters of the language
        tokenise_mock.return_value = ['a', 'a', 'a', 'b', 'b', 'c']

        # assert
        assert Etym.read_inventory(etym_monkey,
                                   None, tokenise_mock) == set(['a', 'b', 'c'])

    # assert calls
    tokenise_mock.assert_called_with("aaabbc")

    # set up2: for clusterise
    etym_monkey.forms_target_language = ["a", "ab", "baac"]
    with patch("loanpy.helpers.clusterise") as clusterise_mock:
        clusterise_mock.return_value = [
            'aa', 'bb', 'aa', 'c']  # clusterised vocab

        # assert
        assert Etym.read_inventory(
            etym_monkey, None, clusterise_mock) == set(['aa', 'bb', 'c'])

    # assert calls
    # all words are pulled together to one string
    clusterise_mock.assert_called_with("aabbaac")

    # tear down
    del etym_monkey, EtymMonkey


def test_get_inventories():
    """test if phoneme/cluster/phonotactic inventories are read in well"""
    # set up
    class EtymMonkey():
        def __init__(self):
            self.read_inventory_called_with = []
            self.read_phonotactic_inv_called_with = []

        def read_inventory(self, *args):
            self.read_inventory_called_with.append([*args])
            return "read_inventory_returned_this"

        def read_phonotactic_inv(self, *args):
            self.read_phonotactic_inv_called_with.append([*args])
            return "read_phonotactic_inv_returned_this"

    # create instancce
    etym_monkey = EtymMonkey()
    # run func
    assert Etym.get_inventories(self=etym_monkey) == (
        "read_inventory_returned_this",
        "read_inventory_returned_this",
        "read_phonotactic_inv_returned_this"
    )

    # assert calls
    assert etym_monkey.read_inventory_called_with == [
        [None], [None, hp.clusterise]]
    assert etym_monkey.read_phonotactic_inv_called_with == [[None, 9999999]]

    # run func without default parameters

    # create instancce
    etym_monkey = EtymMonkey()
    # assert assigned attributes
    assert Etym.get_inventories(etym_monkey, "param1", "param2", "param3", 4
                                ) == ("read_inventory_returned_this",
                                      "read_inventory_returned_this",
                                      "read_phonotactic_inv_returned_this")
    # assert calls
    assert etym_monkey.read_inventory_called_with == [["param1"], [
        "param2", hp.clusterise]]
    assert etym_monkey.read_phonotactic_inv_called_with == [["param3", 4]]

    # tear down
    del etym_monkey, EtymMonkey



def test_get_scdictbase():
    """test if heuristic prediction of sound substitutions works,
    i.e. if phoneme inventory can be ranked
    according to feature vector distance to any sound"""

    # set up mockclass, mock read_csv, create instance of mockclass,
    # plug phoneme_inventory, phon2cv, vow2fb into it
    # set up 2 path variables to test files
    # define expected output as variable
    # define mock function for tqdm and plug it into lonapy.helpers
    class EtymMonkeyget_scdictbase:
        def __init__(self):
            self.rnkcls = iter(["e, f, d", "d, f, e", "f, d, e", "f, d", "e",
                                "e", "d", "f", "f", "e"])
            self.rank_closest_called_with = []

        def rank_closest(self, *args):
            self.rank_closest_called_with.append([*args])
            return next(self.rnkcls)
    with patch("loanpy.qfysc.read_csv") as read_csv_mock:
        read_csv_mock.return_value = DataFrame({"ipa": ["a", "b", "c"]})
        mocketym = EtymMonkeyget_scdictbase()
        mocketym.phoneme_inventory = ["d", "e", "f"]
        mocketym.phon2cv = {"d": "C", "e": "V", "f": "C"}
        mocketym.vow2fb = {"e": "F"}
        path2test_scdictbase = Path(__file__).parent / "test_scdictbase.txt"
        exp = {"a": ["e", "f", "d"],
               "b": ["d", "f", "e"],
               "c": ["f", "d", "e"],
               "C": ["f", "d"],
               "V": ["e"],
               "F": ["e"],
               "B": []}
        exp2 = {"a": ["e"],
                "b": ["d"],
                "c": ["f"],
                "C": ["f"],
                "V": ["e"],
                "F": ["e"],
                "B": []}

        def tqdm_mock(pdseries):
            tqdm_mock.called_with = pdseries
            return pdseries
        tqdm = qs.tqdm
        qs.tqdm = tqdm_mock

        # assert if output is returned, asigned to self, and written correctly
        assert Etym.get_scdictbase(
            self=mocketym, write_to=path2test_scdictbase) == exp
        assert mocketym.scdictbase == exp
        with open(path2test_scdictbase, "r", encoding="utf-8") as f:
            assert literal_eval(f.read()) == exp

        # assert correct output with howmany=1 instead of inf
        assert Etym.get_scdictbase(
            self=mocketym,
            write_to=path2test_scdictbase,
            most_common=1) == exp2
        assert mocketym.scdictbase == exp2
        with open(path2test_scdictbase, "r", encoding="utf-8") as f:
            assert literal_eval(f.read()) == exp2

    # assert calls
    assert_series_equal(qs.tqdm.called_with, Series(
        ["a", "b", "c"], name="ipa"))
    read_csv_mock.assert_called()
    assert mocketym.rank_closest_called_with == [
        ['a', float("inf")], ['b', float("inf")], ['c', float("inf")],
        ['ə', float("inf"), ['d', 'f']], ['ə', float("inf"), ['e']],
        ['a', 1], ['b', 1], ['c', 1], ['ə', 1, ['d', 'f']], ['ə', 1, ['e']]]
    # tear down
    qs.tqdm = tqdm
    remove(path2test_scdictbase)
    del mocketym, path2test_scdictbase, exp, tqdm, EtymMonkeyget_scdictbase

def test_rank_closest_phonotactics():
    """test if getting the distance between to phonotactic structures works"""

    # set up
    mocketym = EtymMonkey()
    mocketym.phonotactic_inventory = None
    with raises(InventoryMissingError) as inventorymissingerror_mock:
        # assert error is raised
        Etym.rank_closest_phonotactics(
            self=mocketym,
            struc="CV",
            howmany=float("inf"))
    # assert error message
    assert str(
        inventorymissingerror_mock.value
    ) == "define phonotactic inventory or forms.csv"

    # set up: create instance of empty mock class,
    #  plug in inventory of phonotactic structures,
    # mock edit_distance_with2ops and pick_minmax
    mocketym = EtymMonkey()
    mocketym.phonotactic_inventory = ["CVC", "CVCVCC"]
    with patch("loanpy.qfysc.edit_distance_with2ops", side_effect=[
            1, 0.98]) as edit_distance_with2ops_mock:
        with patch("loanpy.qfysc.pick_minmax") as pick_minmax_mock:
            pick_minmax_mock.return_value = ["CVCVCC", "CVC"]

            # assert the correct closest string is picked
            assert Etym.rank_closest_phonotactics(
                self=mocketym, struc="CVCV") == "CVCVCC, CVC"

    # assert calls
    edit_distance_with2ops_mock.assert_has_calls(
        [call("CVCV", "CVC"), call("CVCV", "CVCVCC")])
    pick_minmax_mock.assert_called_with(
        [('CVC', 1), ('CVCVCC', 0.98)], 9999999)

    # tear down
    del mocketym

def test_rank_closest():
    """test if phoneme-inventory is ranked correctly
    according to feature vectore distance to a given phoneme"""

    # set up custom class, create instance of it
    class EtymMonkeyrank_closest:
        def __init__(self):
            self.phoneme_inventory, self.dm_called_with = None, []
            self.dm_return = iter([1, 0, 2])

        def distance_measure(self, *args):
            arglist = [*args]
            self.dm_called_with.append(arglist)
            return next(self.dm_return)

    mocketym = EtymMonkeyrank_closest()

    # assert exception and exception message
    with raises(InventoryMissingError) as inventorymissingerror_mock:
        Etym.rank_closest(
            self=mocketym,
            ph="d",
            howmany=float("inf"),
            inv=None)
    assert str(inventorymissingerror_mock.value
               ) == "define phoneme inventory or forms.csv"

    # set up2: mock pick_minmax
    with patch("loanpy.qfysc.pick_minmax") as pick_minmax_mock:
        pick_minmax_mock.return_value = ["b", "a", "c"]

        # assert
        assert Etym.rank_closest(
            self=mocketym, ph="d", inv=[
                "a", "b", "c"]) == "b, a, c"

    # assert calls
    assert mocketym.dm_called_with == [['d', 'a'], ['d', 'b'], ['d', 'c']]
    pick_minmax_mock.assert_called_with(
        [('a', 1), ('b', 0), ('c', 2)], float("inf"))

    # set up3: overwrite mock class instance, mock pick_minmax anew
    mocketym = EtymMonkeyrank_closest()
    with patch("loanpy.qfysc.pick_minmax") as pick_minmax_mock:
        pick_minmax_mock.return_value = ["b", "a"]

        # assert pick_minmax picks mins correctly again
        assert Etym.rank_closest(
            self=mocketym, ph="d", inv=[
                "a", "b", "c"], howmany=2) == "b, a"

    # assert calls
    assert mocketym.dm_called_with == [['d', 'a'], ['d', 'b'], ['d', 'c']]
    pick_minmax_mock.assert_called_with([('a', 1), ('b', 0), ('c', 2)], 2)

    # set up4: check if phoneme inventory can be accessed through self
    mocketym = EtymMonkeyrank_closest()
    mocketym.phoneme_inventory = ["a", "b", "c"]
    with patch("loanpy.qfysc.pick_minmax") as pick_minmax_mock:
        pick_minmax_mock.return_value = "b"

        # assert pick_minmax picks mins correctly again
        assert Etym.rank_closest(
            self=mocketym,
            ph="d",
            inv=None,
            howmany=1) == "b"

    # assert calls
    assert mocketym.dm_called_with == [['d', 'a'], ['d', 'b'], ['d', 'c']]
    pick_minmax_mock.assert_called_with([('a', 1), ('b', 0), ('c', 2)], 1)

    # tear down
    del mocketym, EtymMonkeyrank_closest


def test_read_mode():
    """test if mode is read correctly"""

    # no setup or teardown needed for these assertions

    # assert exception and exception message
    with raises(WrongModeError) as wrongmodeerror_mock:
        read_mode(mode="neitheradaptnorreconstruct")
    assert str(
        wrongmodeerror_mock.value
    ) == "parameter <mode> must be 'adapt' or 'reconstruct'"

    assert read_mode("adapt") == "adapt"
    assert read_mode("reconstruct") == "reconstruct"
    assert read_mode(None) == "adapt"
    assert read_mode("") == "adapt"


def test_read_connector():
    """test if connector is read correctly"""
    # no setup or teardown needed for these assertions
    assert read_connector(connector=None, mode="adapt") == "<"
    assert read_connector(connector=None, mode=None) == "<"
    assert read_connector(connector=None, mode="reconstruct") == "<*"
    assert read_connector(
        connector=(" from ", " from *"),
        mode="reconstruct") == " from *"


def test_read_scdictbase():
    """test if scdictbase is generated correctly from ipa_all.csv"""

    # no setup needed for this assertion
    assert read_scdictbase(None) == {}

    # setup
    base = {"a": ["e", "o"], "b": ["p", "v"]}
    path = Path(__file__).parent / "test_read_scdictbase.txt"
    with open(path, "w", encoding="utf-8") as f:
        f.write(str(base))

    with patch("loanpy.qfysc.literal_eval") as literal_eval_mock:
        literal_eval_mock.return_value = base

        # assert
        assert read_scdictbase(base) == base
        assert read_scdictbase(path) == base

    # assert call
    literal_eval_mock.assert_called_with(str(base))

    # tear down
    remove(path)
    del base, path

#rewrite this by merging it with the other test_init below.
def test_init():
    """test if class Etym is initiated correctly"""

    # set up
    with patch("loanpy.qfysc.read_forms") as read_forms_mock:
        read_forms_mock.return_value = None
        with patch("loanpy.qfysc.forms2list") as forms2list_mock:
            forms2list_mock.return_value = None
            with patch("loanpy.qfysc.cldf2pd") as cldf2pd_mock:
                cldf2pd_mock.return_value = None
                with patch("loanpy.qfysc.Etym.get_inventories"
                           ) as get_inventories_mock:
                    get_inventories_mock.return_value = (None, None, None)
                    with patch("loanpy.qfysc.read_dst"
                               ) as read_dst_mock:
                        read_dst_mock.return_value = "distfunc"
                        with patch("loanpy.qfysc.read_mode") as read_mode_mock:
                            read_mode_mock.return_value = "adapt"
                            with patch("loanpy.qfysc.read_connector") as read_connector_mock:
                                read_connector_mock.return_value = "<"
                                # with patch("loanpy.qfysc.read_nsedict") as read_nsedict_mock:
                                #    read_nsedict_mock.return_value = {}
                                with patch("loanpy.qfysc.read_scdictbase"
                                           ) as read_scdictbase_mock:
                                    read_scdictbase_mock.return_value = {}
                                    mocketym = Etym()

                                    # assert
                                    assert mocketym.mode == "adapt"
                                    assert mocketym.connector == "<"
                                    assert mocketym.scdictbase == {}
                                    assert mocketym.vfb is None
                                    assert mocketym.dfety is None
                                    assert mocketym.phoneme_inventory is None
                                    assert mocketym.cluster_inventory is None
                                    assert mocketym.phonotactic_inventory is None
                                    assert mocketym.distance_measure == "distfunc"

                                    # double check with __dict__
                                    assert len(mocketym.__dict__) == 10
                                    assert mocketym.__dict__ == {
                                        'connector': '<',
                                        'mode': 'adapt',
                                        'scdictbase': {},
                                        'vfb': None} | {
                                            'cluster_inventory': None,
                                            'phoneme_inventory': None,
                                            'dfety': None,
                                            'distance_measure': 'distfunc',
                                            'forms_target_language': None,
                                            'phonotactic_inventory': None}

                read_mode_mock.assert_called_with("adapt")
                read_connector_mock.assert_called_with(None, "adapt")
                read_scdictbase_mock.assert_called_with(None)
                read_forms_mock.assert_called_with(None)
                forms2list_mock.assert_called_with(None, None)
                cldf2pd_mock.assert_called_with(
                    None, None, None)
                get_inventories_mock.assert_called_with(None, None, None, 9999999)
                read_dst_mock.assert_called_with(
                    "weighted_feature_edit_distance")

    del mocketym
    # set up 2
    dfmk = DataFrame({"Segments": ["abc", "def", "pou"],
                      "Cognacy": [1, 1, 2],
                      "Language_ID": ["lg2", "lg1", "lg2"]})
    with patch("loanpy.qfysc.read_forms") as read_forms_mock:
        read_forms_mock.return_value = dfmk
        with patch("loanpy.qfysc.forms2list") as forms2list_mock:
            forms2list_mock.return_value = ["abc", "pou"]
            with patch("loanpy.qfysc.cldf2pd") as cldf2pd_mock:
                cldf2pd_mock.return_value = "sth3"
                with patch("loanpy.qfysc.Etym.get_inventories"
                           ) as get_inventories_mock:
                    get_inventories_mock.return_value = ("sth4", "sth5", "sth6")
                    with patch("loanpy.qfysc.read_dst"
                               ) as read_dst_mock:
                        read_dst_mock.return_value = "sth7"
                        with patch("loanpy.qfysc.read_mode") as read_mode_mock:
                            read_mode_mock.return_value = "adapt"
                            with patch("loanpy.qfysc.read_connector") as read_connector_mock:
                                read_connector_mock.return_value = "<"
                                # with patch("loanpy.qfysc.read_nsedict") as read_nsedict_mock:
                                #    read_nsedict_mock.return_value = {}
                                with patch("loanpy.qfysc.read_scdictbase"
                                           ) as read_scdictbase_mock:
                                    read_scdictbase_mock.return_value = {}

                                    mocketym = Etym(
                                        forms_csv="path", source_language="lg1",
                                        target_language="lg2")

                                    # assert
                                    assert mocketym.mode == "adapt"
                                    assert mocketym.connector == "<"
                                    assert mocketym.scdictbase == {}
                                    assert mocketym.vfb is None
                                    assert mocketym.dfety is "sth3"
                                    assert mocketym.phoneme_inventory is "sth4"
                                    assert mocketym.cluster_inventory is "sth5"
                                    assert mocketym.phonotactic_inventory is "sth6"
                                    assert mocketym.distance_measure == "sth7"

                                    # double check with __dict__
                                    assert len(mocketym.__dict__) == 10
                                    assert mocketym.__dict__ == {
                                        'connector': '<',
                                        'mode': 'adapt',
                                        'scdictbase': {},
                                        'vfb': None,
                                        'cluster_inventory': "sth5",
                                        'phoneme_inventory': "sth4",
                                        'dfety': "sth3",
                                        'distance_measure': 'sth7',
                                        'forms_target_language': ["abc", "pou"],
                                        'phonotactic_inventory': "sth6"}

                read_mode_mock.assert_called_with("adapt")
                read_connector_mock.assert_called_with(None, "adapt")
                read_scdictbase_mock.assert_called_with(None)
                read_forms_mock.assert_called_with("path")
                forms2list_mock.assert_called_with(dfmk, "lg2")
                cldf2pd_mock.assert_called_with(dfmk, "lg1", "lg2")
                get_inventories_mock.assert_called_with(None, None, None, 9999999)
                read_dst_mock.assert_called_with(
                    "weighted_feature_edit_distance")

    # tear down
    del mocketym


def test_forms2list():
    "test if dff is converted to a list correctly"
    # test first break: return None if dff is None
    assert forms2list(None, "sth") is None

    # set up fake input df
    mock_df_in = DataFrame({"Segments": ["abc", "def", "pou"],
                            "Cognacy": [1, 1, 2],
                            "Language_ID": ["lg2", "lg1", "lg2"]})
    assert forms2list(mock_df_in, "lg2") == ["abc", "pou"]

def test_read_forms():
    """Check if CLDF's forms.csv is read in correctly"""

    # set up
    dfin = DataFrame({"Segments": ["a b c", "d e f"],  # pull together later
                      "Cognacy": ["ghi", "jkl"],
                      "Language_ID": [123, 456],
                      "randcol": ["mno", "pqr"]})
    dfexp = DataFrame({"Segments": ["abc", "def"],  # pulled together segments
                       "Cognacy": ["ghi", "jkl"],
                       "Language_ID": [123, 456]})
    path = Path(__file__).parent / "test_read_forms.csv"
    with patch("loanpy.qfysc.read_csv") as read_csv_mock:
        read_csv_mock.return_value = dfexp

        # assert
        assert read_forms(None) is None
        assert_frame_equal(read_forms(path), dfexp)

    # assert calls
    read_csv_mock.assert_called_with(
        path, usecols=['Segments', 'Cognacy', 'Language_ID'])

    # tear down
    del path, dfin, dfexp


def test_cldf2pd():
    """test if the CLDF format is correctly tranformed to a pandas dataframe"""

    # set up
    dfin = DataFrame({"Segments": ["a", "b", "c", "d", "e", "f", "g"],
                      "Cognacy": [1, 1, 2, 2, 3, 3, 3],
                      "Language_ID": ["lg1", "lg2", "lg1", "lg3",
                                      "lg1", "lg2", "lg3"]})
    dfexp = DataFrame({"Target_Form": ["b", "f"],
                       "Source_Form": ["a", "e"],
                       "Cognacy": [1, 3]})
    # only cognates are taken, where source and target language occur
    dfout = cldf2pd(dfin, source_language="lg1", target_language="lg2")

    # assert
    assert cldf2pd(None, source_language="whatever",
                   target_language="wtvr2") is None
    assert_frame_equal(dfout, dfexp)

    # tear down
    del dfout, dfexp, dfin


def test_read_dst():
    """check if getattr gets euclidean distance of panphon feature vectors"""

    # assert where no setup needed
    assert read_dst("") is None

    # set up monkey class
    class MonkeyDist:  # mock panphon's Distance() class
        def __init__(self): pass

        def weighted_feature_edit_distance(self): pass

    # initiate monkey class
    mockdist = MonkeyDist()

    # mock panphon.distance.Distance
    with patch("loanpy.qfysc.Distance") as Distance_mock:
        Distance_mock.return_value = mockdist
        out = read_dst("weighted_feature_edit_distance")

        # assert
        assert ismethod(out)  # check if it is a method of the mocked class

    # assert calls
    assert out == mockdist.weighted_feature_edit_distance
    Distance_mock.assert_called_with()  # the class was called without args

    # tear down
    del mockdist, out, MonkeyDist


def test_align():
    """test if align assigns the correct alignment-function to 2 strings"""

    # set up mock class
    class EtymMonkeyAlign:
        def __init__(self):
            self.align_lingpy_called_with = []
            self.align_clusterwise_called_with = []

        def align_lingpy(self, *args):
            self.align_lingpy_called_with.append([*args])
            return "lingpyaligned"

        def align_clusterwise(self, *args):
            self.align_clusterwise_called_with.append([*args])
            return "clusterwisealigned"

    # initiate mock class, plug in mode
    mockqfy = EtymMonkeyAlign()
    mockqfy.mode = "adapt"
    # assert if lingpy-alignment is assigned correctly if mode=="adapt"
    assert Etym.align(
        self=mockqfy,
        left="leftstr",
        right="rightstr") == "lingpyaligned"
    # assert call
    assert mockqfy.align_lingpy_called_with == [['leftstr', 'rightstr']]

    # set up mock class, plug in mode
    mockqfy = EtymMonkeyAlign()
    mockqfy.mode = "reconstruct"
    # assert
    assert Etym.align(
        self=mockqfy,
        left="leftstr",
        right="rightstr") == "clusterwisealigned"
    # assert call
    assert mockqfy.align_clusterwise_called_with == [["leftstr", "rightstr"]]

    # tear down
    del mockqfy


def test_align_lingpy():
    """test if lingpy's pairwise alignment function is called correctly"""

    # set up instance of basic mock class, plug in phon2cv,
    # mock lingpy.Pairwise, mock pandas.DataFrame
    mockqfy = EtymMonkey()
    mockpairwise = PairwiseMonkey()
    mockqfy.phon2cv = {"h": "C", "a": "V", "l": "C"}
    with patch("loanpy.qfysc.Pairwise") as Pairwise_mock:
        Pairwise_mock.return_value = mockpairwise
        with patch("loanpy.qfysc.DataFrame") as DataFrame_Monkey:
            exp = {"keys": ["h", "a", "l", "V"], "vals": ["k", "a", "l", "a"]}
            DataFrame_Monkey.return_value = DataFrame(exp)

            # assert
            assert_frame_equal(
                Etym.align_lingpy(
                    self=mockqfy,
                    left="kala",
                    right="hal"),
                DataFrame(exp))

    # assert calls
    Pairwise_mock.assert_has_calls([call(
        seqs='kala', seqB='hal', merge_vowels=False)])
    # Pairwise always initiated by 3 args
    assert DataFrame_Monkey.call_args_list == [call(exp)]
    assert mockpairwise.align_called_with == [[]]

    # tear down
    del mockqfy, exp


def test_align_clusterwise():
    """test if loanpy's own clusterwise-alignment works"""

    # set up basic mock class, plug in phon2cv, create expected output var
    mockqfy = EtymMonkey()
    mockqfy.phon2cv = {
        "ɟ": "C", "ɒ": "V", "l": "C", "o": "V", "ɡ": "C", "j": "C"}
    exp = DataFrame({"keys": ['#-', '#ɟ', 'ɒ', 'l', 'o', 'ɡ#'],
                    "vals": ['-', 'j', 'ɑ', 'lk', 'ɑ', '-']})

    # assert
    assert_frame_equal(
        Etym.align_clusterwise(self=mockqfy, left="ɟɒloɡ", right="jɑlkɑ"), exp)

    # tear down
    del mockqfy, exp


def test_get_sound_corresp():
    """test if sound correspondences are extracted correctly"""

    # set up: the expected outcome of assert while mode=="adapt"
    exp = [{"a": ["a", "y", "ü"], "b": ["p", "v"], "i": ["e", "i"],
            "k": ["h", "c"], "u": ["u", "o"]},
           {'a<a': 1, 'e<i': 2, 'h<k': 2, 'p<b': 2, 'u<u': 1},
           {'a<a': [13], 'e<i': [12], 'h<k': [12], 'p<b': [13], 'u<u': [13]},
           {'d1': 0}, {'d2': 0}, {'d3': 0}]

    # set up: the expected outcome of assert while mode=="reconstruct"
    exp2 = [{'#-': ['-'], '#b': ['p'], '#k': ['h'], 'a#': ['a', 'ə', 'ʌ'],
             'b': ['p'], 'i': ['e', 'ə', 'œ'], 'i#': ['e', 'ə', 'œ'],
             'k': ['h'], 'u': ['u', 'ə', 'ʌ']},
            {'#-<*-': 2, '#b<*p': 1, '#k<*h': 1, 'a#<*a': 1, 'b<*p': 1,
             'i#<*e': 1, 'i<*e': 1, 'k<*h': 1, 'u<*u': 1},
            {'#-<*-': [12, 13], '#b<*p': [13], '#k<*h': [12],
             'a#<*a': [13], 'b<*p': [13], 'i#<*e': [12], 'i<*e': [12],
             'k<*h': [12], 'u<*u': [13]},
            {}, {}, {}]

    # set up: create instance 1 of mock class
    mockqfy = EtymMonkeyGetSoundCorresp(
        mode="adapt", connector="<", alignreturns1=DataFrame(
            {
                "keys": [
                    "k", "i", "k", "i"], "vals": [
                    "h", "e", "h", "e"]}), alignreturns2=DataFrame(
                        {
                            "keys": [
                                "b", "u", "b", "a"], "vals": [
                                    "p", "u", "p", "a"]}))

    # set up: create instance 2 of mock class
    mockqfy2 = EtymMonkeyGetSoundCorresp(  # necessary bc of iter()
        mode="reconstruct", connector="<*", vfb="əœʌ",
        alignreturns1=DataFrame(
            {"keys": ["#-", "#k", "i", "k", "i#"],
             "vals": ["-", "h", "e", "h", "e"]}),
        alignreturns2=DataFrame(
            {"keys": ["#-", "#b", "u", "b", "a#"],
             "vals": ["-", "p", "u", "p", "a"]}))

    # set up the side_effects of pandas.concat
    dfconcat = DataFrame({"keys": list("kikibuba"), "vals": list("hehepupa")})
    dfconcat2 = DataFrame(
        {"keys": ["#-", "#k", "i", "k", "i#", "#-", "#b", "u", "b", "a#"],
         "vals": ["-", "h", "e", "h", "e", "-", "p", "u", "p", "a"]})

    # set up path for param write_to
    path2test_get_sound_corresp = Path(
        __file__).parent / "test_get_sound_corresp.txt"

    # mock pandas.concat
    with patch("loanpy.qfysc.concat", side_effect=[
            dfconcat, dfconcat2]) as concat_mock:
        # groupby too difficult to mock
        # assert while mode=="adapt"
        assert Etym.get_sound_corresp(
            self=mockqfy, write_to=None) == exp
        try:  # assert that no file was being written
            remove(Path(__file__).parent / "soundchanges.txt")
            assert 1 == 2  # this asserts that the except part was being run
        except FileNotFoundError:  # i.e. the file was correctly not written
            pass
        # assert while mode=="reconstruct"
        assert Etym.get_sound_corresp(
            self=mockqfy2,
            write_to=path2test_get_sound_corresp) == exp2
        # assert that file was written
        with open(path2test_get_sound_corresp, "r", encoding="utf-8") as f:
            assert literal_eval(f.read()) == exp2

        # assert calls from assert while mode == "adapt"
        assert mockqfy.align_called_with == [
            ("kiki", "hehe"), ("buba", "pupa")]
        assert mockqfy.rank_closest_phonotactics_called_with == []  # no called
        for act, exp in zip(
            concat_mock.call_args_list[0][0][0], [
                mockqfy.df1, mockqfy.df2]):
            # first [0] picks the only call from list of calls
            # second [0] converts call object to tuple
            # third [0] picks the first element of the tuple (2nd is empty),
            # which is a list of two dataframes
            assert_frame_equal(act, exp)

    # assert calls of assert while mode == "reconstruct"
    assert mockqfy2.align_called_with == [
        ("kiki", "hehe"), ("buba", "pupa")]
    assert mockqfy2.rank_closest_phonotactics_called_with == []  # not called
    for act, exp in zip(
        concat_mock.call_args_list[1][0][0], [
            mockqfy2.df1, mockqfy2.df2]):
        # first [0] picks the only call from list of calls
        # second [0] converts call object to tuple
        # third [0] picks the first element of the tuple (2nd is empty),
        # which is a list of two dataframes
        assert_frame_equal(act, exp)

    # tear down
    remove(path2test_get_sound_corresp)
    del mockqfy, dfconcat, exp, path2test_get_sound_corresp


def test_get_phonotactics_corresp():
    """test if phonotactic correspondences are extracted correctly from data"""

    # set up instance of mock class, plug in attributes
    # def expected outcome var, vars for side-effects of mock-functions,
    # vars for expected calls
    # mock pandasDataFrame
    mockqfy = EtymMonkeyGetSoundCorresp(
        mode="adapt",
        connector="<",
        alignreturns1=None,
        alignreturns2=None)

    mockqfy.dfety = DataFrame({"Target_Form": ["kiki", "buba"],
                               "Source_Form": ["hehe", "pupa"],
                               "Cognacy": [12, 13]})
    mockqfy.left = "Target_Form"
    mockqfy.right = "Source_Form"
    mockqfy.connector = "<"
    exp = [{"CVCV": ["CVCV", "CVC", "CVCCC"]},
           {"CVCV<CVCV": 2},
           {"CVCV<CVCV": [12, 13]}]
    exp_call1 = list(zip(["CVCV", "CVCV"], ["CVCV", "CVCV"], [12, 13]))
    exp_call2 = {"columns": ["keys", "vals", "wordchange"]}

    path2test_get_phonotactics_corresp = Path(
        __file__).parent / "phonotctchange.txt"

    with patch("loanpy.qfysc.DataFrame") as DataFrame_mock:
        with patch("loanpy.qfysc.prosodic_string") as prosodic_string_mock:
            prosodic_string_mock.return_value = "CVCV"
            DataFrame_mock.return_value = DataFrame(
                {"keys": ["CVCV"] * 2, "vals": ["CVCV"] * 2,
                 "wordchange": [12, 13]})

            # assert
            assert Etym.get_phonotactics_corresp(
                self=mockqfy, write_to=path2test_get_phonotactics_corresp) == exp
            # assert file was written
            with open(path2test_get_phonotactics_corresp, "r",
                      encoding="utf-8") as f:
                assert literal_eval(f.read()) == exp

    # assert calls
    assert list(DataFrame_mock.call_args_list[0][0][0]) == exp_call1
    assert DataFrame_mock.call_args_list[0][1] == exp_call2
    prosodic_string_mock.assert_has_calls([call(list(i)) for i in ['hehe', 'pupa', 'kiki', 'buba']])
    assert mockqfy.rank_closest_phonotactics_called_with == ["CVCV"]

    # tear down
    remove(path2test_get_phonotactics_corresp)
    del mockqfy, exp, path2test_get_phonotactics_corresp
