from flask_socketio import emit as real_emit

from ..session import Session

__all__ = [
    "emit",
    "emit_session",
    "emit_plot",
    "emit_loading_plot",
    "emit_loading_plot",
    "emit_error",
    "emit_object",
]


def emit(*args, socketio=None, **kwargs):

    if socketio is not None:
        socketio.emit(*args, **kwargs)
    else:
        real_emit(*args, **kwargs)


def emit_error(err, **kwargs):
    emit("server_error", str(err), broadcast=False, **kwargs)


def emit_session(session_to_emit=None, broadcast=True, **kwargs):
    """
    Emits a session through the socket connection

    Parameters
    -----------
    session_to_emit: Session.
        The session you want to emit.
    """
    return emit("current_session", session_to_emit, broadcast=broadcast, **kwargs)


def emit_object(obj, *args, **kwargs):
    """
    Emits an object to the GUI.

    Parameters
    ----------
    obj:
        the object that you want to emit
    *args:
        passed directly to the corresponding emiter.
    **kwargs:
        passed directly to the corresponding emiter.
    """

    if isinstance(obj, Session):
        emiter = emit_session
    else:
        raise NotImplementedError(f"Cannot emit object of type {type(obj)}")

    return emiter(obj, *args, **kwargs)
