"""Mixin class to take care of all operators"""

__all__ = ["OperatorsMixin"]


def inplace_operator():
    """Decorator for inplace operators."""

    def wrapper(self, *args, **kwargs):
        raise RuntimeError("Inplace operations for nodes are not supported.")

    return wrapper


def _comparison_method(name):
    """Implement a comparison method with a function, e.g., __eq__."""

    def func(self, other):
        from .syntax_nodes import CompareNode

        return CompareNode(left=self, right=other, op=name)

    func.__name__ = f"__{name}__"
    return func


def _binary_operation(name):
    """Implement a binary operation method with a function, e.g., __add__."""

    def func(self, other):
        from .syntax_nodes import BinaryOperationNode

        return BinaryOperationNode(left=self, op=name, right=other)

    func.__name__ = f"__{name}__"

    def reflected_func(self, other):
        from .syntax_nodes import BinaryOperationNode

        return BinaryOperationNode(left=other, op=name, right=self)

    reflected_func.__name__ = f"__r{name}__"

    return func, reflected_func


def _unary_method(name):
    """Implement a unary operation method with a function, e.g., __neg__."""

    def func(self):
        from .syntax_nodes import UnaryOperationNode

        return UnaryOperationNode(op=name, operand=self)

    func.__name__ = f"__{name}__"
    return func


class OperatorsMixin:
    """"""

    __slots__ = ()

    # Inplace operators are not allowed
    __iadd__ = __isub__ = __imul__ = __imatmul__ = __itruediv__ = __ifloordiv__ = (
        __imod__
    ) = __ipow__ = __ilshift__ = __irshift__ = __iand__ = __ixor__ = __ior__ = (
        inplace_operator()
    )

    # Comparison methods return a CompareNode
    __lt__ = _comparison_method("lt")
    __le__ = _comparison_method("le")
    __eq__ = _comparison_method("eq")
    __ne__ = _comparison_method("ne")
    __gt__ = _comparison_method("gt")
    __ge__ = _comparison_method("ge")

    # numeric methods
    __add__, __radd__ = _binary_operation("add")
    __sub__, __rsub__ = _binary_operation("sub")
    __mul__, __rmul__ = _binary_operation("mul")
    __matmul__, __rmatmul__ = _binary_operation("matmul")
    __truediv__, __rtruediv__ = _binary_operation("truediv")
    __floordiv__, __rfloordiv__ = _binary_operation("floordiv")
    __mod__, __rmod__ = _binary_operation("mod")
    __divmod__, __rdivmod__ = _binary_operation("divmod")
    __pow__, __rpow__ = _binary_operation("pow")
    __lshift__, __rlshift__ = _binary_operation("lshift")
    __rshift__, __rrshift__ = _binary_operation("rshift")
    __and__, __rand__ = _binary_operation("and")
    __xor__, __rxor__ = _binary_operation("xor")
    __or__, __ror__ = _binary_operation("or")

    # unary methods
    __neg__ = _unary_method("neg")
    __pos__ = _unary_method("pos")
    __abs__ = _unary_method("abs")
    __invert__ = _unary_method("invert")
