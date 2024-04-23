from __future__ import annotations

from typing import Union

try:
    from .server.flask_socketio.app import SocketioApp
except:
    pass

def launch(async_mode: str = "threading", frontend: bool = True, server: bool = True,
    server_host: Union[str, None] = None, server_port: Union[int, None] = None, server_debug: bool = False, 
    interactive: bool = False) -> SocketioApp:
    
    app = SocketioApp(session=None, async_mode=async_mode)

    app.launch(frontend=frontend, server=server, server_host=server_host, server_port=server_port, server_debug=server_debug, interactive=interactive)

    return app