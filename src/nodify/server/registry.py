import inspect
import time
import typing
from collections import defaultdict
from typing import Callable, Dict, Type

from nodify import Node
from nodify.registry import REGISTRY as _REGISTRY
from nodify.registry import NodeClassRegistry

from .json import CustomJSONEncoder, as_jsonable


class NodifyServerRegistry(NodeClassRegistry):

    def __init__(self):
        self._encoder = CustomJSONEncoder()
        self.node_typehints = {}
        self.typehint_specs = {}
        self.classes_dict = {}
        self.node_class_specs = {}

        self.types_registry = defaultdict(
            lambda: {
                "first_arg": [],
                "arg": [],
                "return": [],
                "creators": [],
                "modifiers": [],
            }
        )
        self.types_registry_with_ids = defaultdict(
            lambda: {
                "first_arg": [],
                "arg": [],
                "return": [],
                "creators": [],
                "modifiers": [],
            }
        )

        super().__init__()

    def register(self, node_cls):
        self.classes_dict[id(node_cls)] = node_cls

        self.register_node_typehints(node_cls)
        self.register_node_class_spec(self._encoder, node_cls)

        self.add_to_types_registry(node_cls)
        super().register(node_cls)

    def register_typehint_spec(self, typehint):
        typehint_id = id(typehint)
        if typehint_id not in self.typehint_specs:
            input_type, field_params = self.annotation_to_input_type(typehint)

            self.typehint_specs[typehint_id] = {
                "name": getattr(typehint, "__name__", str(typehint)),
                "module": getattr(typehint, "__module__", None),
                "id": typehint_id,
                "input_type": input_type,
                "field_params": field_params,
            }

    def register_node_typehints(self, node_cls):

        try:
            typehints = typing.get_type_hints(node_cls.function)
        except:
            try:
                sig = node_cls.__signature__

                typehints = {}
                for k, v in sig.parameters.items():
                    if v is inspect._empty:
                        continue
                    typehints[k] = v.annotation

                if sig.return_annotation is not inspect._empty:
                    typehints["return"] = sig.return_annotation
            except:
                typehints = {}

        self.node_typehints[node_cls] = typehints

        for typehint in typehints.values():
            self.register_typehint_spec(typehint)

    def register_node_class_spec(self, encoder, node_class: Type[Node]):

        try:
            spec = self.get_node_class_spec(encoder, node_class)
            self._encoder.encode(spec)
        except:
            return

        self.node_class_specs[id(node_class)] = spec

    def get_node_class_spec(self, encoder, node_class: Type[Node]):
        """Parses a node class into a JSON object that can be sent to the client.

        Parameters
        ----------
        node_class : Type[Node]
            The node class to parse.
        """
        json_node_cls = {}

        json_node_cls["module"] = node_class.__module__
        json_node_cls["id"] = id(node_class)
        json_node_cls["name"] = node_class.__name__
        json_node_cls["doc"] = node_class.__doc__

        if hasattr(node_class, "function"):

            parameters_help = self.get_fields_help_from_function(node_class.function)

            type_hints = self.node_typehints[node_class].copy()

            if "return" in type_hints:
                return_typehint = type_hints.pop("return")

                json_node_cls["output_type"] = str(return_typehint)
                json_node_cls["return_typehint"] = id(return_typehint)

            parameters = inspect.signature(node_class.function).parameters

            json_node_cls["parameters"] = {}
            for k, param in parameters.items():
                parameter = {
                    "name": param.name,
                    "kind": param.kind.name,
                    "help": parameters_help.get(k, ""),
                }

                if k in type_hints:
                    parameter["typehint"] = id(type_hints[k])
                if (
                    param.default is not inspect.Parameter.empty
                    and param.default is not Node._blank
                ):
                    parameter["default"] = as_jsonable(encoder, param.default)

                json_node_cls["parameters"][k] = parameter

        if hasattr(node_class, "registry"):
            json_node_cls["registry"] = {
                str(k): id(node) for k, node in node_class.registry.items()
            }

        return json_node_cls

    def annotation_to_input_type(self, annotation):
        """Converts the annotation of an argument to an input field type.

        Parameters
        ----------
        annotation : Any
            The annotation of the function argument.
        """

        try:
            orig = typing.get_origin(annotation)
            if orig is typing.Literal:
                input_type = "select"
                options = typing.get_args(annotation)
                return input_type, {"options": options}
        except:
            pass

        if isinstance(annotation, type):
            annotation = annotation.__name__

        annotation = str(annotation)

        input_type = {
            "str": "text",
            "int": "number",
            "float": "number",
            "bool": "bool",
        }.get(annotation)

        return input_type, {}

    def get_fields_help_from_function(self, function: Callable) -> Dict[str, str]:
        """Parses a function's docstring following numpy's conventions into a dictionary of help strings.

        Parameters
        ----------
        function : Callable
            The function for which to parse the docstring.

        Returns
        -------
        dict[str, str]
            The dictionary containing a key value pair for each argument of the function.
        """
        sig = inspect.signature(function)

        fields = self.get_fields_help_from_docs(getattr(function, "__doc__", "") or "")

        sanitized_fields = {}
        for k, v in sig.parameters.items():
            if k in fields:
                sanitized_fields[k] = fields[k]
            else:
                sanitized_fields[k] = ""

        return sanitized_fields

    def get_fields_help_from_docs(self, docs: str) -> Dict[str, str]:
        """Parses a docstring following numpy's conventions into a dictionary of help strings.

        Parameters
        ----------
        docs : str
            The docstring to parse.

        Returns
        -------
        dict[str, str]
            The dictionary containing a key value pair for each argument described in the docstring.
            Note that some arguments may be missing, or even there can be some extra arguments that
            are not really in the function's signature.
        """

        params_i = docs.find("Parameters\n")
        # Check number of spaces used for tabulation
        n_spaces = docs[params_i + 11 :].find("-")

        params_docs = {}
        arg_key = None
        key_msg = ""
        for line in docs[params_i:].split("\n")[2:]:
            if len(line) <= n_spaces:
                break

            if line[n_spaces] != " ":
                if ":" not in line:
                    break
                if arg_key is not None:
                    params_docs[arg_key] = key_msg
                key_msg = ""
                arg_key = line.split(":")[0].strip()
            else:
                prefix = "" if key_msg.endswith(" ") or key_msg == "" else " "
                key_msg += prefix + line.lstrip()
        if arg_key is not None:
            params_docs[arg_key] = key_msg.capitalize()

        return params_docs

    def add_to_types_registry(self, node_cls):
        typehints = self.node_typehints[node_cls]

        node_cls_id = id(node_cls)

        for i, (key, typehint) in enumerate(typehints.items()):

            type_id = id(typehint)

            if i == 0:
                k = "first_arg"
            elif key == "return":
                k = key
                first_arg_typehint = list(typehints.values())[0]
                if first_arg_typehint is typehint:
                    self.types_registry_with_ids[type_id]["modifiers"].append(
                        node_cls_id
                    )
                    try:
                        self.types_registry[typehint]["modifiers"].append(node_cls)
                    except TypeError:
                        pass
                else:
                    self.types_registry_with_ids[type_id]["creators"].append(
                        node_cls_id
                    )
                    try:
                        self.types_registry[typehint]["creators"].append(node_cls)
                    except TypeError:
                        pass
            else:
                k = "arg"

            self.types_registry_with_ids[type_id][k].append(node_cls_id)

            try:
                self.types_registry[typehint][k].append(node_cls)
            except TypeError:
                pass


SERVER_REGISTRY = NodifyServerRegistry()
_REGISTRY.subscribe(SERVER_REGISTRY)


class SessionRegistry(NodeClassRegistry):

    def __init__(self, session):
        self.session = session

    def register(self, node_cls):
        self.session.set_last_update("node_classes", time.time())
