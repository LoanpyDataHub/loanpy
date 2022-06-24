"""
Setup-Script for loanpy
"""

from setuptools import setup, find_packages
from pathlib import Path

setup(
  name='loanpy',
  packages=['loanpy'],
  version='2.0.2',
  license='afl-3.0',        # Chose a license from here: https://help.github.com/articles/licensing-a-repository
  description='a linguistic toolkit for predictions of loanword adaptation \
  and historical reconstructions',
  long_description=(Path(__file__).parent / "README.rst").read_text(),
  author='Viktor Martinović',
  author_email='viktor.martinovic@hotmail.com',
  url='https://github.com/martino-vic/loanpy',
  download_url='https://github.com/martino-vic/loanpy/archive/v.2.0-beta.tar.gz',    # I explain this later on
  keywords=['linguistics', 'loanword', 'historical', 'Hungarian'],
#  package_data={"loanpy": ["*", "tests/*",
#  "tests/output_files/*", "tests/input_files/*", "tests/expected_files/*"]},
  setup_requires=['pytest-runner'],
  tests_require=['pytest', 'flake8'],
  install_requires=[
"appdirs==1.4.4",
"attrs==21.4.0",
"clldutils==3.12.0",
"colorlog==6.6.0",
"csvw==2.0.0",
"cycler==0.11.0",
"editdistance==0.6.0",
"fonttools==4.33.3",
"gensim==4.2.0",
"ipatok==0.4.1",
"isodate==0.6.1",
"kiwisolver==1.4.2",
"latexcodec==2.0.1",
"lingpy==2.6.9",
"matplotlib==3.5.2",
"munkres==1.1.4",
"networkx==2.8.3",
"numpy==1.22.4",
"packaging==21.3",
"pandas==1.4.2",
"panphon==0.20.0",
"Pillow==9.1.1",
"pybtex==0.24.0",
"pycldf==1.26.1",
"pyparsing==3.0.9",
"python-dateutil==2.8.2",
"pytz==2022.1",
"PyYAML==6.0",
"regex==2022.6.2",
"rfc3986==1.5.0",
"scipy==1.8.1",
"six==1.16.0",
"smart-open==6.0.0",
"tabulate==0.8.9",
"tqdm==4.64.0",
"unicodecsv==0.14.1",
"uritemplate==4.1.1",
"pytest==7.1.2"
      ],
  classifiers=[
    'Development Status :: 4 - Beta',
    'Intended Audience :: Science/Research',
    'Topic :: Scientific/Engineering',
    'License :: OSI Approved :: Academic Free License (AFL)',
    'Natural Language :: English',
    'Operating System :: OS Independent',
    'Programming Language :: Python :: 3.9'
  ]
)
