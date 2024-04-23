from nodify.node import Node
from nodify.registry import REGISTRY, NodeClassRegistry


def test_registry():

    assert isinstance(REGISTRY, NodeClassRegistry)

    sub_registry = NodeClassRegistry()

    REGISTRY.subscribe(sub_registry)

    assert len(sub_registry.all_classes) == len(REGISTRY.all_classes)

    class TestNode(Node):

        @staticmethod
        def function():
            return 1

    assert REGISTRY.all_classes[-1] is TestNode
    assert sub_registry.all_classes[-1] is TestNode

    REGISTRY.unsubscribe(sub_registry)

    class TestNode2(Node):

        @staticmethod
        def function():
            return 2

    assert REGISTRY.all_classes[-1] is TestNode2
    assert sub_registry.all_classes[-1] is TestNode
