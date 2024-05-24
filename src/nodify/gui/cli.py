import argparse
import importlib

from nodify.gui import launch_gui
from nodify.utils import nodify_module


def build_cli(title, description, defaults, modules=[]):
    """Builds the command line interface for launching nodify's GUI"""

    def cli():
        parser = argparse.ArgumentParser(prog=title, description=description)

        parser.add_argument(
            "modules",
            type=str,
            nargs="*",
            default=defaults.get("modules", []),
            help="Modules to nodify before launching the GUI",
        )
        parser.add_argument(
            "--backend",
            type=str,
            default=defaults.get("backend", "socket"),
            help="The backend to use. If 'socket', the server will be launched.",
        )
        parser.add_argument(
            "--port",
            type=int,
            default=defaults.get("port", None),
            help="If the backend is 'socket', port to use to communicate between frontend and backend.",
        )
        parser.add_argument(
            "--host",
            type=str,
            default=defaults.get("host", None),
            help="If the backend is 'socket', host to use to communicate between frontend and backend.",
        )
        parser.add_argument(
            "--pyodide-packages",
            type=str,
            nargs="*",
            default=defaults.get("pyodide_packages", []),
            help="If the backend is 'pyodide', the packages to load from the pyodide distribution.",
        )
        parser.add_argument(
            "--pyodide-pypi-packages",
            type=str,
            nargs="*",
            default=defaults.get("pyodide_pypi_packages", []),
            help="If the backend is 'pyodide', the packages to install from PyPI in the pyodide environment.",
        )
        parser.add_argument(
            "--session-cls",
            type=str,
            default=defaults.get("session_cls", None),
            help="The session class to instantiate to create the session. If not provided, the default session will be used.",
        )

        args = parser.parse_args()

        modules_to_nodify = [*modules, *(args.modules or [])]

        # Nodify all requested modules
        for module_string in modules_to_nodify:
            module = importlib.import_module(module_string)
            nodify_module(module)

        launch_gui(
            backend=args.backend,
            port=args.port,
            host=args.host,
            session_cls=args.session_cls,
            pyodide_packages=args.pyodide_packages,
            pyodide_pypi_packages=args.pyodide_pypi_packages,
        )

    return cli


nodify_gui_cli = build_cli(
    "nodify-gui",
    "Command line utility to launch nodify's graphical interface.",
    {
        "backend": "socket",
        "port": None,
        "host": None,
        "session_cls": None,
        "pyodide_packages": [],
        "pyodide_pypi_packages": [],
    },
)
