.. currentmodule:: nodify

*************
Workflows
*************

Workflows provide a way of splitting the functionality into pieces of computation,
allowing the user to recompute only the pieces that have been outdated once an
input changes.

As with ``Node``, each workflow class represents a computation. Therefore, each
function that you convert into a workflow will define a new class. This class
will be a subclass of ``Workflow``, which is the parent of all workflows.

.. autosummary::
   :caption: Workflow
   :toctree: generated/

   Workflow

``nodify`` does not provide specialized workflow subclasses, but you can certainly
create your own if you need to.
