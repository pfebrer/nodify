from __future__ import annotations

import inspect
from types import FunctionType, ModuleType
from typing import Any, Callable, Dict, Sequence, Type

from .node import Node

__all__ = [
    "StopTraverse",
    "traverse_tree_forward",
    "traverse_tree_backward",
    "visit_all_connected",
    "nodify_module",
]


class StopTraverse(Exception):
    """Exception that should be raised by callback functions to stop the traversal of a tree."""


def traverse_tree_forward(roots: Sequence[Node], func: Callable[[Node], Any]) -> None:
    """Traverse a tree of nodes in a forward fashion.

    Parameters
    ----------
    roots : Sequence[Node]
        The roots of the tree to traverse.
    func : Callable[[Node], Any]
        The function to apply to each node in the tree. Note that you can raise
        a StopTraverse exception to stop the traversal of the tree for any reason.
    """
    for root in roots:
        try:
            func(root)
        except StopTraverse:
            continue
        traverse_tree_forward(root._output_links, func)


def traverse_tree_backward(leaves: Sequence[Node], func: Callable[[Node], Any]) -> None:
    """Traverse a tree of nodes in a backwards fashion.

    Parameters
    ----------
    leaves : Sequence[Node]
        The leaves of the tree to traverse.
    func : Callable[[Node], Any]
        The function to apply to each node in the tree. Note that you can raise
        a StopTraverse exception to stop the traversal of the tree for any reason.
    """
    for leaf in leaves:
        try:
            func(leaf)
        except StopTraverse:
            continue
        leaf.map_inputs(
            leaf.inputs,
            func=lambda node: traverse_tree_backward((node,), func=func),
            only_nodes=True,
        )


def visit_all_connected(
    nodes: Sequence[Node], func: Callable[[Node], Any], _seen_nodes=None
) -> None:
    """Visit all nodes that are connected to a list of nodes.

    Parameters
    ----------
    nodes : Sequence[Node]
        The nodes to traverse.
    func : Callable[[Node], Any]
        The function to apply to each node in the tree. Note that you can raise
        a StopTraverse exception to stop the traversal of the tree for any reason.
    """
    if _seen_nodes is None:
        _seen_nodes = []

    for node in nodes:
        if id(node) in _seen_nodes:
            continue

        _seen_nodes.append(id(node))

        try:
            func(node)
        except StopTraverse:
            continue

        def visit(visited_node):
            if visited_node is node:
                return

            visit_all_connected((visited_node,), func=func, _seen_nodes=_seen_nodes)
            raise StopTraverse

        traverse_tree_forward((node,), func=visit)
        traverse_tree_backward((node,), func=visit)


_nodified_modules = {}


def nodify_module(module: ModuleType, node_class: Type[Node] = Node) -> ModuleType:
    """Returns a copy of a module where all functions are replaced with nodes.

    This new nodified module contains only nodes (coming from functions or classes).
    The rest of variables are not copied. In fact, the new module uses the variables
    from the original module.

    Also, some functions might not be convertable to nodes and therefore won't be found
    in the new module.

    For each module that is found while traversing, its __nodify__ function is called
    if it exists.

    Parameters
    ----------
    module : ModuleType
        The module to nodify.
    node_class : Type[Node], optional
        The class from which the created nodes will inherit, by default Node.
        This can be useful for example to convert to workflows, if you pass
        the Workflow class.

    Returns
    -------
    ModuleType
        A new module with all functions replaced with nodes.
    """

    if module in _nodified_modules:
        return _nodified_modules[module]

    # Function that recursively traverses the module and replaces functions with nodes.
    def _nodified_module(
        module: ModuleType, visited: Dict[ModuleType, ModuleType], main_module: str
    ) -> ModuleType:
        # Call the __nodify__ function on the module if it exists.
        if hasattr(module, "__nodify__"):
            module.__nodify__()

        # This module has already been visited, so do return the already nodified module.
        if module in visited:
            return visited[module]

        # Create a copy of this module, with the nodified_ prefix in the name.
        noded_module = ModuleType(f"nodified_{module.__name__}")
        # Register the module as visited.
        visited[module] = noded_module

        all_vars = vars(module).copy()

        # Loop through all the variables in the module.
        for k, variable in all_vars.items():
            if k.startswith("__"):
                continue

            # Initialize the noded variable to None.
            noded_variable = None

            if isinstance(variable, (type, FunctionType)):
                # If the variable was not defined in the module that we are nodifying,
                # skip it. This is to avoid nodifying variables that were imported
                # from other modules.
                module_name = getattr(variable, "__module__", "") or ""
                if not (
                    isinstance(module_name, str) and module_name.startswith(main_module)
                ):
                    continue

                # If the variable is a function or a class, try to create a node from it.
                # There are some reasons why a function or class with exotic properties
                # might not be able to be converted to a node. We do not aim at nodifying them.
                try:
                    noded_variable = node_class.from_func(
                        variable, module=f"nodified_{variable.__module__}"
                    )
                except:
                    ...
            elif inspect.ismodule(variable):
                module_name = getattr(variable, "__name__", "") or ""
                if not (
                    isinstance(module_name, str) and module_name.startswith(main_module)
                ):
                    continue

                # If the variable is a module, recursively nodify it.
                noded_variable = _nodified_module(
                    variable, visited, main_module=main_module
                )

            # Add the new noded variable to the new module.
            if noded_variable is not None:
                setattr(noded_module, k, noded_variable)

        return noded_module

    nodified_module = _nodified_module(module, visited={}, main_module=module.__name__)

    _nodified_modules[module] = nodified_module

    return nodified_module
