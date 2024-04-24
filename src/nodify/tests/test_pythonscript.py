"""Test the functionality to go from nodes to a python script and back."""

import pytest

from nodify import Node
from nodify.conversions import node_to_python_script
from nodify.node import ConstantNode


@Node.from_func
def simple_function():
    return 2


@Node.from_func
def kwargs_function(a=None, **kwargs):
    return kwargs if kwargs else a


@Node.from_func
def args_function(*args, kwarg=None):
    return tuple(args) if args else kwarg


def get_complex_tree():
    """Returns a hard case, containing *args, **kwargs, nested nodes
    and duplicated variable names."""
    a = ConstantNode(2)
    b = args_function(a)
    a_1 = ConstantNode(4)

    c = kwargs_function(a=a_1)

    n = kwargs_function(a=a, args=b, c=c)

    return n


constant = ConstantNode(2)
constant_dict = ConstantNode({"a": 2, "b": 4})

nodes = {
    "simple_function": simple_function(),
    "empty_kwargs_function": kwargs_function(),
    "no_kwargs_function": kwargs_function(a=2),
    "kwargs_function": kwargs_function(a=2, b=3, m=2),
    "empty_args_function": args_function(),
    "no_args_function": args_function(kwarg=8),
    "args_function": args_function(5, 9, 10, kwarg=8),
    "complex_tree": get_complex_tree(),
    "constant": constant,
    "equality": constant == 2,
    "sum": constant + 2,
    "negation": -constant,
    "getitem": constant_dict["a"],
}


@pytest.fixture(scope="module", params=list(nodes))
def node(request):
    return nodes[request.param]


@pytest.fixture(scope="module", params=[None, "final_result", "function"])
def final_key(request):
    return request.param


@pytest.fixture(scope="module")
def names_map(node, final_key):
    if final_key is not None:
        return {id(node): final_key}
    else:
        return {}


def test_as_script(node, names_map, final_key):
    """Tests the mode of generating a sequential script."""
    script = node_to_python_script(node, names_map=names_map)
    env = {}
    exec(script, env)
    final_key = final_key or "output"
    assert final_key in env
    assert env[final_key] == node.get()


@pytest.fixture(scope="module", params=[None, "my_workflow"])
def function_name(request):
    return request.param


def test_as_function(node, function_name):
    """Tests the mode of generating the code for a function."""
    script = node_to_python_script(node, as_function=True, function_name=function_name)
    env = {}
    exec(script, env)
    function_name = function_name or "function"
    assert function_name in env

    assert env[function_name]() == node.get()
