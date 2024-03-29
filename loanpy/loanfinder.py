# -*- coding: utf-8 -*-
"""
This module is designed to identify potential loanwords between a hypothesised
donor and recipient language. It processes two input dataframes, one
representing the donor language with predicted adapted forms and the other
the recipient language with predicted reconstructions. The module first finds
phonetic matches between the two languages and then calculates their semantic
similarity. The output is a list of candidate loanwords, which can be further
analysed manually.

The two functions in this module are responsible for finding phonetic
matches between the given donor and recipient language data and calculating
their semantic similarity. These functions process the input dataframes and
compare the phonetic patterns, as well as calculate the semantic similarity
based on a user-provided function. The module returns a list of candidate
loanwords that show phonetic and semantic similarities. The output can
then be used to propose lexical borrowings, adaptation patterns,
and historical reconstructions for words of the proposed donor and recipient
language.
"""
import csv
import logging
import re
from pathlib import Path
from typing import Any, Callable, List, Union

logging.basicConfig(  # set up logger (instead of print)
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
    )

def phonetic_matches(
        df_rc: List[List[str]],
        df_ad: List[List[str]],
        output: Union[str, Path],
        ) -> None:

    """
    Find phonetic matches between the given donor and recipient TSV files.

    The function processes the donor and recipient data frames,
    compares the phonetic patterns,
    and writes the result as a tsv-file to the specified output-path.

    :param df_ad: Table of the donor language data with adapted forms.
    :type df_ad: list of lists. Column 2 (index 1) must be a foreign key,
                 and Column 3 (index 2) a predicted loanword adaptation.
    :param df_rc: Table of the recipient language data with reconstructed
                  forms.
    :type df_rc: list of lists. Column 2 (index 1) must be a foreign key,
                 and Column 3 (index 2) a predicted reconstruction, ideally a
                 regular expression.
    :param output: The path to the output-file
    :type output: str or pathlike object

    :return: writes a tsv-file containing the matched data,
             with the following columns: ``ID`` -- the primary key of the
             table, ``ID_rc`` -- the foreign key of the reconstruction,
             ``ID_ad`` -- the foreign key of the adaptation.
    :rtype: None

    `Run in Google Colab >> <https://colab.research.google.com/drive/1JlHKfdff_yjCO8yvxiKV9xoRAiEPgarM#scrollTo=2Q9Y3yR7ZaOG&line=17&uniqifier=1>`__

    .. code-block:: python

        >>> from loanpy.loanfinder import phonetic_matches
        >>> donor = [
        ...     ['a0', 'Donorese-0', 'igig'],
        ...     ['a1', 'Donorese-1', 'iggi']
        ... ]
        >>> recipient = [
        ...     ['0', 'Recipientese-0', '^(i|u)(g)(g)(i|u)$'],
        ...     ['1', 'Recipientese-1', '^(i|u)(i|u)(g)(g)$']
        ... ]
        >>> outpath = "examples/phonetic_matches.tsv"
        >>> phonetic_matches(recipient, donor, outpath)
        >>> with open(outpath, "r") as f:
        ...     print(f.read())
        ID	ID_rc	ID_ad
        0	Recipientese-0	Donorese-1
    """
    phmid = 0
    with open(output, "w+") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(['ID', 'ID_rc', 'ID_ad'])
        for i, rcrow in enumerate(df_rc):
            last_match = None
            for adrow in df_ad:
                if last_match != adrow[1]:
                    if re.match(rcrow[2], adrow[2]):
                        writer.writerow([phmid, rcrow[1], adrow[1]])
                        phmid += 1
                        last_match = adrow[1]

            if (i + 1) % 50 == 0:
                logging.info(
                    f"{i+1}/{len(df_rc)} iterations completed"
                    )  # pragma: no cover

def semantic_matches(
        df_phonmatch: List[List[str]],
        get_semsim: Callable[[Any, Any], Union[float, int]],
        output: Union[str, Path],
        thresh: Union[int, float] = 0
        ) -> None:
    """
    Calculate the semantic similarity between pairs of rows in the input
    data frame using the provided semantic-similarity scoring function, add
    the information about the semantic similarity to each row. Write the file
    to the provided output-path.

    :param df_phonmatch: phonetic matches tsv, generated by
                   ``loanpy.find.phonetic_matches``. Each sublist represents a
                   row of data. The first sublist should contain the header
                   row, and each subsequent sublist should contain the data
                   for one row. The meanings have to be in columns 4 and 5
                   (index 3 and 4).
    :type df_phonmatch: list of lists of strings

    :param get_semsim: A function that calculates the semantic similarity
                       between two strings.
    :type get_semsim: function

    :param output: The path to the output-file
    :type output: str or pathlike object

    :param thresh: The threshold above which semantic matches count
    :type thresh: float, int

    :return: writes a tsv-file representing semantic
             matches in the input table with the added column of
             semantic similarity.
    :rtype: None

    `Run in Google Colab >> <https://colab.research.google.com/drive/1JlHKfdff_yjCO8yvxiKV9xoRAiEPgarM#scrollTo=1aSl5pabcbnI&line=16&uniqifier=1>`__

    .. code-block:: python

        >>> from loanpy.loanfinder import semantic_matches
        >>> def getsemsim(x, y):
        >>>     return 3
        >>> phmtsv = [
        ...     ["ID", "ID_rc", "ID_ad"],
        ...     ["0", "Recipientese-0", "Donorese-1", "cat", "dog"],
        ... ]
        >>> outpath = "examples/phonetic_matches.tsv"
        >>> semantic_matches(phmtsv, getsemsim, outpath)
        >>> with open(outpath, "r") as f:
        ...     print(f.read())
        ID	ID_rc	ID_ad	semsim
        0	Recipientese-0	Donorese-1	0.75
    """

    # Calculate semantic similarity and add columns to output rows
    with open(output, "w+") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(df_phonmatch[0][:3] + ["semsim"])  # header
        for i, row in enumerate(df_phonmatch[1:]):  # calculate semantic sim.
            semsim = get_semsim(row[3], row[4])
            if semsim >= thresh:
                writer.writerow(row[:3] + [round(semsim, 2)])

            if (i + 1) % 50 == 0:
                logging.info(
                    f"{i+1}/{len(df_phonmatch[1:])-1} iterations completed"
                    )  # pragma: no cover
