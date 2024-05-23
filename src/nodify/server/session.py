import importlib
import inspect
import logging
import time
from functools import wraps
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Type, Union

from nodify import ConstantNode, Node, Workflow, nodify_module
from nodify.conversions import node_to_python_script, python_script_to_nodes
from nodify.utils import (
    traverse_tree_backward,
    traverse_tree_forward,
    visit_all_connected,
)

from .json import CustomJSONEncoder, get_inputs_mode
from .registry import SERVER_REGISTRY, SessionRegistry
from .sync import Synchronized

last_registration = time.time()
registry_callbacks = []


def updates(key: str):
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            ret = func(self, *args, **kwargs)
            self.last_update[key] = time.time()
            return ret

        return wrapper

    return decorator


FILE_PLOT_REGISTRY = {}


def register_file_plot_handler(
    name: str, options_finder: Callable[[str], List[str]], handler: Callable
):
    FILE_PLOT_REGISTRY[name] = (options_finder, handler)


class Session:
    """Base session class that implements the functionality of a session in the GUI"""

    # Object that dispatches session methods and automatically updates the GUI
    synced: Synchronized

    # Keeping track of last updates
    last_update: Dict[str, float] = {
        "nodes": 0.0,
        "flows": 0.0,
        "node_classes": 0.0,
    }

    # Logging parameters
    logger: logging.Logger
    log_level: str = "INFO"
    logs: StringIO

    # Dictionary that stores all nodes that the session knows about, being the key the node ID
    nodes: Dict[int, Dict] = {}
    # Dictionary that maps node names to their IDs so that nodes can be accessed
    # in a more human-friendly way.
    _name_to_id: Dict[str, int] = {}

    # Store flows
    flows: Dict = {}

    # Modules that are allowed to be nodified when loading a session
    allowed_nodifiable: List[str] = []

    def __init__(self, *args, **kwargs):

        # Initialize the synchronized object
        self.synced = Synchronized(self)

        # Initialize node management
        self.nodes = {}
        self._name_to_id = {}

        # Initialize flows
        self.flows = {}

        # Initialize last update times
        self.last_update = {k: time.time() for k in self.last_update}
        self.registry = SessionRegistry(self)
        SERVER_REGISTRY.subscribe(self.registry)

        # Initialize the logging stream
        self.logs = StringIO()
        # And the logger
        self.logger = logging.getLogger(str(id(self)))
        self.logger.setLevel(getattr(logging, self.log_level.upper()))

        # Add the handler so that the logs are written to the stream
        self._log_handler = logging.StreamHandler(self.logs)
        self._log_handler.setFormatter(
            logging.Formatter(fmt="%(asctime)s | %(levelname)-8s :: %(message)s")
        )

        self.logger.addHandler(self._log_handler)

        self.settings = {
            "file_storage_dir": ".nodify_uploaded_files",
            "keep_uploaded": False,
        }

        self.allowed_nodifiable = []

    def supports_file_plotting(self):
        return len(FILE_PLOT_REGISTRY) > 0

    def get_file_plot_options(self, file_name: str) -> List[str]:
        options = []
        for name, (options_finder, _) in FILE_PLOT_REGISTRY.items():
            options.extend(options_finder(file_name))
        return options

    def plot_uploaded_file(
        self,
        name: str,
        file_bytes: Optional[BytesIO] = None,
        method: Optional[str] = None,
        node_name: Optional[str] = None,
        additional_files: Dict[str, BytesIO] = {},
    ) -> int:
        if file_bytes is None:
            # We will assume that the file is already written.
            file_name = Path(name)
            keep = True
            dirname = file_name.parent
        else:
            file_name, dirname, keep = self.write_file(file_bytes, name)

        additional_files_info = []
        for n, file in additional_files.items():
            additional_files_info.append(self.write_file(file, n))

        for name, (options_finder, handler) in FILE_PLOT_REGISTRY.items():
            if method in options_finder(file_name):
                plot = handler(file_name, method)
                break

        self.add_node(plot, node_name or name)

        if not keep:
            self._remove_temp_file(file_name, dirname)

        for file_name, dirname, keep in additional_files_info:
            if not keep:
                self._remove_temp_file(file_name, dirname)

        return id(plot)

    # Functions to receive uploaded files:
    def write_file(self, file_bytes, name):
        dirname = Path(self.settings["file_storage_dir"])
        if not dirname.exists():
            dirname.mkdir()

        file_name = dirname / name
        with open(file_name, "wb") as fh:
            fh.write(file_bytes)

        keep = self.settings["keep_uploaded"]

        return file_name, dirname, keep

    def _remove_temp_file(self, file_name, dirname):
        # Remove the file
        file_name.unlink()
        # If the directory is empty, remove it as well
        try:
            dirname.rmdir()
        except:
            pass

    @updates("nodes")
    def add_node(self, obj: Any, name: Union[str, None] = None):
        """Adds a node to the session.

        Parameters
        ----------
        obj : Any
            The object to add to the session. If it is not a node, a new CONSTANT node
            will be created with the object as its value.
        name : Union[str, None], optional
            The name of the node. If None, the name will be the name of the node class.
            If the name is already taken, a number will be appended to it.
        """
        # If the object is not a node, create a new constant node with the object as its value.
        if not isinstance(obj, Node):
            obj = ConstantNode(obj)

        # If the name is None, use the name of the class
        if name is None:
            name = obj.__class__.__name__

        # Make sure the name is unique
        original_name = name
        i = 1
        while name in self._name_to_id:
            name = f"{original_name}_{i}"
            i += 1

        # Get the ID of the object and use it as the key to store the node.
        obj_id = id(obj)
        self.nodes[obj_id] = {
            "name": name,
            "node": obj,
        }

        # Keep track of the name to ID mapping
        self._name_to_id[name] = obj_id

    def get_nodes(self) -> Dict[int, Node]:
        return self.nodes

    def get_node(self, key: Union[str, int]) -> Node:
        """Returns the node that corresponds to the given key.

        Parameters
        ----------
        key : Union[str, int]
            The key of the node. If it is a string, it will be interpreted as the name of the node.
            If it is an integer, it will be interpreted as the ID of the node.

        Returns
        -------
        Node
            The node object that was requested.
        """

        if isinstance(key, str):
            key = self._name_to_id[key]

        return self.nodes[key]["node"]

    def get_node_logs(self, key: Union[str, int]) -> str:
        """Returns the logs of the node that corresponds to the given key.

        Parameters
        ----------
        key : Union[str, int]
            The key of the node. If it is a string, it will be interpreted as the name of the node.
            If it is an integer, it will be interpreted as the ID of the node.

        Returns
        -------
        str
            The logs of the node.
        """
        node = self.get_node(key)
        return node.logs

    @updates("nodes")
    def remove_node(self, key: Union[str, int]):
        """Removes the node that corresponds to the given key.

        Parameters
        ----------
        key : Union[str, int]
            The key of the node. If it is a string, it will be interpreted as the name of the node.
            If it is an integer, it will be interpreted as the ID of the node.

        See Also
        --------
        get_node
        """
        node = self.get_node(key)
        name = self.nodes[id(node)]["name"]
        if len(node._output_links) > 0:
            if any(id(linked_node) in self.nodes for linked_node in node._output_links):
                raise ValueError(
                    "Cannot remove a node that has output links to other registered nodes."
                )

        obj_id = self._name_to_id.pop(name, None)
        self.nodes.pop(obj_id, None)

    def init_node(
        self, cls: int, kwargs={}, input_modes={}, name: Union[str, None] = None
    ) -> Node:
        """Initializes a new node.

        Parameters
        ----------
        cls : int
            The ID of the node class.
        kwargs : dict, optional
            All the inputs that should be used to initialize the node.
        input_modes : dict, optional
            For each input key in kwargs, a mode specifying how to interpret the value.
            If the mode is "NODE", the value will be interpreted as the ID of a node, and therefore
            will be replaced by the corresponding node object.
        name : Union[str, None], optional
            The name of the node. If None, the name will be automatically determined by ``add_node``.

        """
        node_class = SERVER_REGISTRY.classes_dict[cls]

        args_key = node_class._args_inputs_key
        kwargs_key = node_class._kwargs_inputs_key

        # Remove values for variadic arguments if they are None
        # (they should be either a list for *args or a dict for **kwargs)
        for k in (args_key, kwargs_key):
            if kwargs.get(k) is None:
                kwargs.pop(k, None)

        # Parse values into nodes if the input mode in the GUI was "node"
        # If it is a variadic argument, loop through inputs.
        for k, v in input_modes.items():
            if v == "NODE" and k in kwargs:
                if k == args_key:
                    kwargs[k] = [self.get_node(node_id) for node_id in kwargs[k]]
                elif k == kwargs_key:
                    for kwarg_key in kwargs[k]:
                        kwargs[kwarg_key] = self.get_node(kwargs[k][kwarg_key])
                    kwargs.pop(k)
                else:
                    kwargs[k] = self.get_node(kwargs[k])

        args = []
        # If *args are passed, then we need to get all the arguments that
        # go before them and place them at their right position.
        if args_key is not None and args_key in kwargs:
            params = inspect.signature(node_class.function).parameters
            for k, param in params.items():
                if k == args_key:
                    args.extend(kwargs.pop(k))
                    break
                else:
                    args.append(kwargs.pop(k))

        # Managing **kwargs is easier, we just expand the value of the kwargs field.
        if kwargs_key is not None and kwargs_key in kwargs:
            kwargs.update(kwargs.pop(kwargs_key))

        # Initialize the node.
        new_node = node_class(*args, **kwargs)

        self.add_node(new_node, name)

        return new_node

    @updates("nodes")
    def update_node_inputs(
        self,
        key: Union[str, int],
        kwargs: Dict[str, Any] = {},
        input_modes: Dict[str, str] = {},
    ):
        """Updates the inputs of a stored node.

        Parameters
        ----------
        key : Union[str, int]
            The key of the node. If it is a string, it will be interpreted as the name of the node.
            If it is an integer, it will be interpreted as the ID of the node.
        kwargs : Dict[str, Any], optional
            The new values for the inputs of the node.
        input_modes : Dict[str, Any], optional
            For each input key in kwargs, a mode specifying how to interpret the value.
            If the mode is "NODE", the value will be interpreted as the ID of a node, and therefore
            will be replaced by the corresponding node object.

        See Also
        --------
        get_node
        """

        node = self.get_node(key)

        args_key = node._args_inputs_key
        kwargs_key = node._kwargs_inputs_key

        # Remove values for variadic arguments if they are None
        # (they should be either a list for *args or a dict for **kwargs)
        for k in (args_key, kwargs_key):
            if kwargs.get(k) is None:
                kwargs.pop(k, None)

        # Parse values into nodes if the input mode in the GUI was "node"
        # If it is a variadic argument, loop through inputs.
        for k, v in input_modes.items():
            if v == "NODE" and k in kwargs:
                if k == args_key:
                    kwargs[k] = [self.get_node(node_id) for node_id in kwargs[k]]
                elif k == kwargs_key:
                    kwargs[k] = {key: self.get_node(v) for key, v in kwargs[k].items()}
                else:
                    kwargs[k] = self.get_node(kwargs[k])

        node.update_inputs(**kwargs)

    @updates("nodes")
    def reset_node_inputs(self, key: Union[str, int], input_keys: Optional[List[str]]):
        """Resets the inputs of a stored node.

        Parameters
        ----------
        key :
            The key of the node. If it is a string, it will be interpreted as the name of the node.
            If it is an integer, it will be interpreted as the ID of the node.
        input_keys :
            The keys of the inputs that should be reset. If None, all inputs will be reset.
        """

        node = self.get_node(key)

        defaults = node.default_inputs

        if input_keys is not None:
            defaults = {k: defaults.get(k, Node._blank) for k in input_keys}

        return node.update_inputs(**defaults)

    def duplicate_node(
        self, key: Union[str, int], name: Union[str, None] = None
    ) -> Node:
        """Duplicates the node that corresponds to the given key.

        Parameters
        ----------
        key : Union[str, int]
            The key of the node. If it is a string, it will be interpreted as the name of the node.
            If it is an integer, it will be interpreted as the ID of the node.
        name : str, optional
            The name of the new node. If None, the name will be copied from the old node.

        See Also
        --------
        get_node
        """
        node = self.get_node(key)

        if name is None:
            nodeid = self.get_nodeid(key)
            name = self.nodes[nodeid]["name"]

        new_node = node.__class__(**dict(node._inputs))

        self.add_node(new_node, name)

        return new_node

    def node_input_to_node(
        self, key: Union[str, int], input_key: str, name: Union[str, None] = None
    ) -> Node:
        """Converts an input to a node, and links it.

        A ConstantNode will be created with the value of the input, and it will be linked to the same
        input key.

        This results in no changes on the computation, but it creates a new node that can be linked
        to other nodes.

        Parameters
        ----------
        key : Union[str, int]
            The key of the node whose input we want to convert.
            If it is a string, it will be interpreted as the name of the node.
            If it is an integer, it will be interpreted as the ID of the node.
        input_key : str
            Key of the input to be converted.
        name : str, optional
            The name of the new node. If None, the name will be copied from the old node.
        """
        node = self.get_node(key)

        if input_key in node.inputs:
            input_value = node.inputs[input_key]
        elif input_key in node.__signature__.parameters:
            input_value = Node._blank
        else:
            raise ValueError(f"Input key '{input_key}' not found in node '{node}'.")

        if isinstance(input_value, Node):
            return input_value
        else:
            new_node = ConstantNode(input_value)
            self.add_node(new_node, name or input_key)

            node.update_inputs(**{input_key: new_node})

        return new_node

    def get_nodeid(self, key: Union[str, int]) -> int:
        """Given either the name or the ID of a node, returns the ID of the node.

        Parameters
        ----------
        key : Union[str, int]
            The key of the node. If it is a string, it will be interpreted as the name of the node.
            If it is an integer, it will be interpreted as the ID of the node.
        """
        if isinstance(key, str):
            key = self._name_to_id[key]

        return key

    @updates("nodes")
    def rename_node(self, key: Union[str, int], name: str):
        """Renames the node that corresponds to the given key.

        Parameters
        ----------
        key : Union[str, int]
            The key of the node. If it is a string, it will be interpreted as the name of the node.
            If it is an integer, it will be interpreted as the ID of the node.
        name : str, optional
            The new name for the node.

        See Also
        --------
        get_node
        """
        nodeid = self.get_nodeid(key)

        old_name = self.nodes[nodeid]["name"]

        del self._name_to_id[old_name]
        self._name_to_id[name] = nodeid

        self.nodes[nodeid]["name"] = name

    def node_to_workflow(self, key: Union[str, int]) -> Workflow:
        """Considering a certain node as a workflow output, creates a workflow.

        It does so by recursively traversing nodes through their inputs until it reaches
        the leaves of the tree. The leaves are then considered as the inputs of the new workflow.

        Parameters
        ----------
        key : Union[str, int]
            The key of the node. If it is a string, it will be interpreted as the name of the node.
            If it is an integer, it will be interpreted as the ID of the node.

        See Also
        --------
        get_node
        """
        node = self.get_node(key)

        # names_map = {node_id: name for name, node_id in self._name_to_id.items()}

        return Workflow.from_node_tree(node)  # , names_map=names_map)

    def node_to_python_script(
        self,
        key: Union[str, int],
        include_defaults: bool = False,
        as_function: bool = False,
        function_name: Optional[str] = "function",
    ) -> str:
        """Converts a node and all to a Python script.

        Parameters
        ----------
        key : Union[str, int]
            The key of the node. If it is a string, it will be interpreted as the name of the node.
            If it is an integer, it will be interpreted as the ID of the node.

        See Also
        --------
        get_node
        """
        node = self.get_node(key)

        names_map = {k: v["name"] for k, v in self.nodes.items()}

        return node_to_python_script(
            node,
            include_defaults=include_defaults,
            as_function=as_function,
            function_name=function_name,
            names_map=names_map,
        )

    @updates("nodes")
    def compute_node(self, key: Union[str, int]):
        """Computes the node that corresponds to the given key.

        Parameters
        ----------
        key : Union[str, int]
            The key of the node. If it is a string, it will be interpreted as the name of the node.
            If it is an integer, it will be interpreted as the ID of the node.

        See Also
        --------
        get_node
        """
        node = self.get_node(key)

        node.get()

    def get_compatible_following_nodes(
        self, node_key: Union[str, int], return_id: bool = False
    ) -> List[Union[Type[Node], int]]:
        """Returns all nodes that are instances of a certain class.

        Parameters
        ----------


        Returns
        -------
        List[Node]
            A list of all nodes that are instances of the given class.
        """
        node = self.get_node(node_key)

        # Get current node's output.
        if node._output is not Node._blank:
            out_class = node._output.__class__
        # There is no output yet, get the return type annotation.
        elif "return" in node.typehints:
            out_class = node.typehints["return"]
        # There is no return type annotation
        else:
            return []

        nodes = SERVER_REGISTRY.types_registry[out_class]["first_arg"]

        if return_id:
            nodes = [id(node) for node in nodes]

            return nodes

    def get_forward_nodes(
        self, roots: List[Union[str, int]], return_id: bool = False
    ) -> List[Union[Node, int]]:
        """Returns all nodes that are reachable from a certain node going forward.

        Parameters
        ----------
        roots :
            The nodes from which the search should start.

        Returns
        -------
        List[Node]
            A list of all nodes that are reachable from the given nodes.
        """

        if isinstance(roots, (str, int)):
            roots = [roots]

        forw_nodes = []
        roots = [self.get_node(root) for root in roots]
        root_ids = [id(root) for root in roots]

        def _add_node(node):
            node_id = id(node)
            if node_id not in root_ids and node_id in self.nodes:
                if return_id:
                    node = node_id
                forw_nodes.append(node)

        traverse_tree_forward(roots, _add_node)

        return forw_nodes

    def get_backward_nodes(
        self, roots: List[Union[str, int]], return_id: bool = False
    ) -> List[Union[Node, int]]:
        """Returns all nodes that are reachable from a certain node going backward.

        Parameters
        ----------
        roots :
            The nodes from which the search should start.

        Returns
        -------
        List[Node]
            A list of all nodes that are reachable from the given nodes.
        """

        if isinstance(roots, (str, int)):
            roots = [roots]

        back_nodes = []
        roots = [self.get_node(root) for root in roots]
        root_ids = [id(root) for root in roots]

        def _add_node(node):
            node_id = id(node)
            if node_id not in root_ids and node_id in self.nodes:
                if return_id:
                    node = node_id
                back_nodes.append(node)

        traverse_tree_backward(roots, _add_node)

        return back_nodes

    def get_connected_nodes(
        self, roots: List[Union[str, int]], return_id: bool = False
    ) -> List[Union[Node, int]]:
        """Returns all nodes that are reachable from a certain node going backward.

        Parameters
        ----------
        roots :
            The nodes from which the search should start.

        Returns
        -------
        List[Node]
            A list of all nodes that are reachable from the given nodes.
        """

        if isinstance(roots, (str, int)):
            roots = [roots]

        connected_nodes = []
        roots = [self.get_node(root) for root in roots]
        root_ids = [id(root) for root in roots]

        def _add_node(node):
            node_id = id(node)
            if node_id not in root_ids and node_id in self.nodes:
                if return_id:
                    node = node_id
                connected_nodes.append(node)

        visit_all_connected(roots, _add_node)

        return connected_nodes

    def to_json(self):
        """Creates a JSON representation of the session, to send to the frontend."""

        encoder = CustomJSONEncoder()

        # self._node_classes = {}

        # # for cls in SERVER_REGISTRY.all_classes:
        # #     try:
        # #         encoder.encode(cls)
        # #         self._node_classes[id(cls)] = cls
        # #     except Exception as e:
        # #         pass

        return dict(
            logs=self.logs.getvalue(),
            nodes=self.nodes,
            node_classes=SERVER_REGISTRY.classes_dict,
            last_updates=self.last_update,
        )

    def save(self, path: Union[str, Path]):
        import yaml

        with open(path, "w") as fh:
            yaml.dump(self.saves(), fh, yaml.SafeDumper)

    def saves(self, as_string: bool = False) -> Union[str, dict]:

        to_save = []
        for node_id, node_spec in self.nodes.items():

            node = node_spec["node"]

            inputs, inputs_mode = get_inputs_mode(node, include_defaults=False)
            node_to_save = {
                "id": node_id,
                "name": node_spec["name"],
                "cls": {
                    "module": node.__class__.__module__,
                    "name": node.__class__.__name__,
                },
                "inputs": {
                    k: inputs[k] for k in node.__signature__.parameters if k in inputs
                },
                "inputs_mode": inputs_mode,
            }

            to_save.append(node_to_save)

        state = {"nodes": to_save, "flows": self.flows}

        if as_string:
            import yaml

            return yaml.dump(state, Dumper=yaml.SafeDumper, sort_keys=False)

        return state

    def load_nodes_from_python_file(self, path: Union[str, Path]):

        with open(path, "r") as fh:
            code = fh.read()

        self.load_nodes_from_python_code(code)

    def load_nodes_from_python_code(self, code: str):

        nodes, names = python_script_to_nodes(code)

        for node in nodes:
            self.add_node(node, name=names.get(id(node), None))

    def load(self, path: Union[str, Path]):
        import yaml

        if Path(path).suffix == ".py":
            return self.load_nodes_from_python_script(path)

        with open(path, "r") as fh:
            state = yaml.load(fh, yaml.SafeLoader)

        return self.loads(state)

    def loads(self, state: Union[dict, str]):

        if isinstance(state, str):
            import yaml

            state = yaml.load(state, yaml.SafeLoader)

        loaded_nodes = {}
        nodes_map = {}

        nodified_modules = {}

        def _load_node(node_to_load, nodes_to_load):
            node_to_load = node_to_load.copy()
            old_id = node_to_load.pop("id")

            if old_id in nodes_map:
                return nodes_map[old_id]

            node_cls = node_to_load.pop("cls")

            module = node_cls["module"]
            module_name = module
            if module.startswith("nodified_"):
                mod = module.split(".")[0]
                if (
                    mod not in nodified_modules
                    and mod.replace("nodified_", "") in self.allowed_nodifiable
                ):
                    nodified_modules[mod] = nodify_module(
                        importlib.import_module(mod.replace("nodified_", ""))
                    )

                module = nodified_modules[mod]
                for k in module_name.split(".")[1:]:
                    module = getattr(module, k)
            else:
                module = importlib.import_module(module)

            node_cls = getattr(module, node_cls["name"])
            assert issubclass(
                node_cls, Node
            ), f"Provided class path leads to '{node_cls}', which is not a subclass of Node. We will not call it."

            inputs = node_to_load.pop("inputs").copy()
            inputs_mode = node_to_load.pop("inputs_mode")

            # If the function is a singledispatch, it has a registry with all the dispatchs.
            # By looking at the name of the first argument of the function that was saved,
            # try to guess which dispatch was used.
            if hasattr(node_cls.function, "registry"):
                for k, func in node_cls.function.registry.items():
                    func_node = Node.from_func(func)
                    first_arg_key = list(func_node.__signature__.parameters)[0]
                    if first_arg_key in list(inputs)[0]:
                        node_cls = func_node
                        break

            for k in inputs_mode:
                if k == node_cls._args_inputs_key:
                    inputs[k] = [
                        _load_node(nodes_to_load[node_id], nodes_to_load)
                        for node_id in inputs[k]
                    ]
                elif k == node_cls._kwargs_inputs_key:
                    inputs[k] = {
                        key: _load_node(nodes_to_load[node_id], nodes_to_load)
                        for key, node_id in inputs[k].items()
                    }
                else:
                    node_id = inputs[k]
                    inputs[k] = _load_node(nodes_to_load[node_id], nodes_to_load)

            args_inputs = inputs.pop(node_cls._args_inputs_key, [])
            new_node = node_cls(*args_inputs, **inputs)

            loaded_nodes[id(new_node)] = {**node_to_load, "node": new_node}

            nodes_map[old_id] = new_node

            return new_node

        if "nodes" in state:
            nodes_dict = {node["id"]: node for node in state["nodes"]}

            for node in state["nodes"]:
                _load_node(node, nodes_dict)

        for node in loaded_nodes.values():
            self.add_node(node["node"], node.get("name"))

        # Now set flows
        flows = state.get("flows", {})
        if len(flows) > 0:
            # We need to translate node ids into the newly created nodes
            new_flows = {}
            for flow_name, flow in flows.items():
                new_flows[flow_name] = {
                    "nodes": [id(nodes_map[node_id]) for node_id in flow["nodes"]],
                }
                for attr in ("positions", "dimensions", "expanded", "output_visible"):
                    if attr in flow:
                        new_flows[flow_name][attr] = {
                            str(id(nodes_map[int(k)])): v for k, v in flow[attr].items()
                        }

            self.set_flows({**self.flows, **new_flows})

    def set_flows(self, flows: Dict) -> float:

        for flow in flows.values():
            # Sanitize flows by removing nodes that are no longer in the session
            flow["nodes"] = [
                node_id for node_id in flow["nodes"] if node_id in self.nodes
            ]

            # Also remove attributes of nodes that are no longer in the flow.
            for k in ("positions", "dimensions", "expanded", "output_visible"):
                flow[k] = {k: v for k, v in flow[k].items() if int(k) in flow["nodes"]}

        self.flows = flows
        self.last_update["flows"] = time.time()
        return self.last_update["flows"]

    def get_flows(self) -> Dict:
        return self.flows

    def get_node_classes(self) -> Dict:
        return SERVER_REGISTRY.node_class_specs

    def get_node_classes_registry(self) -> Dict:
        return {
            "node_classes": SERVER_REGISTRY.node_class_specs,
            "types_registry": dict(SERVER_REGISTRY.types_registry_with_ids),
            "typehints": SERVER_REGISTRY.typehint_specs,
        }

    def get_logs(self) -> str:
        return self.logs.getvalue()

    def set_last_update(self, key: str, value: float):
        self.last_update[key] = value

    def emit(self):
        return self.synced.connection.emit(self)
