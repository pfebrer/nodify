.. currentmodule:: nodify

***************
Nodifying
***************

The act of nodifying is performed by users mainly through the ``Node.from_func``
and ``Workflow.from_func`` methods.

Creating a workflow is particularly difficult, since one must split the function's
code into pieces of computation. This is done by getting the function's code and
parsing it into an Abstract Syntax Tree (AST), with python's built-in ``ast`` module.
The AST is then transformed and then converted back into code, which we execute to
generate the workflow. The class that we use for the transformation is:

.. autosummary::
   :toctree: generated/

   NodeConverter

This class is used by the utility functions:

.. autosummary::
   :toctree: generated/

   nodify_func
   nodify_code

to transform python code and python functions into workflows.

Finally, we have a function to convert all the functions of a module into nodes:

.. autosummary::
   :toctree: generated/

   nodify_module
