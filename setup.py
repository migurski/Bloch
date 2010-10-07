#!/usr/bin/env python

from distutils.core import setup

version = '1.0.0'

setup(name='Bloch',
      version=version,
      description='Simplify linework in polygonal geographic datasources.',
      author='Michal Migurski',
      author_email='mike@stamen.com',
      url='http://github.com/migurski/Bloch',
      requires=['ModestMaps'],
      packages=['Bloch'],
      scripts=['blochify.py'],
      license='BSD')
