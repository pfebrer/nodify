import pytest
from sisl.viz import Session, Plot
import time

import sisl_gui as si_gui

@pytest.fixture(scope="module")
def sisl_gui():
    si_gui.launch(only_api=True)
    time.sleep(2)

    return si_gui

def test_first_session_emit(sisl_gui):

    session = sisl_gui.get_session()

    assert isinstance(session, Session)

    session.emit()

def test_emitting_plot(sisl_gui):

    time.sleep(2)

    session = sisl_gui.get_session()
    assert isinstance(session, Session)

    plot = Plot()

    with pytest.raises(Exception):
        plot.emit()

    session.add_plot(plot)

    plot.emit()

def test_new_session_emit(sisl_gui):

    new_session = Session()

    with pytest.raises(Exception):
        new_session.emit()
    
    sisl_gui.set_session(new_session)

    new_session.emit()