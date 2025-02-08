#!/bin/bash
mypython=/Users/h1nlee/miniconda3/envs/gitenv/bin/python

# Upload project to pypi

rm -rf ./build
rm -rf ./dist
rm -rf ./EzQmt.egg-info

$mypython setup.py sdist bdist_wheel
twine check dist/*
twine upload dist/*
# (-u __token__ -p password)
