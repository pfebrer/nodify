import importlib
import webbrowser
from pathlib import Path
from typing import List, Literal, Optional, Type, Union


def open_frontend(
    backend: Literal["socket", "pyodide"],
    port: Optional[int] = None,
    host: Optional[str] = None,
    session_cls: Optional[Union[str, Type]] = None,
    pyodide_packages: List[str] = [],
    pyodide_pypi_packages: List[str] = [],
):
    """Opens the GUI frontend in the default browser.

    Note that this function doesn't launch a server backend! For that use ``gui`` instead.

    Parameters
    ----------
    backend:
        The backend to tell the GUI to use.
    port:
        If the backend is "socket", port to use to communicate with the backend.
    host:
        If the backend is "socket", host to use to communicate with the backend.
    session_cls:
        If the backend is "pyodide", the session class to instantiate to create the session.

        If it is a string, it must be the full path to the session class, including the module.
    pyodide_packages:
        If the backend is "pyodide", the packages to load from the pyodide distribution.
    pyodide_pypi_packages:
        If the backend is "pyodide", the packages to install from PyPI in the pyodide environment.
    """
    this_path = Path(__file__)
    html_path = this_path.parent / "build" / "index.html"

    if backend == "socket":
        url = "file://" + str(html_path) + f"#/?backend=socket"
        if port is not None:
            url += f"&port={port}"
        if host is not None:
            url += f"&host={host}"

    elif backend == "pyodide":
        url = (
            "file://"
            + str(html_path)
            + f"#/?backend=pyodide&packages={','.join(pyodide_packages)}&micropipPackages={','.join(pyodide_pypi_packages)}"
        )
        if session_cls is not None:
            if hasattr(session_cls, "_nodify_default_session"):
                session_cls = session_cls._nodify_default_session

            if isinstance(session_cls, type):
                session_cls = session_cls.__module__ + "." + session_cls.__name__
            url += f"&session_cls={session_cls}"
    else:
        raise ValueError(f"Invalid backend {backend}")

    return webbrowser.open(url)


def launch_gui(
    backend: Literal["socket", "pyodide"] = "socket",
    port: Optional[int] = None,
    host: Optional[str] = None,
    session_cls: Optional[Union[str, Type]] = None,
    pyodide_packages: List[str] = [],
    pyodide_pypi_packages: List[str] = [],
):
    """Launches the GUI, including both the frontend and the backend.

    Parameters
    ----------
    backend:
        The backend to use. If "socket", the server will be launched.
    port:
        If the backend is "socket", port to use to communicate between frontend and backend.
    host:
        If the backend is "socket", host to use to communicate between frontend and backend.
    session_cls:
        The session class to instantiate to create the session. If not provided, the default session
        will be used.
    pyodide_packages:
        If the backend is "pyodide", the packages to load from the pyodide distribution.
    pyodide_pypi_packages:
        If the backend is "pyodide", the packages to install from PyPI in the pyodide environment.
    """

    if backend == "socket":
        from ..server.flask_socketio.app import SocketioApp

        if hasattr(session_cls, "_nodify_default_session"):
            session_cls = session_cls._nodify_default_session

        if isinstance(session_cls, str):

            session_path = session_cls.split(".")
            if len(session_path) == 1:
                session_path = importlib.import_module(
                    session_path[0]
                )._nodify_default_session
                session_path = session_path.split(".")

            module_name = ".".join(session_path[:-1])
            cls_name = session_path[-1]

            session = getattr(importlib.import_module(module_name), cls_name)()
        elif isinstance(session_cls, type):
            session = session_cls()
        else:
            session = None

        print(session_cls, session)

        app = SocketioApp(session=session, async_mode="threading")
        app.launch(frontend=True, server=True, server_host=host, server_port=port)
        return app
    elif backend == "pyodide":
        return open_frontend(
            "pyodide",
            session_cls=session_cls,
            pyodide_packages=pyodide_packages,
            pyodide_pypi_packages=pyodide_pypi_packages,
        )
    else:
        raise ValueError(f"Invalid backend {backend}")
