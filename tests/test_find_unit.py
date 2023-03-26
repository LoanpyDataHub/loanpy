import pytest
from loanpy.find import phonetic_matches, semantic_matches
from unittest.mock import patch, call

@patch("loanpy.find.re.match", side_effect = [0, 0, 1, 0, 0, 0, 0, 0])
def test_phonetic_matches(re_match_mock):
    donor = [
        ['0', 'Donorese-0_hot1-1', 'e g e g', 'VCVC', 'hot', ['igig', 'agag']],
        ['1', 'Donorese-1_dog1-1', 'e g g e', 'VCCV', 'dog', ['iggi', 'agga']]
            ]
    recipient = [
        ['0', 'Recipientese-0', 'i k k i', 'cold', '^(i|u)(g)(g)(i|u)$'],
        ['1', 'Recipientese-1', 'i i k k', 'cat', '^(i|u)(i|u)(g)(g)$']
                ]

    assert phonetic_matches(donor, recipient) == 'ID\tloanID\tadrcID\tdf\tform\
\tpredicted\tmeaning\n0\t0\t0\trecipient\ti k k i\t^(i|u)(g)(g)(i|u)$\tcold\n1\
\t0\t1\tdonor\te g g e\tiggi\tdog'

    # 7  calls bc after matching with iggi it doesn't continue to agga
    assert re_match_mock.call_args_list == [
        call('^(i|u)(g)(g)(i|u)$', 'igig'),
        call('^(i|u)(g)(g)(i|u)$', 'agag'),
        call('^(i|u)(g)(g)(i|u)$', 'iggi'),
        call('^(i|u)(i|u)(g)(g)$', 'igig'),
        call('^(i|u)(i|u)(g)(g)$', 'agag'),
        call('^(i|u)(i|u)(g)(g)$', 'iggi'),
        call('^(i|u)(i|u)(g)(g)$', 'agga'),
    ]

@patch("loanpy.find.heapq.nlargest")
def test_semantic_matches(nlargest_mock):
    nlargest_mock.return_value = [['1', '0', '1', 'donor', 'e g g e',
        'iggi', 'dog', '3', 'y'], ['0', '0', '0', 'recipient', 'i k k i',
        '^(i|u)(g)(g)(i|u)$', 'cold', '3', 'x']]
    # Test case 3: Multiple row input
    phmtsv = [
        ["ID", "loanID", "adrcID", "df", "form", "predicted", "meaning"],
        ["0", "0", "0", "recipient", "i k k i", "^(i|u)(g)(g)(i|u)$", "cold"],
        ["1", "0", "1", "donor", "e g g e", "iggi", "dog"],
    ]
    assert semantic_matches(phmtsv, lambda x, y: [3, "x", "y"]) == \
'ID\tloanID\tadrcID\tdf\tform\tpredicted\tmeaning\tsemsim\tclosest_sem\
\n1\t0\t1\tdonor\te g g e\tiggi\tdog\t3\ty\
\n0\t0\t0\trecipient\ti k k i\t^(i|u)(g)(g)(i|u)$\tcold\t3\tx'

    assert nlargest_mock.call_args_list[0][0] == (1000, [
        ["0", "0", "0", "recipient", "i k k i",
         "^(i|u)(g)(g)(i|u)$", "cold", "3", "x"],
        ["1", "0", "1", "donor", "e g g e", "iggi", "dog", "3", "y"],
    ])