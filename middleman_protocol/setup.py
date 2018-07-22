#!/usr/bin/env python3

import os
from setuptools import setup


def get_version():
    with open(
        os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'RELEASE-VERSION',
        ),
        'r'
    ) as version_file:
        return version_file.read()


setup(
    name='Middleman-Protocol',
    version=get_version(),
    url='',
    maintainer='',
    maintainer_email='',
    packages=[
        'middleman_protocol',
    ],
    package_data={},
    python_requires='>=3.6',
    install_requires=[
        'construct==2.9.45',
        'golem_messages==2.10.1',
        'mypy==0.610',
    ],
    tests_require=[
        'mock==2.0.0',
        'pytest==3.6.2'
        'pytest-xdist==1.22.2',
    ],
)
