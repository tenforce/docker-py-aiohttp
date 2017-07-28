#!/usr/bin/env python3

import os

from setuptools import setup, find_packages

ROOT_DIR = os.path.dirname(__file__)
SOURCE_DIR = os.path.join(ROOT_DIR)

version = None
exec(open('aiodockerpy/version.py').read())

with open('./requirements.txt') as reqs_txt:
    requirements = list(iter(reqs_txt))

with open('./requirements-test.txt') as test_reqs_txt:
    test_requirements = [line for line in test_reqs_txt]

setup(
    name="aiodockerpy",
    version=version,
    description="aiohttp port of docker-py.",
    url='https://github.com/tenforce/docker-py-aiohttp',
    packages=find_packages(exclude=["tests.*", "tests"]),
    install_requires=requirements,
    tests_require=test_requirements,
    zip_safe=False,
    test_suite='tests',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Environment :: Other Environment',
        'Intended Audience :: Developers',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3 :: Only',
        'Programming Language :: Python :: 3.6',
        'Topic :: Utilities',
        'License :: OSI Approved :: Apache Software License',
    ],
    maintainer='Cecile Tonglet',
    maintainer_email='cecile.tonglet@gmail.com',
)
