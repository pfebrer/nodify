# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
from __future__ import annotations

from typing import Type

import pytest

from nodify import Workflow
from nodify.node import ConstantNode
from nodify.utils import traverse_tree_forward


@pytest.fixture(
    scope="module",
    params=["from_func", "explicit_class", "input_operations", "with_annotations"],
)
def triple_sum(request) -> Type[Workflow]:
    """Returns a workflow that computes a triple sum.

    The workflow might have been obtained in different ways, but they all
    should be equivalent in functionality.
    """

    def my_sum(a, b):
        return a + b

    if request.param == "from_func":
        with pytest.warns():
            # A triple sum
            @Workflow.from_func
            def triple_sum(a, b, c):
                first_sum = my_sum(a, b)
                return my_sum(first_sum, c)

        triple_sum._sum_key = "my_sum"
    elif request.param == "explicit_class":

        with pytest.warns():

            class triple_sum(Workflow):
                @staticmethod
                def function(a, b, c):
                    first_sum = my_sum(a, b)
                    return my_sum(first_sum, c)

        triple_sum._sum_key = "my_sum"
    elif request.param == "input_operations":

        with pytest.warns():

            @Workflow.from_func
            def triple_sum(a, b, c):
                first_sum = a + b
                return first_sum + c

        triple_sum._sum_key = "BinaryOperationNode"

    elif request.param == "with_annotations":

        with pytest.warns():

            @Workflow.from_func
            def triple_sum(a: int, b: int, c: int) -> int:
                first_sum = a + b
                return first_sum + c

        triple_sum._sum_key = "BinaryOperationNode"

    return triple_sum


def test_updated_connections(triple_sum):

    a = ConstantNode(2)
    b = ConstantNode(3)
    c = ConstantNode(5)

    val = triple_sum(a, b, c)

    # They are linked to two nodes: the workflow, and the workflow input node.
    assert len(a._output_links) == 2
    assert len(b._output_links) == 2
    assert len(c._output_links) == 2
    assert len(val._input_nodes) == 3
    assert val.get() == 10

    val.update_inputs(a=3)

    assert len(a._output_links) == 0
    assert len(b._output_links) == 2
    assert len(c._output_links) == 2
    assert len(val._input_nodes) == 2
    assert val.get() == 11


def test_named_vars(triple_sum):
    # Check that the first_sum variable has been detected correctly.
    assert set(triple_sum.dryrun_nodes.named_vars) == {"first_sum"}

    # And check that it maps to the correct node.
    assert (
        triple_sum.dryrun_nodes.first_sum
        is triple_sum.dryrun_nodes.workers[triple_sum._sum_key]
    )


def test_workflow_instantiation(triple_sum):
    # Create an instance of the workflow.
    flow = triple_sum(2, 3, 5)

    # Check that the workflow nodes have been instantiated.
    assert hasattr(flow, "nodes")
    for k, wf_node in flow.dryrun_nodes.items():
        assert k in flow.nodes._all_nodes
        new_node = flow.nodes[k]
        assert wf_node is not new_node

    # Traverse all the workflow and make sure that there are no references
    # to the workflow dryrun nodes.
    old_ids = [id(n) for n in flow.dryrun_nodes.values()]

    def check_not_old_id(node):
        assert id(node) not in old_ids

    traverse_tree_forward(flow.nodes.inputs.values(), check_not_old_id)


def test_right_result(triple_sum):
    assert triple_sum(a=2, b=3, c=5).get() == 10


def test_updatable_inputs(triple_sum):
    val = triple_sum(a=2, b=3, c=5)

    assert val.get() == 10

    val.update_inputs(b=4)

    assert val.get() == 11


def test_recalc_necessary_only(triple_sum):
    val = triple_sum(a=2, b=3, c=5)

    assert val.get() == 10

    val.update_inputs(c=4)

    assert val.get() == 9

    assert val.nodes[triple_sum._sum_key]._nupdates == 1
    assert val.nodes[f"{triple_sum._sum_key}_1"]._nupdates == 2


def test_positional_arguments(triple_sum):
    val = triple_sum(2, 3, 5)

    assert val.get() == 10


# *args and **kwargs are not supported for now in workflows.
def test_args():

    with pytest.raises(TypeError):

        @Workflow.from_func
        def some_workflow(*args):
            return args

    with pytest.raises(TypeError):

        @Workflow.from_func
        def some_workflow(*args):
            return args[0]


def test_kwargs():

    with pytest.raises(TypeError):

        @Workflow.from_func
        def some_workflow(**kwargs):
            return kwargs

    with pytest.raises(TypeError):

        @Workflow.from_func
        def some_workflow(*args):
            return kwargs["key"]


# def test_kwargs_not_overriden():

#     @Node.from_func
#     def some_node(**kwargs):
#         return kwargs

#     @Workflow.from_func
#     def some_workflow(**kwargs):
#         return some_node(a=2, b=3, **kwargs)

#     # Here we check that passing **kwargs to the node inside the workflow
#     # does not interfere with the other keyword arguments that are explicitly
#     # passed to the node (and accepted by the node as **kwargs)
#     assert some_workflow().get() == {'a': 2, 'b': 3}
#     assert some_workflow(c=4).get() == {'a': 2, 'b': 3, 'c': 4}


def test_args_nodes_registered():
    def some_node(*args):
        return args

    with pytest.warns():

        @Workflow.from_func
        def some_workflow():
            a = some_node(1, 2, 3)
            return some_node(2, a, 4)

    # Check that the workflow knows about the first instanced node.
    wf = some_workflow()
    assert len(wf.nodes.workers) == 2


def test_kwargs_nodes_registered():
    def some_node(**kwargs):
        return kwargs

    with pytest.warns():

        @Workflow.from_func
        def some_workflow():
            a = some_node(a=1, b=2, c=3)
            return some_node(b=2, a=a, c=4)

    # Check that the workflow knows about the first instanced node.
    wf = some_workflow()
    assert len(wf.nodes.workers) == 2


def test_workflow_inside_workflow(triple_sum):
    def multiply(a, b):
        return a * b

    with pytest.warns():

        @Workflow.from_func
        def some_multiplication(a, b, c, d, e, f):
            """Workflow that computes (a + b + c) * (d + e + f)"""
            return multiply(triple_sum(a, b, c), triple_sum(d, e, f))

    val = some_multiplication(1, 2, 3, 1, 2, 1)

    assert val.get() == (1 + 2 + 3) * (1 + 2 + 1)

    first_triple_sum = val.nodes["triple_sum"]

    assert first_triple_sum.nodes[triple_sum._sum_key]._nupdates == 1
    assert first_triple_sum.nodes[f"{triple_sum._sum_key}_1"]._nupdates == 1

    val.update_inputs(c=2)

    assert first_triple_sum.nodes[triple_sum._sum_key]._nupdates == 1
    assert first_triple_sum.nodes[f"{triple_sum._sum_key}_1"]._nupdates == 1

    assert val.get() == (1 + 2 + 2) * (1 + 2 + 1)

    assert first_triple_sum.nodes[triple_sum._sum_key]._nupdates == 1
    assert first_triple_sum.nodes[f"{triple_sum._sum_key}_1"]._nupdates == 2


def test_outdated(triple_sum):
    wf = triple_sum(2, 3, 4)

    # Test that the workflow knows it is outdated in all possible situations
    assert wf._outdated == True

    wf.get()
    assert wf._outdated == False

    wf.update_inputs(a=3)
    assert wf._outdated == True

    inp = ConstantNode(3)
    wf.update_inputs(a=inp)

    wf.get()
    assert wf._outdated == False
    inp.update_inputs(value=5)
    assert wf._outdated == True

    # Now test that the workflow lets connected nodes that they are outdated.
    out = ConstantNode(wf)

    out.get()
    assert out._outdated == False

    wf.update_inputs(a=4)
    assert out._outdated == True


def test_errored(triple_sum):
    wf = triple_sum(2, 3, 4)

    assert wf._errored == False
    wf.get()
    assert wf._errored == False

    wf.update_inputs(a={"c": "f"})
    assert wf._errored == False
    with pytest.raises(Exception):
        wf.get()
    assert wf._errored == True

    wf.update_inputs(a={"c": "m"})
    assert wf._errored == False
