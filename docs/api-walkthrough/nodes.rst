.. currentmodule:: nodify

*************
Nodes
*************

Each node class performs a given computation. That is, when you convert a function to be used
within ``nodify``, what you are doing is creating a node class. Instances of the node class are
then executions of such function.

The ``Node`` class is the parent of all nodes and therefore what you are going to convert your
functions to. However, ``nodify`` provides node classes for common things, like syntax constructs,
as they are used internally.

The ``Node`` class is the base class for all nodes. It orchestrates the behavior of the library.
Any new function that you incorporate into the framework is going to be a subclass of ``Node``.

.. autosummary::
   :caption: Node
   :toctree: generated/

   Node

Special nodes
==============

These nodes are special in the sense that they represent data structures rather than computation. However,
they are nodes because that facilitates the interplay with the rest of the framework.

.. autosummary::
   :toctree: generated/

   Batch
   Constant

Syntax nodes
=============

Nodes that represent syntax elements in Python code. Most likely you are not going to use these directly,
but they are the core of the library's functionality to translate regular python into workflows. They are
also key to providing lazy evaluation.

.. autosummary::
   :toctree: generated/

    ListNode
    TupleNode
    DictNode
    ConditionalExpressionNode
    CompareNode
    BinaryOperationNode
    UnaryOperationNode
    GetItemNode
    GetAttrNode
