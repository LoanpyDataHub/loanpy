# -*- coding: utf-8 -*-
"""
This module is designed to identify and analyze potential loanwords between a
donor and a recipient language. It processes two input dataframes, one
representing the donor language with adapted forms and the other representing
the recipient language with reconstructed forms. The module first identifies
phonetic matches between the two languages and then calculates their semantic
similarity. The output is a list of candidate loanwords, which can be further
analyzed for linguistic or historical purposes.

The primary functions in this module are responsible for finding phonetic
matches between the given donor and recipient language data and calculating
their semantic similarity. These functions process the input dataframes and
compare the phonetic patterns, as well as calculate the semantic similarity
based on a user-provided function. The module returns a list of candidate
loanwords ranked by their phonetic and semantic similarities. The output can
then be used to study linguistic borrowing, adaptation, and reconstruction
processes between the donor and recipient languages.
"""
import csv
import re

def phonetic_matches(df_rc, df_ad, output, max_ad=100):
    """
    Finds phonetic matches between the given donor and recipient TSV files.

    The function processes the donor and recipient data frames,
    compares the phonetic patterns,
    and returns the matched data as a string in TSV format.

    :param df_ad: Table of the donor language data with adapted forms.
    :type df_ad: list of lists. Column 5 must be a list of predicted
                 loanword adaptations. Col 0: ID in df_ad,
                 Col 2: The form of the word, Col 4: its meanings.

    :param df_rc: Table of the recipient language data with reconstructed
                  forms.
    :type df_rc: list of lists. Column 4 must contain predicted
                 reconstructions as a regular expression. Col 0: The ID in
                 df_rc, Col 2: The form of the word. Col 3: its meanings.

    :return: A string containing the matched data in TSV format,
             with the following columns:
             ID, loanID, adrcID, df, form, predicted, meaning.
    :rtype: str
    """
    phmid = 0
    with open(output, "w+") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(['ID', 'ID_rc', 'ID_ad'])
        for i, rcrow in enumerate(df_rc):
            last_match = None
            for j, adrow in enumerate(df_ad):
                if last_match != adrow[1]:
                    if re.match(rcrow[2], adrow[2]):
                        writer.writerow([phmid, rcrow[1], adrow[1]])
                        phmid += 1
                        last_match = adrow[1]
            print(f"{i+1}/{len(df_rc)} iterations completed", end="\r")

def semantic_matches(df_phonmatch, get_semsim, output, thresh=0):
    """
    Calculate the semantic similarity between pairs of rows in df_senses
    using the function get_semsim, and add columns with the calculated
    similarity and the closest semantic match to each row.

    :param df_senses: phonetic matches tsv, generated by
                   loanpy.find.phonetic_matches. Each sublist represents a
                   row of data. The first sublist should contain the header
                   row, and each subsequent sublist should contain the data
                   for one row. The meanings have to be in column 6.
    :type df_senses: list of lists

    :param get_semsim: A function that calculates the semantic similarity
                       between two strings.
    :type get_semsim: function

    :return: A tab-separated string representing the top 1000 semantically
             most similar meanings in df_senses with the added columns for
             semantic similarity and closest semantic match, sorted in
             descending order by semantic similarity and ascending order
             by loanID.
    :rtype: str
    """

    # Calculate semantic similarity and add columns to output rows
    with open(output, "w+") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(df_phonmatch[0][:3] + ["semsim"])  # header
        for i, row in enumerate(df_phonmatch[1:]):  # calculate semantic sim.
            semsim = get_semsim(row[3], row[4])
            if semsim >= thresh:
                writer.writerow(row[:3] + [round(semsim, 2)])
            print(f"{i+1}/{len(df_phonmatch[1:])-1} iterations completed", end="\r")
