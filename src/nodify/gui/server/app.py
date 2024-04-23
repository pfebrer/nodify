from typing import Union

from .session import Session
from .sync import Connection, NotConnected

class App:
    """Base app class that manages a session and a connection."""

    session: Union[Session, None]
    connection: Connection

    def __init__(self, session: Union[Session, None], connection: Connection):
        self.connection = connection
        self.session = session

        if self.session is not None:
            self.session.synced.set_connection(self.connection)

    def set_session(self, new_session: Session):
        """Binds a new session to the app.

        The old session is unbound from the app. If you want to keep it, store
        it in a variable before setting the new session. Note that, otherwise, 
        THE OLD SESSION WILL BE LOST.

        Parameters
        ----------
        new_session: Session
            the new session to be used by the app.

        Returns
        ----------
        Session
            the new session that should be connected to the app.
        """
        # Disconnect the old session from the app
        if self.session is not None:
            self.session.synced.disconnect()

        # Connect the new session to the app
        new_session.synced.set_connection(self.connection)
        # And associate it with it
        self.session = new_session