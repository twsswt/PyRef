# -*- coding: utf-8 -*-


"""setup.py: setuptools control."""

from setuptools import setup, find_packages

with open('README.md', 'rb') as f:
    long_descr = f.read().decode('utf-8')

with open('requirements.txt', 'rb') as f:
    requirements = f.read().decode('utf-8').split('\n')


setup(
    name='PyRef',
    packages=find_packages(),
    install_requires=requirements,
    zip_safe=False,
    include_package_data=True,
    version="0.0.1",
    description='Python Refactoring.',
    long_description=long_descr,
)
