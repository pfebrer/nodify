.. currentmodule:: nodify

*************
Traversing node trees
*************

Once you start connecting nodes with one another, you might have pretty complex graphs.
We provide three utility functions to traverse the node tree in all possible ways:

.. autosummary::
   :toctree: generated/

   traverse_tree_forward
   traverse_tree_backward
   visit_all_connected

Once you are done traversing, e.g. because you have found the node that you were looking for,
you can raise a ``StopTraverse`` exception to stop the traversal.

.. autosummary::
   :toctree: generated/

   StopTraverse
