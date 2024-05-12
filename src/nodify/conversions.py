import importlib
import inspect
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .context import temporal_context
from .node import ConstantNode, Node
from .parse import nodify_code


def node_to_python_script(
    output_node: Node,
    include_defaults: bool = False,
    as_function: bool = False,
    function_name: Optional[str] = "function",
    names_map: Dict[int, str] = {},
):
    """Converts the tree leading to a given node into a Python script.

    Parameters
    ----------
    output_node:
        The node whose output the script will generate.
    include_defaults:
        Whether to include the default inputs of the functions in the script.
    as_function:
        Whether to write the code defining a function that encapsulates all the computation
        needed.
        If False, the script will be a sequence of variable assignments.
    function_name:
        The name of the function to be created if `as_function` is True.
    names_map:
        A dictionary mapping the id of a node to a custom name. The name will be used for the
        variable containing the value that the node returns.
    """

    variables = {}

    @dataclass
    class DeclaredVariable:
        id: int

        def __repr__(self):
            return variables[self.id]["key"]

    def scrape(key, node):

        if id(node) in variables:
            return

        variable = {}

        if isinstance(node, ConstantNode):
            variable["type"] = "constant"
            variable["value"] = node.inputs["value"]
        else:
            vars = {}
            for k, v in node._inputs.items():

                if k == node._args_inputs_key:
                    if len(v) > 0 and isinstance(v[0], Node):
                        for i, arg_node in enumerate(v):
                            node_name = names_map.get(id(arg_node), f"{k}_{i}").replace(
                                " ", "_"
                            )
                            scrape(node_name, arg_node)

                        vars[k] = [DeclaredVariable(id(arg_node)) for arg_node in v]
                elif k == node._kwargs_inputs_key:
                    if len(v) > 0 and isinstance(list(v.values())[0], Node):
                        for kwarg_key, kwarg_node in v.items():
                            node_name = names_map.get(
                                id(kwarg_node), kwarg_key
                            ).replace(" ", "_")
                            scrape(node_name, kwarg_node)

                        vars[k] = {
                            kwarg_key: DeclaredVariable(id(kwarg_node))
                            for kwarg_key, kwarg_node in v.items()
                        }
                elif isinstance(v, Node):
                    node_name = names_map.get(id(v), k).replace(" ", "_")
                    scrape(node_name, v)

                    vars[k] = DeclaredVariable(id(v))

            all_inputs = {**node._inputs, **vars}
            default_inputs = dict(node.default_inputs).copy()

            module = node.__module__.replace("nodified_", "")
            func_name = node.__class__.__name__

            func = getattr(importlib.import_module(module), func_name)
            args = []
            if hasattr(func, "registry"):
                # This is a singledispatch function
                first_arg = list(node.__signature__.parameters.keys())[0]
                if first_arg in all_inputs:
                    args.append(all_inputs.pop(first_arg))
                    default_inputs.pop(first_arg, None)
            args.extend(all_inputs.pop(node._args_inputs_key, []))
            default_inputs.pop(node._args_inputs_key, None)

            kwargs = {}
            kwargs.update(all_inputs.pop(node._kwargs_inputs_key, {}))
            kwargs.update(all_inputs)
            for k in kwargs:
                default_inputs.pop(k, None)
            default_inputs.pop(node._kwargs_inputs_key, None)

            variable.update(
                {
                    "type": "function",
                    "module": module,
                    "name": func_name,
                    "args": args,
                    "kwargs": kwargs,
                    "default_inputs": default_inputs,
                    "get_syntax": node.get_syntax,
                }
            )

        variables[id(node)] = {"key": key, **variable}

    output_name = names_map.get(id(output_node), "output").replace(" ", "_")

    scrape(output_name, output_node)

    def build_script(
        variables,
        include_defaults: bool = False,
        as_function: bool = False,
        function_name: Optional[str] = None,
    ):

        # Avoid duplicate variable names and create a list with all names
        variable_names = []
        for var in variables.values():
            if "key" not in var:
                continue
            var["key"] = var["key"].replace(" ", "_")

            orig_name = var["key"]
            if var["key"] in variable_names:
                i = 1
                while var["key"] in variable_names:
                    var["key"] = orig_name + f"_{i}"
                    i += 1

            variable_names.append(var["key"])

        constants = [
            variable
            for variable in variables.values()
            if variable["type"] == "constant"
        ]
        functions = [
            variable
            for variable in variables.values()
            if variable["type"] == "function"
        ]

        script = ""

        # Write imports
        function_modules = {}
        imports = defaultdict(list)
        for var in variables.values():
            if "module" not in var or var.get("get_syntax") is not None:
                continue

            module = var["module"]
            name = var["name"]
            if name in variable_names or (
                name in function_modules and function_modules[name] != module
            ):
                name = None
                var["script_name"] = f"{module}.{var['name']}"

            function_modules[var.get("script_name", var["name"])] = module

            imports[module].append(name)
        imports = {k: list(set(v)) for k, v in imports.items()}

        def _get_import_string(module, names):
            if len(names) == 1 and names[0] is None:
                return f"import {module}"

            pre = ""
            if any([name is None for name in names]):
                pre = f"import {module}\n"
            return (
                pre
                + f"from {module} import {','.join([name for name in names if name is not None])}"
            )

        script += "\n".join(
            [_get_import_string(module, names) for module, names in imports.items()]
        )
        script += "\n\n"

        def _write_func(func, include_vardef: bool = True):
            script = ""

            if func.get("get_syntax") is not None:
                try:
                    if include_vardef:
                        script += f"{func['key']} = "
                    script += f"{func['get_syntax'](*func['args'], **func['kwargs'])}\n"
                    return script
                except Exception as e:
                    pass

            if include_vardef:
                script += f"{func['key']} = "
            script += f"{func.get('script_name', func['name'])}("

            # Add positional args
            if len(func["args"]) > 0:
                script += ",".join([repr(arg) for arg in func["args"]]) + ","

            # Add keyword args
            if len(func["kwargs"]) > 0:
                script += (
                    ",".join([f"{k}={repr(v)}" for k, v in func["kwargs"].items()])
                    + ","
                )

            if include_defaults and len(func["default_inputs"]) > 0:
                script += "\n# Default inputs\n"
                script += (
                    ",".join(
                        [f"{k}={repr(v)}" for k, v in func["default_inputs"].items()]
                    )
                    + ","
                )

            if script[-1] == ",":
                script = script[:-1]
            script += ")"
            script += "\n"

            return script

        if as_function:

            # Determine function name
            if (
                function_name is None
                and len(functions) > 0
                and functions[-1]["key"] != "output"
            ):
                function_name = functions[-1]["key"]
            else:
                if function_name is None:
                    function_name = "function"

                original_name = function_name
                i = 1
                while function_name in [*variable_names, *function_modules]:
                    function_name = original_name + f"_{i}"
                    i += 1

            # Proceed to write the script
            script += f"def {function_name}("
            script += ",".join(
                [f"{const['key']}={repr(const['value'])}" for const in constants]
            )
            script += "):\n"

            if len(functions) > 0:
                for func in functions[:-1]:
                    script += "    "
                    script += _write_func(func)
                    script += "\n"

            script += f"    return {_write_func(functions[-1], include_vardef=False) if len(functions) > 0 else constants[0]['key']}"

        else:
            script += (
                "\n\n# -------------------\n#    VARIABLES\n# -------------------\n\n"
            )
            for const in constants:
                script += f"{const['key']} = {repr(const['value'])} \n"

            script += (
                "\n# -------------------\n#    COMPUTATION\n# -------------------\n\n"
            )

            for func in functions:
                script += _write_func(func)
                script += "\n"

        return script

    script = build_script(
        variables,
        include_defaults=include_defaults,
        as_function=as_function,
        function_name=function_name,
    )

    def format_script(script):
        import black
        import isort

        styled = black.format_str(script, mode=black.FileMode())

        return isort.code(styled)

    return format_script(script)


def python_script_to_nodes(code: str) -> Tuple[List[Node], Dict[int, str]]:

    names = {}

    def assign_fn(value, var_name):
        if isinstance(value, Node):
            names[id(value)] = var_name
        return value

    ns = {}
    code = nodify_code(
        code, namespace=ns, assign_fn=assign_fn, nodify_constant_assignments=True
    )

    def on_init(node):
        store.append(node)

    store = []
    with temporal_context(on_init=on_init):
        exec(code, ns)

    return store, names
