.. nodify documentation master file, created by
   sphinx-quickstart on Sat May  4 10:44:42 2024.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

| |pypi| |conda| |license| |python-versions|

Nodify python package
==================================

If the Cambridge dictionary had an entry for the word "nodify", which it doesn't (for now),
it would look something like this:

-------------------------------------

| **nodify**
| verb
| *The art of converting python functions into nodes and connecting them to create a workflow. Once you start nodifying, you can't stop doing it.*

-------------------------------------

It is then fair from your side to ask: **"How can I start nodifying??"**.

Well, there are several ways to do it. Are you interested in...

- **Learning how to nodify hands on**. Find the tutorials on the left side bar, which will guide you through the process of creating nodes, workflows, and using the library to the full potential.
- **Help expand to the art of nodifying**. Find the library walkthrough on the left side bar, which explains the most important parts of the code. You can also explore the more hardcore Reference Documentation.

.. .. toctree::
..    :maxdepth: 2
..    :caption: Contents:

..    nodes_intro.ipynb

.. toctree::
   :maxdepth: 2
   :caption: Tutorials
   :hidden:

   tutorials/Nodes_intro.ipynb

.. toctree::
   :maxdepth: 2
   :caption: Library walkthrough
   :hidden:

   api-walkthrough/nodes
   api-walkthrough/workflows
   api-walkthrough/nodifying
   api-walkthrough/traversing

.. autosummary::
    :toctree: api/generated/
    :template: autosummary/custom-module-template.rst
    :recursive:
    :caption: Reference documentation

    nodify

.. |pypi| image:: https://badge.fury.io/py/nodify.svg
   :target: https://pypi.org/project/nodify

.. |license| image:: https://img.shields.io/badge/License-MIT%202.0-brightgreen.svg
   :target: https://github.com/pfebrer/nodify/blob/main/LICENSE

.. |conda| image:: https://anaconda.org/conda-forge/nodify/badges/version.svg
   :target: https://anaconda.org/conda-forge/nodify

.. |python-versions| image:: https://img.shields.io/pypi/pyversions/nodify.svg
   :target: https://pypi.org/project/nodify/
