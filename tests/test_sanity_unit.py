"""unit test for loanpy.sanity.py (2.0 BETA) for pytest 7.1.1"""

from collections import OrderedDict
from datetime import datetime
from os import remove
from pathlib import Path
from time import struct_time
from unittest.mock import call, patch

from numpy import nan
from pandas import DataFrame, Series, read_csv
from pandas.testing import assert_frame_equal, assert_series_equal
from pytest import raises

from loanpy.sanity import (
    ArgumentsAlreadyTested,
    cache,
    check_cache,
    eval_adapt,
    eval_recon,
    eval_all,
    eval_one,
    get_crossval_data,
    get_dist,
    get_nse4df,
    get_noncrossval_sc,
    get_tpr_fpr_opt,
    loop_thru_data,
    make_stat,
    plot_roc,
    postprocess,
    postprocess2,
    phonotactics_predicted,
    write_to_cache)

from loanpy import sanity


def test_cache():
    """Is cache read and written to correctly?"""
    with patch("loanpy.sanity.check_cache") as check_cache_mock:
        check_cache_mock.return_value = None
        with patch("loanpy.sanity.write_to_cache") as write_to_cache_mock:
            write_to_cache_mock.return_value = None

            @cache
            def mockfunc(*args, **kwargs): return 1, 2, 3, 4

            # without kwarg
            assert mockfunc(path2cache=4) is None
            check_cache_mock.assert_called_with(4, {'path2cache': 4})
            write_to_cache_mock.assert_called_with(
                4, {'path2cache': 4}, 2, 3, 4)

            # with kwarg
            assert mockfunc(4, 5, 6, path2cache=7) is None
            check_cache_mock.assert_called_with(7, {
                'path2cache': 7, 'forms_csv': 4, 'tgt_lg': 5, 'src_lg': 6})
            write_to_cache_mock.assert_called_with(7, {
                'path2cache': 7, 'forms_csv': 4,
                'tgt_lg': 5, 'src_lg': 6}, 2, 3, 4)


def test_eval_all():
    """Is the main function doing its job in evaluating etymological data?"""
    class AdrcMonkey:
        def __init__(self):
            self.dfety = 12345
    adrc_monkey = AdrcMonkey()
    # patch all functions. wrapper counts as part of eval_all
    with patch("loanpy.sanity.check_cache") as check_cache_mock:
        check_cache_mock.return_value = "cc"
        with patch("loanpy.sanity.write_to_cache") as write_to_cache_mock:
            write_to_cache_mock.return_value = "w2c"
            with patch("loanpy.sanity.time", side_effect=[5, 5]) as time_mock:
                with patch("loanpy.sanity.Adrc") as adrc_mock:
                    adrc_mock.return_value = AdrcMonkey
                    with patch("loanpy.sanity.loop_thru_data"
                               ) as loop_thru_data_mock:
                        loop_thru_data_mock.return_value = "ld"
                        with patch("loanpy.sanity.postprocess"
                                   ) as postprocess_mock:
                            postprocess_mock.return_value = adrc_monkey
                            with patch("loanpy.sanity.postprocess2"
                                       ) as postprocess2_mock:
                                postprocess2_mock.return_value = 987  # stat

                                assert eval_all(9, 9, 9) == (12345, 987, 5, 5)

    # assert calls
    check_cache_mock.assert_not_called()
    write_to_cache_mock.assert_not_called()
    time_mock.assert_has_calls([], [])
    adrc_mock.assert_called_with(
        forms_csv=9,
        source_language=9,
        target_language=9,
        mode='adapt',
        most_frequent_phonotactics=9999999,
        phonotactic_inventory=None,
        connector=None,
        scdictbase=None,
        vfb=None)
    loop_thru_data_mock.assert_called_with(
        AdrcMonkey, False, False, False, False, 1, 1, 100, 49, False, [
            10, 50, 100, 500, 1000], 'adapt', False, True)
    postprocess_mock.assert_called_with("ld")
    postprocess2_mock.assert_called_with(
        adrc_monkey,
        [10, 50, 100, 500, 1000],
        "adapt",
        None)

    del AdrcMonkey, adrc_monkey


def test_loop_thru_data():
    """Is cross-validation called and loop run?"""
    # set up expected output
    df_exp = DataFrame({
        "guesses": [1], "best_guess": [2],
        "workflow_step0": [3], "workflow_step1": [4]
    })

    dfforms_mock = DataFrame({
        "Segments_src": ["a p p l e", "b a n a n a", "c h e r r y"],
        "CV_Segments_src": ["a p.p.l e", "b a n a n a", "c.h e r.r y"],
        "Segments_tgt": ["A pf e l", "B a n a n e", "K i r sch e"],
        "CV_Segments_tgt": ["A p.f e l", "B a n a n e", "K i r s.c.h e"]
    })

    out1_eval_one = {"best_guess": "a b c", "guesses": 1}
    out2_eval_one = {"best_guess": "d e f", "guesses": 2}
    out3_eval_one = {"best_guess": "g h i", "guesses": 3}

    class AdrcMonkey:
        def __init__(self):
            self.dfety = dfforms_mock
            self.mode = "adapt"

#    def tqdm_mock(iterable):
#        tqdm_mock.called_with = iterable
#        return iterable
#    tqdm_real, sanity.tqdm = sanity.tqdm, tqdm_mock

    adrc_monkey = AdrcMonkey()
    idxlist = iter([0, 1, 2])
    forms = iter(["A pf e l", "B a n a n e", "K i r sch e"])
    # first patch is not called by default
    with patch("loanpy.sanity.get_noncrossval_sc") as get_noncrossval_sc_mock:
        with patch("loanpy.sanity.get_crossval_data",
                   side_effect=[adrc_monkey] * 3) as get_crossval_data_mock:
            adrc_monkey.idx_of_popped_word = next(idxlist)
            adrc_monkey.popped_word = next(forms)
            with patch("loanpy.sanity.eval_one",
                       side_effect=[out1_eval_one,
                                    out2_eval_one, out3_eval_one]
                       ) as eval_one_mock:
                with patch("loanpy.sanity.DataFrame") as DataFrame_mock:
                    DataFrame_mock.return_value = "dfoutmock"
                    with patch("loanpy.sanity.concat") as concat_mock:
                        concat_mock.return_value = df_exp
                        assert loop_thru_data(
                            adrc_monkey, 1, 1, 100, 49,
                            False, False, False, False, False,
                            [10, 50, 100, 500, 1000],
                            'adapt', False, True) == adrc_monkey
                        # assert dfety was plugged in with good col names
                        assert_frame_equal(adrc_monkey.dfety, df_exp)

    # assert calls
    # assert 1st patch not called
    get_noncrossval_sc_mock.assert_not_called()
    get_crossval_data_mock.assert_has_calls([
        call(adrc_monkey, 0, False),
        call(adrc_monkey, 1, False),
        call(adrc_monkey, 2, False)
    ])

    eval_one_mock.assert_has_calls([
        call("A pf e l", adrc_monkey, "a p p l e", 1, 1, 100, 49, False,
             False, False, False, False, [10, 50, 100, 500, 1000], 'adapt'),
        call("B a n a n e", adrc_monkey, "b a n a n a", 1, 1, 100, 49, False,
             False, False, False, False, [10, 50, 100, 500, 1000], 'adapt'),
        call("K i r sch e", adrc_monkey, "c h e r r y", 1, 1, 100, 49, False,
             False, False, False, False, [10, 50, 100, 500, 1000], 'adapt')
    ])

    DataFrame_mock.assert_called_with({'best_guess': ['a b c', 'd e f', 'g h i'],
                                       'guesses': [1, 2, 3]})
    concat_mock.assert_called_with([dfforms_mock, "dfoutmock"], axis=1)
#    assert isinstance(tqdm_mock.called_with, enumerate)

    # tear down
#    sanity.tqdm.called_with = None

    # 2nd assertion: loop with crossval=True

    # fresh instance (old got modified)
    adrc_monkey = AdrcMonkey()

    with patch("loanpy.sanity.get_noncrossval_sc") as get_noncrossval_sc_mock:
        get_noncrossval_sc_mock.return_value = adrc_monkey
        with patch("loanpy.sanity.get_crossval_data"
                   ) as get_crossval_data_mock:
            with patch("loanpy.sanity.eval_one",
                       side_effect=[out1_eval_one,
                                    out2_eval_one, out3_eval_one]
                       ) as eval_one_mock:
                with patch("loanpy.sanity.DataFrame") as DataFrame_mock:
                    DataFrame_mock.return_value = "dfoutmock"
                    with patch("loanpy.sanity.concat") as concat_mock:
                        concat_mock.return_value = DataFrame(
                            [(1, 2, 3, 4)],
                            columns=['guesses', 'best_guess',
                                     'workflow_step0', 'workflow_step1'])
                        assert loop_thru_data(
                            adrc_monkey, 1, 1, 100, 49,
                            False, False, False, False, False,
                            [10, 50, 100, 500, 1000],
                            'adapt', False, False) == adrc_monkey
                        assert_frame_equal(adrc_monkey.dfety, df_exp)

    # assert calls
    # assert 1st patch not called
    get_crossval_data_mock.assert_not_called()
    get_noncrossval_sc_mock.assert_called_with(adrc_monkey, False)

    eval_one_mock.assert_has_calls([
        call("A pf e l", adrc_monkey, "a p p l e", 1, 1, 100, 49, False,
             False, False, False, False, [10, 50, 100, 500, 1000], 'adapt'),
        call("B a n a n e", adrc_monkey, "b a n a n a", 1, 1, 100, 49, False,
             False, False, False, False, [10, 50, 100, 500, 1000], 'adapt'),
        call("K i r sch e", adrc_monkey, "c h e r r y", 1, 1, 100, 49, False,
             False, False, False, False, [10, 50, 100, 500, 1000], 'adapt')
    ])

    DataFrame_mock.assert_called_with({'best_guess': ['a b c', 'd e f', 'g h i'],
                                       'guesses': [1, 2, 3]})
    concat_mock.assert_called_with([dfforms_mock, "dfoutmock"], axis=1)
#    assert isinstance(tqdm_mock.called_with, enumerate)

    # tear down
#    sanity.tqdm = tqdm_real

    del adrc_monkey, AdrcMonkey, dfforms_mock, df_exp


def test_eval_one():
    """Are eval_adapt, eval_recon called and their results evaluated?"""
    class AdrcMonkey:
        pass
    adrc_monkey = AdrcMonkey()

    # test when target is hit in first round
    with patch("loanpy.sanity.eval_adapt") as eval_adapt_mock:
        with patch("loanpy.sanity.eval_recon") as eval_recon_mock:
            eval_adapt_mock.return_value = {
                "guesses": 123, "best_guess": "b l a"}
            assert eval_one("a p.p.l e", "A pf e l", adrc_monkey, False,
                            False, False, False, 1, 1, 100, 49, False,
                            [10, 50, 100, 500, 1000], 'adapt'
                            ) == {"guesses": 123, "best_guess": "b l a"}

    # assert correct args were passed on to eval_adapt
    eval_adapt_mock.assert_called_with(
        "a p.p.l e",
        "A pf e l",
        adrc_monkey,
        10,
        False,
        False,
        False,
        False,
        1,
        1,
        100,
        49,
        False)
    # assert eval_recon was not called
    eval_recon_mock.assert_not_called()

    # test when target is hit in 2nd round
    with patch("loanpy.sanity.eval_adapt",
               side_effect=[
                   {"guesses": float("inf"), "best_guess": "b l i"},
                   {"guesses": 123, "best_guess": "b l a"}]) as eval_adapt_mock:
        with patch("loanpy.sanity.eval_recon") as eval_recon_mock:
            assert eval_one("a p.p.l e", "A pf e l", adrc_monkey, False,
                            False, False, False, 1, 1, 100, 49, False,
                            [10, 50, 100, 500, 1000], 'adapt'
                            ) == {"guesses": 123, "best_guess": "b l a"}

    # eval_adapt called twice
    eval_adapt_mock.assert_has_calls([
        call("a p.p.l e", "A pf e l", adrc_monkey,
             10, False, False, False, False, 1, 1, 100, 49, False),
        call("a p.p.l e", "A pf e l", adrc_monkey,
             50, False, False, False, False, 1, 1, 100, 49, False)])
    # assert eval_recon was not called
    eval_recon_mock.assert_not_called()

    # test when target is hit in 3rd round
    with patch("loanpy.sanity.eval_adapt",
               side_effect=[
                   {"guesses": float("inf"), "best_guess": "b l i"},
                   {"guesses": float("inf"), "best_guess": "b l a"},
                   {"guesses": 123, "best_guess": "b l u"}]
               ) as eval_adapt_mock:
        assert eval_one("a p.p.l e", "A pf e l", adrc_monkey, False,
                        False, False, False, 1, 1, 100, 49, False,
                        [10, 50, 100, 500, 1000], 'adapt'
                        ) == {"guesses": 123, "best_guess": "b l u"}

    # eval_adapt called 3 times
    eval_adapt_mock.assert_has_calls([
        call("a p.p.l e", "A pf e l", adrc_monkey,
             10, False, False, False, False, 1, 1, 100, 49, False),
        call("a p.p.l e", "A pf e l", adrc_monkey,
             50, False, False, False, False, 1, 1, 100, 49, False),
        call("a p.p.l e", "A pf e l", adrc_monkey,
             100, False, False, False, False, 1, 1, 100, 49, False)])

    # assert eval_recon was not called
    eval_recon_mock.assert_not_called()

    # test when target is not hit
    with patch("loanpy.sanity.eval_adapt") as eval_adapt_mock:
        eval_adapt_mock.return_value = {"guesses": float("inf"),
                                        "best_guess": "b l a"}
        with patch("loanpy.sanity.eval_recon") as eval_recon_mock:
            assert eval_one("a p.p.l e", "A pf e l", adrc_monkey, False,
                            False, False, False, 1, 1, 100, 49, False,
                            [10, 50, 100, 500, 1000], 'adapt'
                            ) == {"guesses": float("inf"), "best_guess": "b l a"}

    # assert eval_adapt called as many times as guesslist is long
    eval_adapt_mock.assert_has_calls([
        call("a p.p.l e", "A pf e l", adrc_monkey,
             10, False, False, False, False, 1, 1, 100, 49, False),
        call("a p.p.l e", "A pf e l", adrc_monkey,
             50, False, False, False, False, 1, 1, 100, 49, False),
        call("a p.p.l e", "A pf e l", adrc_monkey,
             100, False, False, False, False, 1, 1, 100, 49, False),
        call("a p.p.l e", "A pf e l", adrc_monkey,
             500, False, False, False, False, 1, 1, 100, 49, False),
        call("a p.p.l e", "A pf e l", adrc_monkey,
             1000, False, False, False, False, 1, 1, 100, 49, False)
    ])
    # assert eval_recon was not called
    eval_recon_mock.assert_not_called()

    # test if reconstruct is called when mode=="reconstruct"
    with patch("loanpy.sanity.eval_recon") as eval_recon_mock:
        eval_recon_mock.return_value = {"guesses": float("inf"),
                                        "best_guess": "b l a"}
        with patch("loanpy.sanity.eval_adapt") as eval_adapt_mock:
            assert eval_one("a p.p.l e", "A pf e l", adrc_monkey, False,
                            False, False, False, 1, 1, 100, 49, False,
                            [10, 50, 100, 500, 1000], 'reconstruct'
                            ) == {"guesses": float("inf"), "best_guess": "b l a"}

    # eval eval_recon called as many times as guesslist is long
    eval_recon_mock.assert_has_calls([
        call("a p.p.l e", "A pf e l", adrc_monkey,
             10, False, False, False, False, 1, 1, 100, 49, False),
        call("a p.p.l e", "A pf e l", adrc_monkey,
             50, False, False, False, False, 1, 1, 100, 49, False),
        call("a p.p.l e", "A pf e l", adrc_monkey,
             100, False, False, False, False, 1, 1, 100, 49, False),
        call("a p.p.l e", "A pf e l", adrc_monkey,
             500, False, False, False, False, 1, 1, 100, 49, False),
        call("a p.p.l e", "A pf e l", adrc_monkey,
             1000, False, False, False, False, 1, 1, 100, 49, False)
    ])
    # assert eval_adapt not called
    eval_adapt_mock.assert_not_called()

    del adrc_monkey, AdrcMonkey


def test_eval_adapt():
    """Is result of loanpy.Adrc.adrc.adapt evaluated?"""
    class AdrcMonkey:
        def __init__(self, adapt_returns=None, adapt_raises=None):
            self.workflow = {"step1": "ya", "step2": "ye", "step3": "yu"}
            self.adapt_returns = adapt_returns
            self.adapt_raises = adapt_raises
            self.adapt_called_with = []

        def adapt(self, *args):  # the patch. This is being run.
            self.adapt_called_with.append([self, *args])
            if self.adapt_raises is not None:
                raise self.adapt_raises()
            return self.adapt_returns

    adrc_monkey = AdrcMonkey(adapt_raises=KeyError)

    sanity.Adrc, real_Adrc = AdrcMonkey, sanity.Adrc

    # check if keyerror is handled correctly (no prediction possible)
    with patch("loanpy.sanity.get_howmany") as get_howmany_mock:
        get_howmany_mock.return_value = (1, 2, 3)
        # assert with show_workflow=False
        assert eval_adapt(
            "A pf e l",
            adrc_monkey,
            "a p.p.l e",
            10,
            1,
            1,
            100,
            49,
            False,
            False,
            False,
            False,
            False) == {
            'best_guess': 'KeyError',
            'guesses': float("inf")}
        get_howmany_mock.assert_called_with(10, 1, 1)
        # assert call
        assert adrc_monkey.adapt_called_with[0] == [
            adrc_monkey, "a p.p.l e",
            1, 2, 3, 100, 49, False, False, False, False, False]
        # assert with show_workflow=True
        assert eval_adapt(
            "A pf e l",
            adrc_monkey,
            "a p.p.l e",
            10,
            1,
            1,
            100,
            49,
            False,
            False,
            False,
            False,
            True) == {
            "best_guess": "KeyError",
            "guesses": float("inf"),
            "step1": "ya",
            "step2": "ye",
            "step3": "yu"}
        get_howmany_mock.assert_called_with(10, 1, 1)
        assert adrc_monkey.adapt_called_with[1] == [
            adrc_monkey, "a p.p.l e", 1, 2, 3, 100, 49,
            False, False, False, False, True]

    # check if valueerror is handled correctly (wrong predictions made)
    adrc_monkey = AdrcMonkey(adapt_returns="y a m d e l a v a s a, 2nd_g, 3rd_g")
    with patch("loanpy.sanity.get_howmany") as get_howmany_mock:
        get_howmany_mock.return_value = (1, 2, 3)
        assert eval_adapt("A pf e l", adrc_monkey, "a p.p.l e",
                          10, 1, 1, 100, 49,
                          False, False, False, False, False) == {
            # "didn't hit target but this was best guess"
            "guesses": float("inf"), "best_guess": "y a m d e l a v a s a"}
        get_howmany_mock.assert_called_with(10, 1, 1)
        assert adrc_monkey.adapt_called_with[0] == [
            adrc_monkey, "a p.p.l e", 1, 2, 3, 100, 49,
            False, False, False, False, False]
        # assert with show_workflow=True
        assert eval_adapt(
            "A pf e l",
            adrc_monkey,
            "a p.p.l e",
            10,
            1,
            1,
            100,
            49,
            False,
            False,
            False,
            False,
            True) == {
            "guesses": float("inf"),
            "best_guess": "y a m d e l a v a s a",
            "step1": "ya",
            "step2": "ye",
            "step3": "yu"}
        get_howmany_mock.assert_called_with(10, 1, 1)
        assert adrc_monkey.adapt_called_with[1] == [
            adrc_monkey, "a p.p.l e", 1, 2, 3, 100, 49,
            False, False, False, False, True]

    # -check if no error is handled correctly (right prediction made)
    adrc_monkey = AdrcMonkey(adapt_returns="y a m d e l a v a s a, d e f, A pf e l")
    with patch("loanpy.sanity.get_howmany") as get_howmany_mock:
        get_howmany_mock.return_value = (1, 2, 3)
        assert eval_adapt(
            "A pf e l",
            adrc_monkey,
            "a p.p.l e",
            10,
            1,
            1,
            100,
            49,
            False,
            False,
            False,
            False,
            False) == {
            'best_guess': 'A pf e l',
            'guesses': 3}
        # hit the target, so: best guess = target (even if not on index 0!)
        get_howmany_mock.assert_called_with(10, 1, 1)
        assert adrc_monkey.adapt_called_with[0] == [
            adrc_monkey, "a p.p.l e", 1, 2, 3, 100, 49,
            False, False, False, False, False]
        # assert with show_workflow=True
        assert eval_adapt(
            "A pf e l",
            adrc_monkey,
            "a p.p.l e",
            10,
            1,
            1,
            100,
            49,
            False,
            False,
            False,
            False,
            True) == {
            'best_guess': 'A pf e l',
            'guesses': 3,
            'step1': 'ya',
            'step2': 'ye',
            'step3': 'yu'}
        get_howmany_mock.assert_called_with(10, 1, 1)
        assert adrc_monkey.adapt_called_with[1] == [
            adrc_monkey, "a p.p.l e", 1, 2, 3, 100, 49,
            False, False, False, False, True]

    # tear down
    sanity.Adrc = real_Adrc
    del AdrcMonkey, adrc_monkey, real_Adrc


def test_eval_recon():
    """Is result of loanpy.adrc.Adrc.reconstruct evaluated?"""
    # set up
    class AdrcMonkey:
        def __init__(self, reconstruct_returns):
            self.reconstruct_returns = reconstruct_returns
            self.reconstruct_called_with = []

        def reconstruct(self, *args):  # the patch. This is being run.
            self.reconstruct_called_with.append([self, *args])
            return self.reconstruct_returns
    # plug in class
    sanity.Adrc, real_Adrc = AdrcMonkey, sanity.Adrc

    # 1: target not hit, keyerror (else condition)
    adrc_monkey = AdrcMonkey("#a, b c# not old")
    assert eval_recon(
        "A pf e l",
        adrc_monkey,
        "a p.p.l e",
        10,
        1,
        1,
        100,
        49,
        False,
        False,
        False,
        False,
        False) == {
        'best_guess': '#a, b c# not old',
        'guesses': float("inf")}
    # assert call (source and target gets flipped!)
    assert adrc_monkey.reconstruct_called_with[0] == [
        adrc_monkey, "a p.p.l e", 10, 1, 1, 100, 49,
        False, False, False, False, False]

    # target not hit, short regex (capital "A" missing)
    adrc_monkey = AdrcMonkey("(a)(p)(p|f)(e)?(l)(e)?")
    assert eval_recon(
        "A pf e l",
        adrc_monkey,
        "a p.p.l e",
        10,
        1,
        1,
        100,
        49,
        False,
        False,
        False,
        False,
        False) == {
        'best_guess': '(a)(p)(p|f)(e)?(l)(e)?',
        'guesses': float("inf")}
    # assert call
    assert adrc_monkey.reconstruct_called_with[0] == [
        adrc_monkey, "a p.p.l e", 10, 1, 1, 100, 49,
        False, False, False, False, False]

    # target not hit, long regex (capital "A" missing)
    adrc_monkey = AdrcMonkey("^Appele$|^Appel$")
    assert eval_recon(
        "A pf e l",
        adrc_monkey,
        "a p.p.l e",
        10,
        1,
        1,
        100,
        49,
        False,
        False,
        False,
        False,
        False) == {
        'best_guess': 'Appele',
        'guesses': float("inf")}
    # assert call
    assert adrc_monkey.reconstruct_called_with[0] == [
        adrc_monkey, "a p.p.l e", 10, 1, 1, 100, 49,
        False, False, False, False, False]

    # 2: target hit with short regex
    adrc_monkey = AdrcMonkey("(a|A) (p) (p|f) ?(e)? (l) ?(e)?")
    assert eval_recon(
        "A p f e l",
        adrc_monkey,
        "a p.p.l e",
        10,
        1,
        1,
        100,
        49,
        False,
        False,
        False,
        False,
        False) == {
        'best_guess': '(a|A) (p) (p|f) ?(e)? (l) ?(e)?',
        'guesses': 10}

    # 3: target hit with long regex
    adrc_monkey = AdrcMonkey(  # correct solution on index nr 5
        "^Appele$|^Appel$|^a p.p.l e$|^A p.p.l$|^A pf e l e$|^A pf e l$|^A pfle$|^Apfl$")
    assert eval_recon(
        "A pf e l",
        adrc_monkey,
        "a p.p.l e",
        10,
        1,
        1,
        100,
        49,
        False,
        False,
        False,
        False,
        False) == {
        'best_guess': 'A pf e l',
        'guesses': 6}

    # tear down
    sanity.Adrc = real_Adrc

    del adrc_monkey, real_Adrc, AdrcMonkey


def test_get_noncrossval_sc():
    """Are non-crossvalidated sound correspondences extracted and assigned?"""
    # set up
    class AdrcMonkey:
        def __init__(self): self.get_sound_corresp_called_with = []

        def get_sound_corresp(self, *args):
            self.get_sound_corresp_called_with.append([*args])
            return [1, 2, 3, 4, 5, 6]

    # test with writesc=False
    adrc_monkey = AdrcMonkey()
    get_noncrossval_sc(adrc_monkey, False)
    assert adrc_monkey.__dict__ == {
        'get_sound_corresp_called_with': [[False]],
        'scdict': 1, 'scdict_phonotactics': 4, 'sedict': 2}

    # test with writesc=Path
    adrc_monkey, path = AdrcMonkey(), Path()
    get_noncrossval_sc(adrc_monkey, path)
    assert adrc_monkey.__dict__ == {
        'get_sound_corresp_called_with': [[path]],
        'scdict': 1, 'scdict_phonotactics': 4, 'sedict': 2}

    del adrc_monkey, AdrcMonkey


def test_get_crossval_data():
    """check if correct row is dropped from df for cross-validation"""

    # set up mock class for input and instantiate it
    class AdrcMonkey:
        def __init__(self):
            self.get_sound_corresp_called_with = []
            self.dfety = DataFrame({"Segments_tgt":
                                    ["a p.p.l e", "banana", "cherry"],
                                    "color": ["green", "yellow", "red"]})

        def get_sound_corresp(self, *args):
            self.get_sound_corresp_called_with.append([*args])
            return [{"d1": "scdict"}, {"d2": "sedict"}, {},
                    {"d3": "scdict_phonotactics"}, {}, {}]

        def get_inventories(self, *args):
            return ({"a", "p", "l", "e", "b", "n", "c", "h", "r", "y"},
                    {"a", "p.p", "l", "e", "b", "n", "c.h", "r.r", "y"},
                    {"VCCVC", "CVCVCV", "CCVCCV"})

    adrc_monkey = AdrcMonkey()
    # set up actual output as variable
    adrc_obj_out = get_crossval_data(adrc_monkey, 1, None)

    # assert scdict and scdict_phonotactics were correctly plugged into
    # adrc_class
    assert adrc_obj_out.scdict == {"d1": "scdict"}
    assert adrc_obj_out.sedict == {"d2": "sedict"}
    assert adrc_obj_out.scdict_phonotactics == {"d3": "scdict_phonotactics"}
    assert adrc_monkey.get_sound_corresp_called_with == [[None]]

    # tear down
    del AdrcMonkey, adrc_monkey, adrc_obj_out


def test_postprocess():
    """Is result of loanpy.sanity.loop_thru_data postprocessed correctly?"""

    class MockIn:
        def __init__(self):
            self.mode = "adapt"
    mock_in = MockIn()
    # patch functions
    with patch("loanpy.sanity.get_nse4df",
               side_effect=["out1_getnse4df",
                            "out2_getnse4df"]) as get_nse4df_mock:
        with patch(
            "loanpy.sanity.phonotactics_\
predicted") as phonotactics_predicted_mock:
            phonotactics_predicted_mock.return_value = "out_phonotacticspred"
            with patch("loanpy.sanity.get_dist") as get_dist_mock:
                get_dist_mock.return_value = "out_getldnld"

                # assert return value
                assert postprocess(mock_in) == "out_getldnld"

    # assert calls
    get_dist_mock.assert_called_with("out_phonotacticspred", "best_guess")
    phonotactics_predicted_mock.assert_called_with("out2_getnse4df")
    get_nse4df_mock.assert_has_calls(
        [call(mock_in, 'Segments_tgt'), call('out1_getnse4df', 'best_guess')]
    )

    # test with show_workflow=False
    # patch functions
    with patch("loanpy.sanity.get_nse4df",
               side_effect=["out1_getnse4df",
                            "out2_getnse4df"]) as get_nse4df_mock:
        with patch("loanpy.\
sanity.phonotactics_predicted") as phonotactics_predicted_mock:
            phonotactics_predicted_mock.return_value = "out_phonotacticspred"
            with patch("loanpy.sanity.get_dist") as get_dist_mock:
                get_dist_mock.return_value = "out_getldnld"

                # assert return value
                assert postprocess(mock_in) == "out_getldnld"

    # assert calls
    get_dist_mock.assert_called_with("out_phonotacticspred", "best_guess")
    phonotactics_predicted_mock.assert_called_with(
        "out2_getnse4df")  # only called if show_workflow
    get_nse4df_mock.assert_has_calls(
        [call(mock_in, 'Segments_tgt'), call('out1_getnse4df', 'best_guess')]
    )


def test_postprocess2():
    """Is result of loanpy.sanity.postprocess postprocessed correctly?"""
    # set up
    df_exp = DataFrame({"guesses": [1, 2, 3]})

    class AdrcMonkey:
        def __init__(self): self.dfety = df_exp
    adrc_monkey = AdrcMonkey()

    # patch functions
    with patch("loanpy.sanity.get_tpr_fpr_opt") as get_tpr_fpr_opt_mock:
        get_tpr_fpr_opt_mock.return_value = ("x", "y", (7, 8, 9))
        with patch("loanpy.sanity.make_stat") as make_stat_mock:
            make_stat_mock.return_value = "out_stat"

            assert postprocess2(adrc_monkey, [4, 5, 6], None) == "out_stat"

    # assert calls
    assert_series_equal(get_tpr_fpr_opt_mock.call_args_list[0][0][0],
                        Series([1, 2, 3], name="guesses"))
    assert get_tpr_fpr_opt_mock.call_args_list[0][0][1] == [4, 5, 6]
    assert get_tpr_fpr_opt_mock.call_args_list[0][0][2] == 3

    make_stat_mock.assert_called_with(9, 8, 6, 3)

    # test with write=Path()

    path2out = Path(__file__).parent / "postprocess2.csv"
    # patch functions
    with patch("loanpy.sanity.get_tpr_fpr_opt") as get_tpr_fpr_opt_mock:
        get_tpr_fpr_opt_mock.return_value = ("x", "y", (7, 8, 9))
        with patch("loanpy.sanity.make_stat") as make_stat_mock:
            make_stat_mock.return_value = "out_stat"
            with patch("loanpy.sanity.plot_roc") as plot_roc_mock:
                plot_roc_mock.return_value = None

                assert postprocess2(
                    adrc_monkey,
                    [4, 5, 6],
                    "adapt.csv",
                    path2out) == "out_stat"

    # assert output was written
    assert_frame_equal(read_csv(path2out), df_exp)

    # assert calls
    assert_series_equal(get_tpr_fpr_opt_mock.call_args_list[0][0][0],
                        Series([1, 2, 3], name="guesses"))
    assert get_tpr_fpr_opt_mock.call_args_list[0][0][1] == [4, 5, 6]
    assert get_tpr_fpr_opt_mock.call_args_list[0][0][2] == 3

    make_stat_mock.assert_called_with(9, 8, 6, 3)

    # tear down
    remove(path2out)
    del adrc_monkey, AdrcMonkey, path2out


def test_get_nse4df():
    """Is normalised sum of examples for data frame calculated correctly?"""
    # set up
    df_exp = DataFrame()
    dfety = DataFrame({
    "Segments_src": ["a b c", "d e f", "g h i"],
    "CV_Segments_src": ["a b.c", "d e f", "g.h i"],
    "Segments_tgt": ["j k l", "m n o", "p q r"],
    "CV_Segments_tgt": ["j.k.l", "m.n o", "p.q.r"]})
    dfetynse = DataFrame({
        "NSE_Segments_tgt_src": [1, 5, 9],
        "SE_Segments_tgt_src": [2, 6, 10],
        "E_distr_Segments_tgt_src": [3, 7, 11],
        "align_Segments_tgt_src": [4, 8, 12]})

    class AdrcMonkey:
        def __init__(self):
            self.dfety = dfety
            self.get_nse_returns = iter(
                [(1, 2, 3, 4), (5, 6, 7, 8), (9, 10, 11, 12)])
            self.get_nse_called_with = []

        def get_nse(self, *args):
            self.get_nse_called_with.append([*args])
            return next(self.get_nse_returns)

    adrc_monkey = AdrcMonkey()

    with patch("loanpy.sanity.concat") as concat_mock:
        concat_mock.return_value = df_exp
        # assert output is correct
        adrc_monkey.mode = "adapt"
        out = get_nse4df(adrc_monkey, "Segments_tgt")
        assert isinstance(out, AdrcMonkey)
        assert_frame_equal(out.dfety, df_exp)

    # assert calls mock patch
    assert len(concat_mock.call_args_list[0][0]) == 1  # called with 1 list
    assert isinstance(concat_mock.call_args_list[0][0][0], list)
    assert len(concat_mock.call_args_list[0][0][0]) == 2  # len of that list
    # ele1 of that list
    assert_frame_equal(concat_mock.call_args_list[0][0][0][0], dfety)
    # ele2 of that list
    assert_frame_equal(concat_mock.call_args_list[0][0][0][1], dfetynse)

    # assert call to monkey
    assert adrc_monkey.get_nse_called_with == [["j k l", "a b c"], ["m n o", "d e f"],
                                               ["p q r", "g h i"]]


def test_phonotactics_predicted():
    """Correct boolean returned when checking if phonotactics was predicted?"""
    # set up
    df_in = DataFrame({
        "Segments_tgt": ["abc", "def", "ghi"],
        "ProsodicStructure_tgt": ["VCC", "CVC", "CCV"],
        "predicted_phonotactics": [["CCC", "VVV"], ["CVC"], ["CCV", "CCC"]]})

    df_exp = df_in.assign(phonotactics_predicted=[False, True, True])

    class AdrcMonkey():
        def __init__(self):
            self.dfety = df_in

    adrc_monkey = AdrcMonkey()
    # assert output
    with patch("loanpy.sanity.tokenise",
    side_effect=[["a", "b", "c"], ["d", "e", "f"], ["g", "h", "i"]]) as tokenise_mock:
        assert_frame_equal(phonotactics_predicted(adrc_monkey).dfety, df_exp)

    # test break - return input if KeyError, i.e. if col is missing from df
    adrc_monkey = AdrcMonkey()
    adrc_monkey.dfety = DataFrame()
    assert phonotactics_predicted(adrc_monkey) == adrc_monkey
    assert phonotactics_predicted(adrc_monkey).dfety.empty

def test_get_dist():
    """Are (normalised) Levenshtein Distances calculated correctly?"""
    # set up 1
    class DistMonkey:
        def __init__(self):
            self.fast_levenshtein_distance_returns = iter([1, 2, 3])
            self.fast_levenshtein_distance_called_with = []
            self.fast_levenshtein_distance_div_maxlen_returns = iter([4, 5, 6])
            self.fast_levenshtein_distance_div_maxlen_called_with = []

        def fast_levenshtein_distance(self, *args):
            self.fast_levenshtein_distance_called_with.append([*args])
            return next(self.fast_levenshtein_distance_returns)

        def fast_levenshtein_distance_div_maxlen(self, *args):
            self.fast_levenshtein_distance_div_maxlen_called_with.append(
                [*args])
            return next(self.fast_levenshtein_distance_div_maxlen_returns)

    # set up input
    dfety = DataFrame({
        "best_guess": ["will not buy", "record", "scrat.ched"],
        "Segments_tgt": ["won't buy", "tobacconists", "scrat.ched"]})

    class AdrcMonkey:
        def __init__(self):
            self.dfety = dfety

    adrc_monkey = AdrcMonkey()
    dist_monkey = DistMonkey()

    # set up expected outcome
    df_exp = dfety.assign(
        fast_levenshtein_distance_best_guess_tgt=[1, 2, 3],
        fast_levenshtein_distance_div_maxlen_best_guess_tgt=[4, 5, 6])

    # plug monkey into patch
    with patch("loanpy.sanity.Distance") as Distance_mock:
        Distance_mock.return_value = dist_monkey
        # assert output
        assert_frame_equal(get_dist(adrc_monkey, "best_guess").dfety, df_exp)

    # assert call1
    assert dist_monkey.fast_levenshtein_distance_called_with == [
        ["willnotbuy", "won'tbuy"],
        ["record", "tobacconists"],
        ["scratched", "scratched"]]
    # assert call2
    assert dist_monkey.fast_levenshtein_distance_div_maxlen_called_with == [
        ["willnotbuy", "won'tbuy"],
        ["record", "tobacconists"],
        ["scratched", "scratched"]]
    # assert call3
    Distance_mock.assert_called_with()

    # tear down
    del df_exp, dist_monkey, adrc_monkey, AdrcMonkey, DistMonkey, dfety


def test_make_stat():
    """Are statistics calculated correctly?"""
    # no set up or tear down needed. Nothing to mock.
    assert make_stat(opt_fp=0.099, opt_tp=0.6, max_fp=1000, len_df=10
                     ) == (100, "6/10", "60%")


def test_get_tpr_fpr_opt():
    """Is the true/false positive rate and optimum calculated correctly?"""
    # no steup or teardown or mock needed
    assert get_tpr_fpr_opt(
        guesses_needed=[10, None, 20, 4, 17, None, None, 8, 9, 120],
        guesses_made=[1, 3, 5, 7, 9, 99, 999],
        len_df=10) == (
        [0.0, 0.0, 0.1, 0.1, 0.3, 0.6, 0.7],
        [0.001, 0.003, 0.005, 0.007, 0.009, 0.099, 1.0],
        (0.501, 0.6, 0.099))


def test_plot_roc():
    """Is result plotted correctly to .jpg? Just asserting calls here."""
    # set up path to mock plot
    path2mockplot = Path(__file__).parent / "mockplot.jpg"
    # mock first input arg
    df_forms_mock = DataFrame(
        {"CV_Segments_src": ["k i k i", "b u b a", "k a b a"],
         "Segments_tgt": ["h e h e", "p u p a", "h a p a"],
         "guesses": [1, None, 3]})

    # test with lev_dist and norm_lev_dist == False (default settings)

    # mock all matplotlib funcs without mock return values
    with patch("loanpy.sanity.xlabel") as xlabel_mock:
        with patch("loanpy.sanity.ylabel") as ylabel_mock:
            with patch("loanpy.sanity.plot") as plot_mock:
                with patch("loanpy.sanity.scatter") as scatter_mock:
                    with patch("loanpy.sanity.title") as title_mock:
                        with patch("loanpy.sanity.legend") as legend_mock:
                            with patch("loanpy.sanity.savefig"
                                       ) as savefig_mock:
                                with patch("loanpy.sanity.clf") as clf_mock:
                                    # mocked savefig won't write any file

                                    # run function
                                    plot_roc(guesslist=[0, 1, 2],
                                             plot_to=path2mockplot,
                                             tpr_fpr_opt=(
                                        [0.0, 0.0, 0.1, 0.1, 0.3, 0.6, 0.7],
                                        [0.001, 0.003, 0.005,
                                         0.007, 0.009, 0.099, 1.0],
                                        (0.501, 0.6, 0.099)), opt_howmany=1,
                                        opt_tpr=0.6, len_df=3, mode="adapt")
                                    # mock write fig writes no file so nth 2
                                    # remove

    # assert all calls were made with the right args
    xlabel_mock.assert_called_with("fpr (100%=2)")
    ylabel_mock.assert_called_with("tpr (100%=3)")
    plot_mock.assert_called_with(
        [0.001, 0.003, 0.005, 0.007, 0.009, 0.099, 1.0],
        [0.0, 0.0, 0.1, 0.1, 0.3, 0.6, 0.7], label='ROC-curve')
    scatter_mock.assert_called_with(0.099, 0.6, marker='x', c='blue',
                                    label='Optimum:\nhowmany=1 -> tpr: 0.6')
    title_mock.assert_called_with('Predicting with \
loanpy.adrc.Adrc.adapt')
    legend_mock.assert_called_with()
    savefig_mock.assert_called_with(path2mockplot)
    clf_mock.assert_called_with()

    # tear down
    del path2mockplot, df_forms_mock


def test_check_cache():
    """test if DIY cache is initiated correctly and args checked in it"""

    # set up path of mock cache
    mockpath = Path(__file__).parent / "test_opt_param.csv"
    # make sure this file does not exist (e.g. from previous tests)
    try:
        remove(mockpath)
    except FileNotFoundError:
        pass
    # set up first expected outcome, a pandas data frame
    exp1 = DataFrame(columns=["arg1", "arg2", "arg3", "opt_tpr",
                              "optimal_howmany", "opt_tp", "timing", "date"])

    # assert first break works: cache not found
    check_cache(mockpath, {"arg1": "x", "arg2": "y", "arg3": "z"})
    assert_frame_equal(read_csv(mockpath), exp1)

    # tear down
    remove(mockpath)

    # check if exception is rased if these params were tested already

    # mock read_csv
    with patch("loanpy.sanity.read_csv") as read_csv_mock:
        read_csv_mock.return_value = DataFrame({"arg1": ["x"], "arg2": ["y"],
                                                "arg3": ["z"]})
        # assert exception is raised bc args exist in cache already
        with raises(ArgumentsAlreadyTested) as aat_mock:
            check_cache(mockpath,
                        {"arg1": "x", "arg2": "y", "arg3": "z"})
        assert str(aat_mock.value) == f"These arguments were tested \
already, see {mockpath} line 1! (start counting at 1 in 1st row)"

    # assert call for read_csv
    read_csv_mock.assert_called_with(mockpath,
                                     usecols=["arg1", "arg2", "arg3"])

    # check if nothing happens if arguments were NOT tested already
    with patch("loanpy.sanity.read_csv") as read_csv_mock:
        read_csv_mock.return_value = DataFrame({"arg1": ["a"], "arg2": ["b"],
                                                "arg3": ["c"]})
        # assert that the function runs, does nothing, and returns None
        assert check_cache(mockpath,
                           {"arg1": "x", "arg2": "y", "arg3": "z"}) is None

    # assert call for read_csv
    read_csv_mock.assert_called_with(mockpath,
                                     usecols=["arg1", "arg2", "arg3"])


def test_write_to_cache():
    """Test if the writing-part of cache functions."""
    # set up path to mock cache
    mock_cache_path = Path(__file__).parent / "mock_cache.csv"
    # set up mock init args, used in 2 places so var necessary
    init_args_mock = {"forms_csv": "forms.csv", "tgt_lg": "EAH",
                      "src_lg": "WOT", "crossval": True,
                      "path2cache": mock_cache_path,
                      "guesslist": [[2, 4, 6, 8]],
                      "max_phonotactics": 1, "max_paths": 1, "writesc": False,
                      "writesc_phonotactics": False, "vowelharmony": False,
                      "only_documented_clusters": False, "sort_by_nse": False,
                      "phonotactics_filter": False, "show_workflow": False,
                      "write": False,
                      "outname": "viz", "plot_to": None, "plotldnld": False}
    # set up return value of mocked read_csv, used in 2 places
    read_csv_mock_returns = DataFrame(columns=list(
        init_args_mock) + ["opt_tpr", "optimal_howmany",
                           "opt_tp", "timing", "date"])
    # set up 2 dfs with which concat is being valled
    df_concat_call1 = read_csv_mock_returns
    df_concat_call2 = DataFrame(
        {
            "forms_csv": ["forms.csv"],
            "tgt_lg": ["EAH"],
            "src_lg": ["WOT"],
            "crossval": ["True"],
            "path2cache": [
                str(mock_cache_path)],
            "guesslist": ["[[2, 4, 6, 8]]"],
            "max_phonotactics": ["1"],
            "max_paths": ["1"],
            "writesc": ["False"],
            "writesc_phonotactics": ["False"],
            "vowelharmony": ["False"],
            "only_documented_clusters": ["False"],
            "sort_by_nse": ["False"],
            "phonotactics_filter": ["False"],
            "show_workflow": ["False"],
            "write": ["False"],
            "outname": ["viz"],
            "plot_to": ["None"],
            "plotldnld": ["False"],
            "optimal_howmany": [0.501],
            "opt_tp": [0.6],
            "opt_tpr": [0.099],
            "timing": ["14:00"],
            "date": [
                datetime.now().strftime("%x %X")]})
    # set up mock cache
    DataFrame().to_csv(mock_cache_path, index=False, encoding="utf-8")
    # set up expected new cache
    df_exp = DataFrame(
        {"fruit": ["cherry", "banana", "a p.p.l e"],
         "color": ["red", "yellow", "green"],
         "opt_tpr": [0.8, 0.6, 0.4]})
    # mock pandas concat
    with patch("loanpy.sanity.concat") as concat_mock:
        concat_mock.return_value = DataFrame(
            {"fruit": ["a p.p.l e", "banana", "cherry"],
             "color": ["green", "yellow", "red"],
             "opt_tpr": [0.4, 0.6, 0.8]})
        # mock pandas read_csv
        with patch("loanpy.sanity.read_csv") as read_csv_mock:
            read_csv_mock.return_value = read_csv_mock_returns
            # mock strftime
            with patch("loanpy.sanity.strftime") as strftime_mock:
                strftime_mock.return_value = "14:00"

                # write to mock cache
                write_to_cache(
                    stat=(0.501, 0.6, 0.099),
                    init_args=init_args_mock,
                    path2cache=mock_cache_path, start=1, end=2)

                # assert cache was written correctly
                assert_frame_equal(read_csv(mock_cache_path), df_exp)

                # assert pandas concat call
                assert_frame_equal(
                    concat_mock.call_args_list[0][0][0][0], df_concat_call1)
                assert_frame_equal(
                    concat_mock.call_args_list[0][0][0][1], df_concat_call2)
                # assert pandas read_csv called with
                read_csv_mock.assert_called_with(mock_cache_path)
                # assert strftime call
                strftime_mock.assert_called()

    # tear down
    remove(mock_cache_path)
    del mock_cache_path, df_exp, read_csv_mock_returns, init_args_mock
