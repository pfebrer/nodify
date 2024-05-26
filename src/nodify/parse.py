import ast
import inspect
import textwrap
from types import FunctionType
from typing import Any, Callable, Optional, Type, Union
from warnings import warn

from .node import ConstantNode, Node
from .syntax_nodes import ConditionalExpressionNode, DictNode, ListNode, TupleNode

__all__ = ["NodeConverter", "nodify_func", "nodify_code"]


class NodeConverter(ast.NodeTransformer):
    """AST transformer that converts a function into a workflow."""

    # ast_to_operator = {
    #     ast.Eq: "eq",
    #     ast.NotEq: "ne",
    #     ast.Lt: "lt",
    #     ast.LtE: "le",
    #     ast.Gt: "gt",
    #     ast.GtE: "ge",
    #     ast.Is: "is_",
    #     ast.IsNot: "is_not",
    #     ast.In: "contains",
    # }

    def __init__(
        self,
        *args,
        assign_fn: Union[str, None] = None,
        node_cls_name: str = "Node",
        constant_cls: str = "ConstantNode",
        nodify_constants: bool = False,
        nodify_constant_assignments: bool = False,
        remove_function_annotations: bool = False,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        self.assign_fn = assign_fn
        self.node_cls_name = node_cls_name
        self.constant_cls = constant_cls
        self.nodify_constants = nodify_constants
        self.nodify_constant_assignments = nodify_constant_assignments
        self.remove_function_annotations = remove_function_annotations

    def visit_Call(self, node):
        """Converts some_module.some_attr(some_args) into Node.from_func(some_module.some_attr)(some_args)"""
        node2 = ast.Call(
            func=ast.Call(
                func=ast.Attribute(
                    value=ast.Name(id=self.node_cls_name, ctx=ast.Load()),
                    attr="from_func",
                    ctx=ast.Load(),
                ),
                args=[self.visit(node.func)],
                keywords=[],
            ),
            args=[self.visit(arg) for arg in node.args],
            keywords=[self.visit(keyword) for keyword in node.keywords],
        )

        ast.fix_missing_locations(node2)

        return node2

    def visit_Assign(self, node):
        """Converts some_module.some_attr(some_args) into Node.from_func(some_module.some_attr)(some_args)"""

        if len(node.targets) > 1 or not isinstance(node.targets[0], ast.Name):
            return self.generic_visit(node)

        if self.nodify_constant_assignments and isinstance(node.value, ast.Constant):
            node.value = ast.Call(
                func=ast.Name(id=self.constant_cls, ctx=ast.Load()),
                args=[self.generic_visit(node.value)],
                keywords=[],
            )

            if self.assign_fn is not None:
                node.value = ast.Call(
                    func=ast.Name(id=self.assign_fn, ctx=ast.Load()),
                    args=[],
                    keywords=[
                        ast.keyword(arg="value", value=node.value),
                        ast.keyword(
                            arg="var_name", value=ast.Constant(value=node.targets[0].id)
                        ),
                    ],
                )

            ast.fix_missing_locations(node.value)

            return node

        elif self.assign_fn is None:
            return self.generic_visit(node)
        else:
            node.value = ast.Call(
                func=ast.Name(id=self.assign_fn, ctx=ast.Load()),
                args=[],
                keywords=[
                    ast.keyword(arg="value", value=self.visit(node.value)),
                    ast.keyword(
                        arg="var_name", value=ast.Constant(value=node.targets[0].id)
                    ),
                ],
            )

            ast.fix_missing_locations(node.value)

            return node

    def visit_List(self, node):
        """Converts the list syntax into a call to the ListNode."""
        if all(isinstance(elt, ast.Constant) for elt in node.elts):
            return self.generic_visit(node)

        new_node = ast.Call(
            func=ast.Name(id="ListNode", ctx=ast.Load()),
            args=[self.visit(elt) for elt in node.elts],
            keywords=[],
        )

        ast.fix_missing_locations(new_node)

        return new_node

    def visit_Tuple(self, node):
        """Converts the tuple syntax into a call to the TupleNode."""
        if all(isinstance(elt, ast.Constant) for elt in node.elts):
            return self.generic_visit(node)

        new_node = ast.Call(
            func=ast.Name(id="TupleNode", ctx=ast.Load()),
            args=[self.visit(elt) for elt in node.elts],
            keywords=[],
        )

        ast.fix_missing_locations(new_node)

        return new_node

    def visit_Dict(self, node: ast.Dict) -> Any:
        """Converts the dict syntax into a call to the DictNode."""
        if all(isinstance(elt, ast.Constant) for elt in node.values):
            return self.generic_visit(node)
        if not all(isinstance(elt, ast.Constant) for elt in node.keys):
            return self.generic_visit(node)

        new_node = ast.Call(
            func=ast.Name(id="DictNode", ctx=ast.Load()),
            args=[],
            keywords=[
                ast.keyword(arg=key.value, value=self.visit(value))
                for key, value in zip(node.keys, node.values)
            ],
        )

        ast.fix_missing_locations(new_node)

        return new_node

    def visit_IfExp(self, node: ast.IfExp) -> Any:
        """Converts the if expression syntax into a call to the ConditionalExpressionNode."""
        new_node = ast.Call(
            func=ast.Name(id="ConditionalExpressionNode", ctx=ast.Load()),
            args=[
                self.visit(node.test),
                self.visit(node.body),
                self.visit(node.orelse),
            ],
            keywords=[],
        )

        ast.fix_missing_locations(new_node)

        return new_node

    def visit_Constant(self, node: ast.Constant) -> Any:
        if self.nodify_constants:
            new_node = ast.Call(
                func=ast.Name(id=self.constant_cls, ctx=ast.Load()),
                args=[node],
                keywords=[],
            )

            ast.fix_missing_locations(new_node)

            return new_node
        else:
            return self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:

        if self.remove_function_annotations:

            def _remove_annotation(arg):
                arg.annotation = None
                return arg

            node.args.args = [_remove_annotation(arg) for arg in node.args.args]
            node.args.kwonlyargs = [
                _remove_annotation(arg) for arg in node.args.kwonlyargs
            ]
            node.args.posonlyargs = [
                _remove_annotation(arg) for arg in node.args.posonlyargs
            ]

            node.returns = None

        return self.generic_visit(node)

    # def visit_Compare(self, node: ast.Compare) -> Any:
    #     """Converts the comparison syntax into CompareNode call."""
    #     if len(node.ops) > 1:
    #         return self.generic_visit(node)

    #     op = node.ops[0]
    #     if op.__class__ not in self.ast_to_operator:
    #         return self.generic_visit(node)

    #     new_node = ast.Call(
    #         func=ast.Name(id="CompareNode", ctx=ast.Load()),
    #         args=[
    #             self.visit(node.left),
    #             ast.Constant(value=self.ast_to_operator[op.__class__], ctx=ast.Load()),
    #             self.visit(node.comparators[0]),
    #         ],
    #         keywords=[],
    #     )

    #     ast.fix_missing_locations(new_node)

    #     # new_node = ast.Call(
    #     #     func=ast.Name(id=self.ast_to_operator[op.__class__], ctx=ast.Load()),
    #     #     args=[self.visit(node.left), self.visit(node.comparators[0])],
    #     #     keywords=[],
    #     # )

    #     # ast.fix_missing_locations(new_node)

    #     return new_node


def nodify_func(
    func: FunctionType,
    transformer_cls: Type[NodeConverter] = NodeConverter,
    assign_fn: Union[Callable, None] = None,
    node_cls: Type[Node] = Node,
) -> FunctionType:
    """Converts all calculations of a function into nodes.

    This is used for example to convert a function into a workflow.

    The conversion is done by getting the function's source code, parsing it
    into an abstract syntax tree, modifying the tree and recompiling.

    Parameters
    ----------
    func : Callable
        The function to convert.
    transformer_cls : Type[NodeConverter], optional
        The NodeTransformer class to that is used to transform the AST.
    assign_fn : Union[Callable, None], optional
        A function that will be placed as middleware for variable assignments.
        It will be called with the following arguments:
            - value: The value assigned to the variable.
            - var_name: The name of the variable that will be assigned.
    node_cls : Type[Node], optional
        The Node class to which function calls will be converted.
    """
    # Get the function's namespace.
    closurevars = inspect.getclosurevars(func)
    func_namespace = {
        **closurevars.nonlocals,
        **closurevars.globals,
        **closurevars.builtins,
    }

    # Get the function's source code.
    code = inspect.getsource(func)
    # Make sure the first line is at the 0 indentation level.
    code = textwrap.dedent(code)

    old_signature = inspect.signature(func)

    code_obj = nodify_code(
        code,
        transformer_cls,
        assign_fn,
        node_cls,
        remove_function_annotations=True,
        namespace=func_namespace,
    )

    # Execute the code, and retrieve the new function from the namespace.
    exec(code_obj, func_namespace)

    new_func = func_namespace[func.__name__]

    new_func.__signature__ = old_signature

    return new_func


def nodify_code(
    code: str,
    transformer_cls: Type[NodeConverter] = NodeConverter,
    assign_fn: Union[Callable, None] = None,
    node_cls: Type[Node] = Node,
    nodify_constants: bool = False,
    nodify_constant_assignments: bool = False,
    remove_function_annotations: bool = False,
    namespace: Optional[dict] = None,
):
    if namespace is None:
        namespace = {}

    # Parse the source code into an AST.
    tree = ast.parse(code)

    # If the function has decorators, remove them. Perhaps in the future we can
    # support arbitrary decorators.
    first = tree.body[0]
    if isinstance(first, ast.FunctionDef):
        decorators = first.decorator_list
        if len(decorators) > 0:
            warn(
                f"Decorators are ignored for now when parsing code. Ignoring {len(decorators)} decorators on {first.name}"
            )
            first.decorator_list = []

    # The alias of the assign_fn function, which we make sure does not conflict
    # with any other variable in the function's namespace.
    assign_fn_key = None
    if assign_fn is not None:
        assign_fn_key = "__assign_fn"
        while assign_fn_key in namespace:
            assign_fn_key += "_"

    # We also make sure that the name of the node class does not conflict with
    # any other variable in the function's namespace.
    node_cls_name = node_cls.__name__
    while node_cls_name in namespace:
        node_cls_name += "_"

    # Transform the AST.
    transformer = transformer_cls(
        assign_fn=assign_fn_key,
        node_cls_name=node_cls_name,
        nodify_constants=nodify_constants,
        nodify_constant_assignments=nodify_constant_assignments,
        remove_function_annotations=remove_function_annotations,
    )
    new_tree = transformer.visit(tree)

    # Add the needed variables into the namespace.
    namespace.update(
        {
            node_cls_name: node_cls,
            "ListNode": ListNode,
            "TupleNode": TupleNode,
            "DictNode": DictNode,
            "ConditionalExpressionNode": ConditionalExpressionNode,
            "ConstantNode": ConstantNode,
            # "CompareNode": CompareNode,
            **namespace,
        }
    )

    if assign_fn_key is not None:
        namespace[assign_fn_key] = assign_fn

    return ast.unparse(new_tree)
