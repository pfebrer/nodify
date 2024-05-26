import operator
from typing import Any, Dict, Literal

from .node import Node

__all__ = [
    "ListNode",
    "TupleNode",
    "DictNode",
    "ConditionalExpressionNode",
    "CompareNode",
    "BinaryOperationNode",
    "UnaryOperationNode",
    "GetItemNode",
    "GetAttrNode",
]


class ListNode(Node):
    """Creates a list"""

    @staticmethod
    def function(*items):
        return list(items)

    def get_syntax(self, *items):
        return repr(list(items))


class TupleNode(Node):
    @staticmethod
    def function(*items):
        return tuple(items)

    def get_syntax(self, *items):
        return repr(tuple(items))


class DictNode(Node):
    @staticmethod
    def function(**items):
        return items

    def get_syntax(self, **items):
        return repr(items)


class ConditionalExpressionNode(Node):
    _outdate_due_to_inputs: bool = False

    def get_syntax(self, test: bool, true: Any, false: Any):
        return f"{repr(true)} if {repr(test)} else {repr(false)}"

    def _get_evaluated_inputs(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate the inputs of this node.

        This function overwrites the default implementation in Node, because
        we want to evaluate only the path that we are going to take.

        Parameters
        ----------
        inputs : dict
            The inputs to this node.
        """

        evaluated = {}

        # Get the state of the test input, which determines the path that we are going to take.
        evaluated["test"] = (
            self.evaluate_input_node(inputs["test"])
            if isinstance(inputs["test"], Node)
            else inputs["test"]
        )

        # Evaluate only the path that we are going to take.
        if evaluated["test"]:
            evaluated["true"] = (
                self.evaluate_input_node(inputs["true"])
                if isinstance(inputs["true"], Node)
                else inputs["true"]
            )
            evaluated["false"] = self._prev_evaluated_inputs.get("false")
        else:
            evaluated["false"] = (
                self.evaluate_input_node(inputs["false"])
                if isinstance(inputs["false"], Node)
                else inputs["false"]
            )
            evaluated["true"] = self._prev_evaluated_inputs.get("true")

        return evaluated

    def update_inputs(self, **inputs):
        # This is just a wrapper over the normal update_inputs, which makes
        # sure that the node is only marked as outdated if the input that
        # is being used has changed. Note that here we just create a flag,
        # which is then used in _receive_outdated. (_receive_outdated is
        # called by super().update_inputs())
        current_test = self._prev_evaluated_inputs["test"]

        self._outdate_due_to_inputs = len(inputs) > 0
        if "test" not in inputs:
            if current_test and ("true" not in inputs):
                self._outdate_due_to_inputs = False
            elif not current_test and ("false" not in inputs):
                self._outdate_due_to_inputs = False

        try:
            super().update_inputs(**inputs)
        except:
            self._outdate_due_to_inputs = False
            raise

    def _receive_outdated(self):
        # Relevant inputs have been updated, mark this node as outdated.
        if self._outdate_due_to_inputs:
            return super()._receive_outdated()

        # We avoid marking this node as outdated if the outdated input
        # is not the one being returned.
        for k in self._input_nodes:
            if self._input_nodes[k]._outdated:
                if k == "test":
                    return super()._receive_outdated()
                elif k == "true":
                    if self._prev_evaluated_inputs["test"]:
                        return super()._receive_outdated()
                elif k == "false":
                    if not self._prev_evaluated_inputs["test"]:
                        return super()._receive_outdated()

    @staticmethod
    def function(test: bool, true: Any, false: Any):
        return true if test else false

    def get_diagram_label(self):
        """Returns the label to be used in diagrams when displaying this node."""
        return "if/else"


_CompareOp = Literal["eq", "ne", "gt", "lt", "ge", "le", "is_", "is_not", "contains"]


class CompareNode(Node):
    _op_to_symbol = {
        "eq": "==",
        "ne": "!=",
        "gt": ">",
        "lt": "<",
        "ge": ">=",
        "le": "<=",
        "is_": "is",
        "is_not": "is not",
        "contains": "in",
        None: "compare",
    }

    def get_syntax(self, left: Any, op: _CompareOp, right: Any):
        if not isinstance(op, str):
            raise ValueError(f"Invalid operator: {op}")
        return f"{repr(left)} {self._op_to_symbol[op]} {repr(right)}"

    @staticmethod
    def function(left: Any, op: _CompareOp, right: Any):
        return getattr(operator, op)(left, right)

    def get_diagram_label(self):
        """Returns the label to be used in diagrams when displaying this node."""
        return self._op_to_symbol.get(self._prev_evaluated_inputs.get("op"))


_BynaryOp = Literal[
    "add",
    "sub",
    "mul",
    "truediv",
    "floordiv",
    "mod",
    "pow",
    "lshift",
    "rshift",
    "and",
    "xor",
    "or",
]


class BinaryOperationNode(Node):

    _op_to_symbol = {
        "add": "+",
        "sub": "-",
        "mul": "*",
        "truediv": "/",
        "floordiv": "//",
        "mod": "%",
        "pow": "**",
        "lshift": "<<",
        "rshift": ">>",
        "and": "&",
        "xor": "^",
        "or": "|",
    }

    @staticmethod
    def function(left: Any, op: _BynaryOp, right: Any):
        return getattr(operator, op)(left, right)

    def get_syntax(self, left: Any, op: _BynaryOp, right: Any):
        if not isinstance(op, str):
            raise ValueError(f"Invalid operator: {op}")
        return f"{repr(left)} {self._op_to_symbol[op]} {repr(right)}"


_UnaryOp = Literal["invert", "neg", "pos"]


class UnaryOperationNode(Node):
    _op_to_symbol = {
        "invert": "~",
        "neg": "-",
        "pos": "+",
    }

    @staticmethod
    def function(op: _UnaryOp, operand: Any):
        return getattr(operator, op)(operand)

    def get_syntax(self, op: _UnaryOp, operand: Any):
        if not isinstance(op, str):
            raise ValueError(f"Invalid operator: {op}")
        return f"{self._op_to_symbol[op]}{repr(operand)}"


class GetItemNode(Node):
    @staticmethod
    def function(obj: Any, key: Any):
        return obj[key]

    def get_syntax(self, obj: Any, key: Any):
        return f"{repr(obj)}[{repr(key)}]"


class GetAttrNode(Node):
    @staticmethod
    def function(obj: Any, key: str):
        return getattr(obj, key)

    def get_syntax(self, obj: Any, key: str):
        return f"{repr(obj)}.{key}"
