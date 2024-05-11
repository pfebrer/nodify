import os
from typing import Any, Callable, Optional

NODES_ENV_VARIABLES = {}


def register_env_variable(
    name: str,
    default: Any,
    description: Optional[str] = None,
    process: Optional[Callable[[Any], Any]] = None,
):
    """Register a new global nodes environment variable.

    Parameters
    -----------
    name: str or list-like of str
        the name of the environment variable. Needs to
        be correctly prefixed with "NODES_".
    default: any, optional
        the default value for this environment variable
    description: str, optional
        a description of what this variable does.
    process : callable, optional
        a callable which will be used to post-process the value when retrieving
        it.

    Raises
    ------
    ValueError
       if `name` does not start with "NODIFY_"
    """
    if not name.startswith("NODIFY_"):
        raise ValueError("register_environ_variable: name should start with 'NODIFY_'")
    if process is None:

        def process(arg: Any) -> Any:
            return arg

    global NODES_ENV_VARIABLES

    if name in NODES_ENV_VARIABLES:
        raise NameError(f"register_environ_variable: name {name} already registered")

    NODES_ENV_VARIABLES[name] = {
        "default": default,
        "description": description,
        "process": process,
        "value": os.environ.get(name, default),
    }


def get_env_variable(name: str):
    """Gets the value of a registered environment variable.

    Parameters
    -----------
    name: str
        the name of the environment variable.
    """
    variable = NODES_ENV_VARIABLES[name]
    return variable["process"](variable["value"])
