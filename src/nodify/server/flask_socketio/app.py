import code
import logging
import sys
import time
import webbrowser
from pathlib import Path
from threading import Thread
from typing import Type, Union

from flask import Flask
from flask_socketio import SocketIO

from nodify._env import get_env_variable, register_env_variable

from ..app import App
from ..json import CustomJsonModule
from ..session import Session
from ..sync import Connection
from .emiters import emit, emit_error, emit_session
from .sync import SocketioConnection
from .user_management import if_user_can  # , listen_to_users , with_user_management

# Register the environment variables that the user can tweak
register_env_variable(
    "NODIFY_SERVER_HOST",
    "localhost",
    "The host where the GUI will run when self-hosted by the user.",
    process=str,
)
register_env_variable(
    "NODIFY_SERVER_PORT",
    4000,
    "The port where the GUI will run when self-hosted by the user.",
    process=int,
)

__all__ = ["SocketioApp"]


class SocketioLastUpdateEmiter(SocketioConnection):

    def emit(self, obj):
        try:
            return emit("session_last_update", obj.last_update, broadcast=True)
        except RuntimeError:
            app = list(self.socketio.server.environ.values())[0]["flask.app"]
            with app.app_context():
                emit(
                    "session_last_update",
                    obj.last_update,
                    broadcast=True,
                    namespace="/",
                )


class SocketioApp(App):

    connection: SocketioConnection

    host: Union[str, None]
    port: Union[int, None]

    def __init__(
        self,
        session: Union[Session, None],
        session_cls: Type[Session] = Session,
        async_mode="threading",
    ):
        self.host = None
        self.port = None

        self.app = Flask("NODIFY API")

        # No user management yet
        if False:
            ...
            # with_user_management(self.app)

        socketio = SocketIO(
            self.app,
            cors_allowed_origins="*",
            json=CustomJsonModule(),
            manage_session=True,
            async_mode=async_mode,
            max_http_buffer_size=1e20,
        )
        # We set max_http_buffer_size to 1e20 to in practice don't impose any limit on the size
        # This is because big files might be transferred.
        # async_mode="threading" this option can not use websockets, therefore there is less communication performance
        # however, it's the only way we can emit socket events from outside of the thread that is running the api
        # Maybe instead of threading we can use socketio.start_background_task (see https://github.com/miguelgrinberg/Flask-SocketIO/issues/876)
        # You can set this to any other async_mode if you don't plan to interact from python (i.e. only through the GUI)
        on = socketio.on

        if False:
            ...
            # listen_to_users(on, emit_session)

        connection = SocketioLastUpdateEmiter(socketio)

        self.socketio = socketio

        if session is None:
            session = session_cls()

        super().__init__(session=session, connection=connection)

        # -------------------------------------------
        # From now on, we define the socketio events
        # -------------------------------------------
        @socketio.on_error()
        def send_error(err):
            if self.session is not None:
                self.session.logger.exception(err)

            emit_error(err)
            emit_session(self.session, broadcast=True)
            raise err

        @on("request_last_updates")
        @if_user_can("see")
        def send_session(path=None):
            return self.session.last_update if self.session else {}

        @on("apply_method_on_session")
        @if_user_can("edit")
        def apply_method(method_name, kwargs={}, *args):

            session = self.session

            if session is None:
                raise Exception("The app is not associated with any session.")

            session.logger.info(f"Applying method {method_name}")
            session.logger.debug(
                f"Applying method {method_name} with args {args} and kwargs {kwargs}"
            )

            if kwargs is None:
                # This is because the GUI might send None
                kwargs = {}

            # Remember that if the method is not found an error will be raised
            # but it will be handled socketio.on_error (used above)
            method = getattr(session.synced, method_name)

            # Since the session is bound to the app, this will automatically emit the
            # session
            return method(*args, **kwargs)

        # @on("load_session_from_file")
        # @if_user_can("edit")
        # def load_session_from_file(file_bytes, name):
        #     session = get_session()

        #     file_name, dirname, keep = _write_file(session, file_bytes, name)

        #     session = load(file_name)
        #     if isinstance(session, Session):
        #         set_session(session)
        #         emit_session(session, broadcast=True)

        #     _remove_temp_file(file_name, dirname)

        #     if not isinstance(session, Session):
        #         raise ValueError("A session could not be loaded from the file provided.")

        # @on("get_session_file")
        # @if_user_can("see")
        # def send_session_file():
        #     session = get_session()

        #     dirname = session.get_setting("file_storage_dir")
        #     if not dirname.exists():
        #         dirname.mkdir()

        #     file_name = dirname / "__temp_session"
        #     apply_method("save", {"path": file_name})

        #     with open(file_name, "rb") as fh:
        #         session_bytes = fh.read()

        #     emit("session_file", session_bytes, broadcast=False)

    def run_server(
        self,
        host: Union[str, None] = None,
        port: Union[int, None] = None,
        debug: bool = False,
    ):
        # Disable all kinds of logging
        if not debug:
            self.app.logger.disabled = True
            log = logging.getLogger("werkzeug")
            log.disabled = True
            cli = sys.modules["flask.cli"]
            cli.show_server_banner = lambda *x: None

        if host is None:
            host = get_env_variable("NODIFY_SERVER_HOST")
        if port is None:
            port = get_env_variable("NODIFY_SERVER_PORT")

        self.host = host
        self.port = port

        print(
            f"\nApi running on {self.get_server_address()}...\nconnect the GUI to this address or send it to someone for sharing."
        )

        return self.socketio.run(
            self.app, debug=debug, host=host, port=port, allow_unsafe_werkzeug=True
        )

    def get_server_address(self) -> str:
        return f"http://{self.host}:{self.port}"

    def open_frontend(self):
        """Opens the graphical interface"""
        from nodify.gui import open_frontend

        open_frontend("socket", self.port, self.host)

    def launch(
        self,
        frontend: bool = True,
        server: bool = True,
        server_host: Union[str, None] = None,
        server_port: Union[int, None] = None,
        server_debug: bool = False,
        interactive: bool = False,
    ):
        """Launches the graphical interface.

        Parameters
        -----------
        frontend: bool, optional
            Whether to open the frontend, defaults to True.
        server: bool, optional
            Whether to start the server, defaults to True.
        server_host: str, optional
            The host to use for the server.
            If not provided, it will be taken from the environment variable NODIFY_SERVER_HOST.
        server_port: int, optional
            The port to use for the server.
            If not provided, it will be taken from the environment variable NODIFY_SERVER_PORT.
        server_debug: bool, optional
            Whether to run the server in debug mode.
        interactive: bool, optional
            whether an interactive console should be started.
        """

        if not server:
            return

        self.threads = [
            Thread(
                target=self.run_server,
                kwargs={
                    "host": server_host,
                    "port": server_port,
                    "debug": server_debug,
                },
            )
        ]

        if interactive:
            # To launch an interactive console (not needed from jupyter)
            self.threads.append(
                Thread(
                    target=code.interact,
                    kwargs={
                        "local": {"app": self, "session": self.session},
                        "banner": "Interactive console started. The 'app' variable contains the current app. It has a session attribute with the current session.",
                    },
                )
            )

        for t in self.threads:
            t.start()

        if frontend:
            self.open_frontend()

        if interactive:
            try:
                while 1:
                    time.sleep(0.1)
            except KeyboardInterrupt:
                print("Please use Ctrl+D to kill the interactive console first")
