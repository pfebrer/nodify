import pytest

from nodify import Batch, Node, Workflow, temporal_context


def test_batch_works():

    batch = Batch(1, 2, 3)

    result = batch + 2

    assert isinstance(result, Node)
    assert isinstance(result.get(), Batch)
    assert list(result.get()) == [3, 4, 5]


def _some_func(a, *args, **kwargs):
    """Function to use to test batching."""
    b = a + args[0]
    return b * kwargs["factor"]


@pytest.fixture(scope="module", params=["function", "Node.from_func", "Node_class"])
def some_func(request):
    if request.param == "function":
        return _some_func
    elif request.param == "Node.from_func":
        return Node.from_func(_some_func)
    elif request.param == "Node_class":

        class func_node(Node):
            function = staticmethod(_some_func)

        return func_node


def test_batch_works_with_function(some_func):

    batch = Batch(1, 2, 3)

    result = some_func(batch, 2, factor=3)

    assert isinstance(result, Node)
    assert isinstance(result.get(), Batch)
    assert list(result.get()) == [9, 12, 15]


def test_batch_doesnt_trigger_recompute(some_func):

    batch = Batch(1, 2, 3)

    result = some_func(batch, 2, factor=3)

    result.get()
    result.get()

    assert result._nupdates == 1


def test_batch_works_on_args(some_func):

    batch = Batch(1, 2, 3)

    result = some_func(2, batch, factor=3)

    assert isinstance(result, Node)
    assert isinstance(result.get(), Batch)
    assert list(result.get()) == [9, 12, 15]


def test_batch_works_on_kwargs(some_func):

    batch = Batch(1, 2, 3)

    result = some_func(2, 2, factor=batch)

    assert isinstance(result, Node)
    assert isinstance(result.get(), Batch)
    assert list(result.get()) == [4, 8, 12]


def test_multiple_batches(some_func):

    batch = Batch(1, 2)

    result = some_func(batch, batch, factor=3)

    with temporal_context(batch_iter="zip"):
        assert isinstance(result, Node)
        assert isinstance(result.get(), Batch)
        assert list(result.get()) == [6, 12]

        assert result._nupdates == 1

    with temporal_context(batch_iter="product"):
        assert isinstance(result, Node)
        assert isinstance(result.get(), Batch)
        assert list(result.get()) == [6, 9, 9, 12]


# Implement batch.apply(). Or more generally node.apply(func, key, *args, **kwargs)
