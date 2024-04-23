from typing import Union

from flask_socketio import SocketIO

from .emiters import emit_object
from ..sync import Connection

class SocketioConnection(Connection):
    """Helps connecting objects to the graphical interface.

    Parameters
    ----------
    socketio: socketio
        The socketIO channel that will be used for transmissions.
    """
    socketio: SocketIO

    def __init__(self, socketio: SocketIO):
        self.socketio = socketio

    def after_modification(self, obj):
        return self.emit(obj)

    def emit(self, obj):
        """Emits an object through the socketio channel."""
        return emit_object(obj)