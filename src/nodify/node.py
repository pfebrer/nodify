from __future__ import annotations

import inspect
import itertools
import logging
from collections import ChainMap
from io import StringIO
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Literal,
    Optional,
    Sequence,
    Tuple,
    Type,
    Union,
)

from .context import NODES_CONTEXT, NodeContext
from .errors import NodeCalcError, NodeError
from .operators import OperatorsMixin
from .registry import REGISTRY

__all__ = ["Node", "Batch", "Constant", "ConstantNode"]


class _TimeFilter(logging.Filter):
    """A helper class to keep the last time a log was emitted.

    This might work in a different way in the future.
    """

    last: float = 0.0

    def filter(self, record):

        import datetime

        try:
            last = self.last
        except AttributeError:
            last = record.relativeCreated

        delta = datetime.datetime.fromtimestamp(
            record.relativeCreated / 1000.0
        ) - datetime.datetime.fromtimestamp(last / 1000.0)

        record.relative = "{0:.2f}".format(
            delta.seconds + delta.microseconds / 1000000.0
        )

        self.last = record.relativeCreated
        return True


class Node(OperatorsMixin):
    """Generic class for nodes.

    A node is a process that runs with some inputs and returns some outputs.
    Inputs can come from other nodes' outputs, and therefore outputs can be
    linked to another node's inputs.

    A node MUST be a pure function. That is, the output should only depend on
    the input. In that way, the output of the node only needs to be calculated
    when the inputs change.
    """

    # Object that will be the reference for output that has not been returned.
    _blank = object()
    # This is the signal to remove a kwarg from the inputs.
    DELETE_KWARG = object()

    # Dictionary that stores the functions that have been converted to this kind of node.
    _known_function_nodes: dict[Callable, Node] = {}

    # Variable containing settings regarding how the node must behave.
    # As an example, the context contains whether a node should be lazily computed or not.
    _cls_context: Dict[str, Any]
    context: NodeContext = NodeContext({}, NODES_CONTEXT)

    # Keys for variadic arguments, if present.
    _args_inputs_key: Optional[str] = None
    _before_args_input_keys: List[str]
    _kwargs_inputs_key: Optional[str] = None

    # Dictionary containing the current inputs (might contain Node objects as values)
    _inputs: Dict[str, Any]
    # Dictionary containing the inputs that were used to calculate the last output.
    # (does not contain Node objects)
    _prev_evaluated_inputs: Dict[str, Any]
    # Variable containing the last method used to handle batches.
    _prev_batch_iter: Literal["zip", "product"] = "zip"

    # Current output value of the node
    _output: Any = _blank

    # Nodes that are connected to this node's inputs
    _input_nodes: Dict[str, Node]
    # Nodes to which the output of this node is connected
    _output_links: List[Node]

    # Number of times the node has been updated.
    _nupdates: int
    # Whether the node's output is currently outdated.
    _outdated: bool
    # Whether the node has errored during the last execution
    # with the current inputs.
    _errored: bool
    # The error that was raised during the last execution
    _error: Optional[NodeError] = None

    # Logs of the node's execution.
    _logger: logging.Logger
    _log_filter: _TimeFilter
    logs: str

    # Contains the raw function of the node.
    function: Callable

    # Method that can be implemented to return the syntax of the node.
    get_syntax: Optional[Callable[[Any], str]] = None

    def __init__(self, *args, **kwargs):
        self.setup(*args, **kwargs)

        lazy_init = self.context["lazy_init"]
        if lazy_init is None:
            lazy_init = self.context["lazy"]

        if not lazy_init:
            self.get()

        if self.context["on_init"] is not None:
            self.context["on_init"](self)

    def __call__(self, *args, **kwargs):
        self.update_inputs(*args, **kwargs)
        return self.get()

    def setup(self, *args, **kwargs):
        """Sets up the node based on its initial inputs."""
        # Parse inputs into arguments.
        bound_params = inspect.signature(self.function).bind_partial(*args, **kwargs)
        # bound_params.apply_defaults()

        self._inputs = bound_params.arguments

        self._input_nodes = {}
        self._output_links = []

        self._update_connections(self._inputs)

        self._prev_evaluated_inputs = self._inputs

        self._output = self._blank
        self._nupdates = 0

        self._outdated = True
        self._errored = False
        self._error = None

        self._logger = logging.getLogger(f"{__name__}.{id(self)!s}")
        self._log_formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s :: %(message)s"
        )
        self._log_filter = _TimeFilter()
        self.logs = ""

        self.context = self.__class__.context.new_child({})

    def __init_subclass__(cls):
        # Assign a context to this node class. This is a chainmap that will
        # resolve keys from its parents, in the order defined by the MRO, in
        # case the context key is not set for this class.
        base_contexts = []
        for base in cls.mro()[1:]:
            if issubclass(base, Node):
                base_contexts.append(base.context.maps[0])

        if not hasattr(cls, "_cls_context") or cls._cls_context is None:
            cls._cls_context = {}

        cls.context = NodeContext(cls._cls_context, *base_contexts, NODES_CONTEXT)

        # Initialize the dictionary that stores the functions that have been converted to this kind of node
        cls._known_function_nodes = {}

        # If the class doesn't contain a "function" attribute, it means that it is just meant
        # to be a base class. If it does contain a "function" attribute, it is an actual usable
        # node class that implements some computation. In that case, we modify the signature of the
        # class to mimic the signature of the function.
        if hasattr(cls, "function"):
            node_func = cls.function

            # Get the signature of the function
            sig = inspect.signature(node_func)

            cls.__doc__ = node_func.__doc__

            # Use the function's signature for the __init__ function, so that the help message
            # is actually useful.
            init_sig = sig
            if "self" not in init_sig.parameters:
                init_sig = sig.replace(
                    parameters=[
                        inspect.Parameter(
                            "self", kind=inspect.Parameter.POSITIONAL_ONLY
                        ),
                        *sig.parameters.values(),
                    ]
                )

            no_self_sig = init_sig.replace(
                parameters=tuple(init_sig.parameters.values())[1:]
            )

            # Find out if there are arguments that are VAR_POSITIONAL (*args) or VAR_KEYWORD (**kwargs)
            # and register it so that they can be handled on init.
            cls._args_inputs_key = None
            cls._before_args_input_keys = []
            cls._kwargs_inputs_key = None
            keys = []
            for key, parameter in no_self_sig.parameters.items():
                if parameter.kind == parameter.VAR_POSITIONAL:
                    cls._args_inputs_key = key
                    cls._before_args_input_keys = keys
                elif cls._args_inputs_key is None:
                    keys.append(key)

                if parameter.kind == parameter.VAR_KEYWORD:
                    cls._kwargs_inputs_key = key

            cls.__signature__ = no_self_sig

            REGISTRY.register(cls)

        return super().__init_subclass__()

    @classmethod
    def from_func(
        cls,
        func: Union[Callable, None] = None,
        context: Union[dict, None] = None,
        module: Optional[str] = None,
    ):
        """Builds a node from a function.

        Parameters
        ----------
        func: function, optional
            The function to be converted to a node.

            If not provided, the return of this method is just a lambda function that expects
            the function. This is useful if you want to use this method as a decorator while
            also providing extra arguments (like the context argument).
        context: dict, optional
            The context to be used as the default for the node class that
            will be created.
        """
        if func is None:
            return lambda func: cls.from_func(func=func, context=context, module=module)

        if isinstance(func, type) and issubclass(func, Node):
            return func

        if isinstance(func, Node):
            node = func

            return CallableNode(func=node)

        if func in cls._known_function_nodes:
            return cls._known_function_nodes[func]

        new_node_cls = type(
            func.__name__,
            (cls,),
            {
                "function": staticmethod(func),
                "_cls_context": context,
                "_from_function": True,
                "__module__": module or func.__module__,
            },
        )

        cls._known_function_nodes[func] = new_node_cls

        return new_node_cls

    def is_output_outdated(self, evaluated_inputs: Dict[str, Any]):
        """Checks if the node needs to be ran"""
        # If there is no output, we clearly need to calculate it
        if self._output is self._blank:
            return True

        # If there are different input keys than there were before,
        # it is also obvious that the inputs are different.
        if set(self._prev_evaluated_inputs) != set(evaluated_inputs):
            return True

        # Check if the batching method has changed, and if so, check if there
        # are batches in the inputs.
        if self._prev_batch_iter != self.context["batch_iter"]:
            # Batching method has changed, are there batches in the inputs?
            any_batch = [False]

            def _is_batch(node):
                if isinstance(node, Batch):
                    any_batch[0] = True

            self.map_inputs(evaluated_inputs, _is_batch)

            if any_batch[0]:
                return True

        # As a last resort, check for inequalities in the inputs.
        def _is_equal(prev, curr):
            if prev is curr:
                return True

            if type(prev) != type(curr):
                return False
            try:
                if prev == curr:
                    return True
                return False
            except:
                return False

        for key in self._prev_evaluated_inputs:
            # Get the previous and current values
            prev = self._prev_evaluated_inputs[key]
            curr = evaluated_inputs[key]

            if not _is_equal(prev, curr):
                return True

        return False

    def map_inputs(
        self,
        inputs: Dict[str, Any],
        func: Callable,
        only_nodes: bool = False,
        exclude: Sequence[str] = (),
    ) -> Dict[str, Any]:
        """Maps all inputs of the node applying a given function.

        It considers the args and kwargs keys.

        Parameters
        ----------
        inputs : Dict[str, Any]
            The inputs of the node.
        func : Callable
            The function to apply to each value.
        only_nodes : bool, optional
            Whether to apply the function only to nodes, by default False.
        exclude : Sequence[str], optional
            The keys to exclude from the mapping. This means that these keys are returned
            as they are.
        """
        # Initialize the output dictionary
        mapped = {}

        # Loop through all items
        for key, input_val in inputs.items():
            if key in exclude:
                mapped[key] = input_val
                continue

            # For the special args_inputs key (if any), we need to loop through all the items
            if key == self._args_inputs_key:
                input_val = tuple(
                    func(val) if not only_nodes or isinstance(val, Node) else val
                    for val in input_val
                )
            elif key == self._kwargs_inputs_key:
                input_val = {
                    k: func(val) if not only_nodes or isinstance(val, Node) else val
                    for k, val in input_val.items()
                }
            else:
                # This is not a special key
                if not only_nodes or isinstance(input_val, Node):
                    input_val = func(input_val)

            mapped[key] = input_val

        return mapped

    def _sanitize_inputs(
        self, inputs: Dict[str, Any]
    ) -> Tuple[Tuple[Any, ...], Dict[str, Any]]:
        """Converts a dictionary that may contain args and kwargs keys to a tuple of args and a dictionary of kwargs.

        Parameters
        ----------
        inputs : Dict[str, Any]
            The dictionary containing the inputs.
        """
        kwargs = inputs.copy()
        args = ()
        if self._args_inputs_key is not None:
            args = []
            # Add arguments that come before the *args key
            for k in self._before_args_input_keys:
                if k in kwargs:
                    args.append(kwargs.pop(k))
            # Then add the variadic positional arguments
            args.extend(kwargs.pop(self._args_inputs_key, ()))
            args = tuple(args)
        if self._kwargs_inputs_key is not None:
            kwargs_inputs = kwargs.pop(self._kwargs_inputs_key, {})
            kwargs.update(kwargs_inputs)

        return args, kwargs

    @staticmethod
    def evaluate_input_node(node: Node):
        return node.get() if not isinstance(node, Batch) else node

    def _get_evaluated_inputs(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluates all inputs.

        This function is ONLY called by the get method.

        The default implementation just goes over the inputs and, if they are nodes,
        makes them compute their output. But some nodes might need more complex things,
        like only evaluating some inputs depending on the value of other inputs.

        Parameters
        ----------
        inputs : Dict[str, Any]
            The input dictionary, possibly containing nodes to evaluate.
        """
        # Map all inputs to their values. That is, if they are nodes, call the get
        # method on them so that we get the updated output. This recursively evaluates nodes.
        return self.map_inputs(
            inputs=inputs,
            func=self.evaluate_input_node,
            only_nodes=True,
        )

    def _handle_batch(
        self,
        evaluated_inputs: Dict[str, Any],
        is_batch_input: Dict[str, Any],
    ) -> Batch:
        """Gathers inputs that are batches and calls _get_batch to apply the function to them.

        Parameters
        ----------
        evaluated_inputs:
            The inputs of the node, already evaluated.
        is_batch_input:
            A dictionary indicating, for each input, whether they are a batch or not.
        """
        batch_inputs = {
            k: evaluated_inputs[k] for k, v in is_batch_input.items() if v is True
        }
        args_batch_inputs = {}
        if (
            self._args_inputs_key is not None
            and self._args_inputs_key in evaluated_inputs
        ):
            args_batch_inputs = {
                i: evaluated_inputs[self._args_inputs_key][i]
                for i, v in enumerate(is_batch_input[self._args_inputs_key])
                if v is True
            }
        kwargs_batch_inputs = {}
        if (
            self._kwargs_inputs_key is not None
            and self._kwargs_inputs_key in evaluated_inputs
        ):
            for k, v in evaluated_inputs[self._kwargs_inputs_key].items():
                if is_batch_input[self._kwargs_inputs_key][k]:
                    kwargs_batch_inputs[k] = v

        return self._get_batch(
            evaluated_inputs, batch_inputs, args_batch_inputs, kwargs_batch_inputs
        )

    def _get_batch(
        self,
        evaluated_inputs: Dict[str, Any],
        batch_inputs: Dict[str, Batch],
        args_batch_inputs: Dict[int, Batch],
        kwargs_batch_inputs: Dict[str, Batch],
    ) -> Batch:
        """Handles the case in which the inputs contain batches.

        Parameters
        ----------
        evaluated_inputs:
            The inputs of the node, already evaluated.
        batch_inputs:
            The inputs that are batches.
        args_batch_inputs:
            The inputs passed to the variadic positional arguments that are batches.
        kwargs_batch_inputs:
            The inputs passed to the variadic keyword arguments that are batches.
        """

        keys = [*batch_inputs.keys(), *kwargs_batch_inputs.keys()]
        iters = [*batch_inputs.values(), *kwargs_batch_inputs.values()]

        args_keys = list(args_batch_inputs.keys())
        args_iters = [v for v in args_batch_inputs.values()]

        if self.context["batch_iter"] == "zip":
            vals_iterator = zip(*iters, *args_iters)
        elif self.context["batch_iter"] == "product":
            vals_iterator = itertools.product(*iters, *args_iters)
        else:
            raise ValueError(f"Invalid batch_iter mode: {self.context['batch_iter']}")

        outputs = []
        for vals in vals_iterator:
            inps = {**evaluated_inputs, **dict(zip(keys, vals[: len(iters)]))}
            if self._args_inputs_key is not None and len(args_batch_inputs) > 0:
                args_vals = vals[len(iters) :]
                inps[self._args_inputs_key] = tuple(
                    args_vals[args_keys.index(i)] if i in args_keys else val
                    for i, val in enumerate(evaluated_inputs[self._args_inputs_key])
                )

            if self._kwargs_inputs_key is not None and len(kwargs_batch_inputs) > 0:
                for k in kwargs_batch_inputs:
                    inps[self._kwargs_inputs_key][k] = inps.pop(k)

            args, kwargs = self._sanitize_inputs(inps)
            outputs.append(self.function(*args, **kwargs))

        return Batch(*outputs)

    def get(self):
        """Returns the output of the node, possibly running the computation.

        The computation of the node is only performed if the output is outdated,
        otherwise this function just returns the stored output.
        """
        self._logger.setLevel(getattr(logging, self.context["log_level"].upper()))

        logs = logging.StreamHandler(StringIO())
        logs.addFilter(self._log_filter)
        self._logger.addHandler(logs)

        logs.setFormatter(self._log_formatter)

        self._logger.debug("Getting output from node...")
        self._logger.debug(f"Raw inputs: {self._inputs}")

        evaluated_inputs = self._get_evaluated_inputs(self._inputs)

        self._logger.debug(f"Evaluated inputs: {evaluated_inputs}")

        if self._outdated or self.is_output_outdated(evaluated_inputs):
            try:
                # Check if there are batches
                any_batch = [False]

                def _is_batch(node):
                    result = isinstance(node, Batch)
                    if result:
                        any_batch[0] = True
                    return result

                is_batch_input = self.map_inputs(evaluated_inputs, _is_batch)

                self._prev_batch_iter = self.context["batch_iter"]
                # If there are batches, gather them and return a batch object
                if any_batch[0]:
                    output = self._handle_batch(evaluated_inputs, is_batch_input)
                else:
                    args, kwargs = self._sanitize_inputs(evaluated_inputs)
                    output = self.function(*args, **kwargs)

                self._output = output

                self._logger.info(f"Evaluated because inputs changed.")
            except Exception as e:
                self._logger.exception(e)
                self.logs += logs.stream.getvalue()
                logs.close()
                self._errored = True
                self._error = NodeCalcError(self, e, evaluated_inputs)

                if self.context["raise_custom_errors"]:
                    raise self._error
                else:
                    raise e

            self._nupdates += 1
            self._prev_evaluated_inputs = evaluated_inputs
            self._outdated = False
            self._errored = False
            self._error = None
        else:
            self._logger.info(f"No need to evaluate")

        self._logger.debug(f"Output: {self._output}.")

        self.logs += logs.stream.getvalue()
        logs.close()

        return self._output

    def get_tree(self):
        tree = {
            "node": self,
        }

        tree["inputs"] = self.map_inputs(
            self._inputs,
            only_nodes=True,
            func=lambda node: node.get_tree(),
        )

        return tree

    @property
    def default_inputs(self):
        params = inspect.signature(self.function).bind_partial()
        params.apply_defaults()
        return params.arguments

    @property
    def inputs(self):
        return ChainMap(self._inputs, self.default_inputs)

    def get_input(self, key: str):
        input_val = self.inputs[key]

        return input_val

    def recursive_update_inputs(
        self, cls: Optional[Union[Type, Tuple[Type, ...]]] = None, **inputs
    ):
        """Updates the inputs of the node recursively.

        This method updates the inputs of get node and all its children.

        Parameters
        ----------
        cls : Optional[Union[Type, Tuple[Type, ...]]], optional
            Only update nodes of this class. If None, update all nodes.
        inputs : Dict[str, Any]
            The inputs to update.
        """
        from .utils import traverse_tree_backward

        def _update(node):
            if cls is None or isinstance(self, cls):
                node.update_inputs(**inputs)

                update_inputs = {}
                # Update the inputs of the node
                for k in self.inputs:
                    if k in inputs:
                        update_inputs[k] = inputs[k]

                self.update_inputs(**update_inputs)

        traverse_tree_backward([self], _update)

    def update_inputs(self, **inputs):
        """Updates the inputs of the node.

        Note that you can not pass positional arguments to this method.
        The positional arguments must be passed also as kwargs.

        This is because there would not be a well defined way to update the
        variadic positional arguments.

        E.g. if the function signature is (a: int, *args), there is no way
        to pass *args without passing a value for a.

        This means that one must also pass the *args also as a key:
        ``update_inputs(args=(2, 3))``. Beware that functions not necessarily
        name their variadic arguments ``args``. If the function signature is
        ``(a: int, *arguments)`` then the key that you need to use is `arguments`.

        Similarly, the **kwargs can be passed either as a dictionary in the key ``kwargs``
        (or whatever the name of the variadic keyword arguments is). This indicates that
        the whole kwargs is to be replaced by the new value. Alternatively, you can pass
        the kwargs as separate key-value arguments, which means that you want to update the
        kwargs dictionary, but keep the old values. In this second option, you can indicate
        that a key should be removed by passing ``Node.DELETE_KWARG`` as the value.

        Parameters
        ----------
        **inputs :
            The inputs to update.
        """
        # If no new inputs were provided, there's nothing to do
        if not inputs:
            return

        # Pop the args key (if any) so that we can parse the inputs without errors.
        args = None
        if self._args_inputs_key:
            args = inputs.pop(self._args_inputs_key, None)
        # Pop also the kwargs key (if any)
        explicit_kwargs = None
        if self._kwargs_inputs_key:
            explicit_kwargs = inputs.pop(self._kwargs_inputs_key, None)

        # Parse the inputs. We do this to separate the kwargs from the rest of the inputs.
        bound = inspect.signature(self.function).bind_partial(**inputs)
        inputs = bound.arguments

        # Now that we have parsed the inputs, put back the args key (if any).
        if args is not None:
            inputs[self._args_inputs_key] = args

        if explicit_kwargs is not None:
            # If a kwargs dictionary has been passed, this means that the user wants to replace
            # the whole kwargs dictionary. So, we just update the inputs with the new kwargs.
            inputs[self._kwargs_inputs_key] = explicit_kwargs
        elif self._kwargs_inputs_key is not None:
            # Otherwise, update the old kwargs with the new separate arguments that have been passed.
            # Here we give the option to delete individual kwargs by passing the DELETE_KWARG indicator.
            new_kwargs = inputs.get(self._kwargs_inputs_key, {})
            if len(new_kwargs) > 0:
                kwargs = self._inputs.get(self._kwargs_inputs_key, {}).copy()
                kwargs.update(new_kwargs)

                for k, v in new_kwargs.items():
                    if v is self.DELETE_KWARG:
                        kwargs.pop(k, None)

                inputs[self._kwargs_inputs_key] = kwargs

        # Update the inputs
        self._inputs.update(inputs)

        # Now, update all connections between nodes
        self._update_connections(self._inputs)

        # Mark the node as outdated
        self._receive_outdated()

        return self

    @property
    def last_log(self) -> float:
        """Last time the logs of this node were updated"""
        return self._log_filter.last

    def __array_ufunc__(self, ufunc, method, *inputs, **kwargs):
        if "out" in kwargs:
            raise NotImplementedError(
                f"{self.__class__.__name__} does not allow the 'out' argument in ufuncs."
            )
        inputs = {f"input_{i}": input for i, input in enumerate(inputs)}
        return UfuncNode(ufunc=ufunc, method=method, input_kwargs=kwargs, **inputs)

    def __getitem__(self, key):
        from .syntax_nodes import GetItemNode

        return GetItemNode(obj=self, key=key)

    def __getattr__(self, key):
        if key.startswith("_"):
            raise super().__getattr__(key)
        from .syntax_nodes import GetAttrNode

        return GetAttrNode(obj=self, key=key)

    def _update_connections(self, inputs):
        def _update(key, value):
            # Get the old connected node (if any) and tell them
            # that we are no longer using their input
            old_connection = self._input_nodes.get(key, None)
            if old_connection is value:
                # The input value has not been updated, no need to update any connections
                return

            if old_connection is not None:
                self._input_nodes.pop(key)
                old_connection._receive_output_unlink(self)

            # If the new input is a node, create the connection
            if isinstance(value, Node):
                self._input_nodes[key] = value
                value._receive_output_link(self)

        previous_connections = list(self._input_nodes)

        for key, input in inputs.items():
            if key == self._args_inputs_key:
                # Loop through all the current *args to update connections
                input_len = 0
                if not isinstance(input, DummyInputValue):
                    input_len = len(input)
                    for i, item in enumerate(input):
                        _update(f"{key}[{i}]", item)
                # For indices higher than the current *args length, remove the connections.
                # (this is because the previous *args might have been longer)
                for k in previous_connections:
                    if k.startswith(f"{key}["):
                        if int(k[len(key) + 1 : -1]) > input_len:
                            _update(k, None)
            elif key == self._kwargs_inputs_key:
                current_kwargs = []
                # Loop through all the current **kwargs to update connections
                if not isinstance(input, DummyInputValue):
                    for k, item in input.items():
                        connection_key = f"{key}[{k}]"
                        current_kwargs.append(connection_key)
                        _update(connection_key, item)
                # Remove connections for those keys that are no longer in the kwargs
                for k in previous_connections:
                    if k.startswith(f"{key}[") and k not in current_kwargs:
                        _update(k, None)
            else:
                # This is the normal case, where the key is not either the *args or the **kwargs key.
                _update(key, input)

    def _receive_output_link(self, node):
        for linked_node in self._output_links:
            if linked_node is node:
                break
        else:
            self._output_links.append(node)

    def _receive_output_unlink(self, node):
        for i, linked_node in enumerate(self._output_links):
            if linked_node is node:
                del self._output_links[i]
                break

    def _inform_outdated(self):
        """Informs nodes that are linked to our output that they are outdated.

        This is either because we are outdated, or because an input update has
        triggered an automatic recalculation.
        """
        for linked_node in self._output_links:
            linked_node._receive_outdated()

    def _receive_outdated(self):
        # Mark the node as outdated
        self._outdated = True
        self._errored = False
        # If automatic recalculation is turned on, recalculate output
        self._maybe_autoupdate()
        # Inform to the nodes that use our input that they are outdated
        # now.
        self._inform_outdated()

    def _maybe_autoupdate(self):
        """Makes this node recalculate its output if automatic recalculation is turned on"""
        if not self.context["lazy"]:
            self.get()

    def get_diagram_label(self):
        """Returns the label to be used in diagrams when displaying this node."""
        return None


class Batch(Node):
    """Stores a batch of values.

    This class signals to nodes that they should run their computation
    for each value in the batch.
    """

    @staticmethod
    def function(*items):
        return items

    def __iter__(self):
        return iter(self.get())


class DummyInputValue(Node):
    """A dummy node that can be used as a placeholder for input values."""

    @property
    def input_key(self):
        return self._inputs["input_key"]

    @property
    def value(self):
        return self._inputs.get("value", Node._blank)

    @staticmethod
    def function(input_key: str, value: Any = Node._blank):
        return value


class FuncNode(Node):
    @staticmethod
    def function(*args, func: Callable, **kwargs):
        return func(*args, **kwargs)


class CallableNode(FuncNode):
    def __call__(self, *args, **kwargs):
        self.update_inputs(*args, **kwargs)
        return self


class UfuncNode(Node):
    """Node that wraps a numpy ufunc."""

    def __call__(self, *args, **kwargs):
        self.recursive_update_inputs(*args, **kwargs)
        return self.get()

    @staticmethod
    def function(ufunc, method: str, input_kwargs: Dict[str, Any], **kwargs):
        # We need to
        inputs = []
        i = 0
        while True:
            key = f"input_{i}"
            if key not in kwargs:
                break
            inputs.append(kwargs.pop(key))
            i += 1
        return getattr(ufunc, method)(*inputs, **input_kwargs)


class Constant(Node):
    """Node that just returns its input value."""

    @staticmethod
    def function(value: Any):
        return value


ConstantNode = Constant
