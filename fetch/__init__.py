"""Downloader for the ten Japanese general transmission and distribution operators' public
transformer loading files and transformer capacity tables.

Entry pages are fetched first and file links are resolved from their anchors, so file names
that change between releases (random path segments, fiscal-year suffixes) are never hard-coded.
"""
