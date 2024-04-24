class NodeError(BaseException):
    def __init__(self, node, error):
        self._node = node
        self._error = error

    def __str__(self):
        return f"There was an error with node {self._node}. {self._error}"


class NodeCalcError(NodeError):
    def __init__(self, node, error, inputs):
        super().__init__(node, error)
        self._inputs = inputs

    def __str__(self):
        return f"Couldn't generate an output for {self._node} with the current inputs."


class NodeInputError(NodeError):
    def __init__(self, node, error, inputs):
        super().__init__(node, error)
        self._inputs = inputs

    def __str__(self):
        # Should make this more specific
        return f"Some input is not right in {self._node} and could not be parsed"
