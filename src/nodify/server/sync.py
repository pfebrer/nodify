""" In this file we build the patches that will make the session
capable of updating the GUI automatically when an action is performed
on it """

from abc import ABC, abstractmethod
from functools import wraps
from typing import Union

__all__ = ["Connection", "NotConnected", "Synchronized"]


class Connection(ABC):
    """Object that represents a connection, which is used to syncronize
    python objects with e.g. the graphical interface."""

    def connect(self, obj):
        """Called when the connection is associated to the object."""
        ...

    def disconnect(self, obj):
        """Called before the connection is deassociated from the object."""
        ...

    @abstractmethod
    def after_modification(self, obj):
        """Implements whatever the connection wants to do with an object
        once it has been modified."""
        ...


class NotConnected(Connection):
    """A connection that does nothing"""

    def after_modification(self, obj):
        pass


class Synchronized:
    """Takes care of emiting all changes automatically to the UI.

    An instance of Syncronized has an object and a connection associated to it.
    Methods of the object are wrapped so that the object is handled by the connection
    after the method is executed.

    Note that one can avoid the behavior of Synchronized in two different ways:
        - Setting the autosync_enabled attribute to False.
        - Passing emit=False to the executed method

    Parameters
    ----------
    obj: any
        the object that we want to keep syncronized.
    connection: Connection, optional
        the connection that will be used to syncronize the object.
    """

    def __init__(self, obj, connection: Union[Connection, None] = None):
        self.autosync_enabled = True

        if connection is None:
            connection = NotConnected()
        self.connection = connection

        self._obj = obj

    def __getattr__(self, key):
        attr = getattr(self._obj, key)
        if callable(attr):
            return self.dispatch(attr)
        return attr

    def set_connection(self, new_connection: Connection):
        self.connection.disconnect(self._obj)
        self.connection = new_connection
        self.connection.connect(self._obj)

    def disconnect(self):
        self.connection.disconnect(self._obj)
        self.connection = NotConnected()
        self.connection.connect(self._obj)

    def dispatch(self, method):

        # We won't act if it's a private method or autosync is turned off
        if method.__name__[0] == "_" or not self.autosync_enabled:
            return method

        @wraps(method)
        def with_changes_emitted(*args, emit=True, **kwargs):

            ret = method(*args, **kwargs)

            if emit:
                self.connection.after_modification(self._obj)

            return ret

        return with_changes_emitted
