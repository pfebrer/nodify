"""Implements conversion from python elements to JSON to send the messages."""

import pathlib
from typing import Any, Dict, Literal, Optional, Tuple

try:
    import plotly.graph_objects as go

    _PLOTLY_AVAILABLE = True
except:
    _PLOTLY_AVAILABLE = False

try:
    import numpy as np

    np_ndarray = np.ndarray
    np_generic = np.generic
    _NUMPY_AVAILABLE = True
except:

    class np_ndarray:
        pass

    class np_generic:
        pass

    _NUMPY_AVAILABLE = False

import simplejson
from simplejson.encoder import JSONEncoder

from nodify import Node


def as_jsonable(encoder, obj):
    if (
        _NUMPY_AVAILABLE
        and isinstance(obj, np_ndarray)
        and not np.issubdtype(obj.dtype, np.number)
    ):
        return as_jsonable(encoder, obj.tolist())
    elif isinstance(obj, (list, tuple)):
        return type(obj)([as_jsonable(encoder, v) for v in obj])
    elif isinstance(obj, dict):
        return {k: as_jsonable(encoder, v) for k, v in obj.items()}
    elif not isinstance(obj, (tuple, float, str, int, bool, type(None), np_ndarray)):
        return as_jsonable(encoder, encoder.default(obj))
    else:
        return obj


def get_inputs_mode(
    node: Node, encoder: Optional[JSONEncoder] = None, include_defaults: bool = True
) -> Tuple[Dict[str, Any], Dict[str, Literal["NODE"]]]:
    """Given some inputs, finds out which of them are nodes and which are not.

    Parameters
    ----------
    node : Node
        The node for which to get the inputs mode.

    Returns
    -------
    inputs
        The inputs dictionary with the nodes replaced by their IDs.
    inputs_mode
        The dictionary indicating which inputs are nodes.
    """
    # Go over the inputs and find out which of them contain nodes
    # We need to mark them so that the GUI knows it. Then, we replace
    # the nodes by their ID.
    if include_defaults:
        inputs = {**node.inputs}
    else:
        inputs = {**node._inputs}

    inputs_mode = {}
    for k, v in inputs.items():
        if k == node._args_inputs_key and len(v) > 0 and isinstance(v[0], Node):
            # This is the *args input, and it contains nodes
            inputs_mode[k] = "NODE"
            inputs[k] = [id(node) for node in v]
        elif (
            k == node._kwargs_inputs_key
            and len(v) > 0
            and isinstance(list(v.values())[0], Node)
        ):
            # This is the **kwargs input, and it contains nodes
            inputs_mode[k] = "NODE"
            inputs[k] = {k: id(node) for k, node in v.items()}
        elif isinstance(v, Node):
            # This is a simple input, and it contains a node
            inputs_mode[k] = "NODE"
            inputs[k] = id(v)
        else:
            inputs[k] = as_jsonable(encoder, v) if encoder is not None else v

    return inputs, inputs_mode


def node_to_json(encoder: JSONEncoder, node: Node):
    """Parses a node into a JSON object that can be sent to the client.

    Parameters
    ----------
    node : Node
        The node object to parse.
    """
    json_node = {}

    json_node["id"] = id(node)
    json_node["class"] = id(node.__class__)

    json_node["last_log"] = node.last_log
    if getattr(encoder, "encode_node_logs", True):
        json_node["logs"] = node.logs

    json_node["outdated"] = node._outdated
    json_node["errored"] = node._errored

    json_node["inputs"], json_node["inputs_mode"] = get_inputs_mode(node, encoder)

    json_node["output_links"] = [id(link) for link in node._output_links]

    output = node._output

    if output is not Node._blank:
        json_node["output_class"] = output.__class__.__name__
        json_node["output_class_id"] = id(output.__class__)

        json_node["output"] = as_jsonable(encoder, output)

        if hasattr(output, "_repr_nodify"):
            output = output._repr_nodify_server()

        if _PLOTLY_AVAILABLE and isinstance(output, go.Figure):
            json_node["output_repr"] = {
                "type": "plotlyfigure",
                "data": as_jsonable(encoder, output),
            }
        elif hasattr(output, "_repr_html_"):
            if _PLOTLY_AVAILABLE and isinstance(output._repr_html_.__self__, go.Figure):
                # This is a plotly figure, so we need to convert it to a JSON object
                json_node["output_repr"] = {
                    "type": "plotlyfigure",
                    "data": as_jsonable(encoder, output._repr_html_.__self__),
                }
            else:
                html = output._repr_html_()
                json_node["output_repr"] = {
                    "type": "html",
                    "data": html,
                }
        else:
            json_node["output_repr"] = {
                "type": "text",
                "data": repr(output),
            }

    return json_node


class CustomJSONEncoder(JSONEncoder):
    """Custom JSON encoder that can handle more types than the default one.

    Specifically, it can handle: node objects, session objects, node classes
    and plotly figures.
    """

    def __init__(self, *args, node_logs: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        self.encode_node_logs = node_logs

    def default(self, obj):

        if isinstance(obj, Node):
            return node_to_json(self, obj)
        elif _PLOTLY_AVAILABLE and isinstance(obj, go.Figure):
            return obj.to_plotly_json()
        elif hasattr(obj, "to_json"):
            return obj.to_json()
        elif isinstance(obj, np_ndarray):
            return obj.tolist()
        elif isinstance(obj, np_generic):
            return obj.item()
        elif isinstance(obj, pathlib.Path):
            return str(obj)
        elif isinstance(obj, type):
            return repr(obj)

        try:
            return super().default(obj)
        except Exception as e:
            return repr(obj)


class CustomJsonModule:
    """Class that mimics the simplejson module, but with a custom JSON encoder
    and ignoring NaN values by default (i.e. converting them to null)."""

    def __init__(self, encoder_cls=CustomJSONEncoder):
        self.encoder_cls = encoder_cls

    def dump(self, *args, **kwargs):
        if "cls" not in kwargs:
            kwargs["cls"] = self.encoder_cls
        if "ignore_nan" not in kwargs:
            kwargs["ignore_nan"] = True

        return simplejson.dump(*args, **kwargs)

    def dumps(self, *args, **kwargs):
        if "cls" not in kwargs:
            kwargs["cls"] = self.encoder_cls
        if "ignore_nan" not in kwargs:
            kwargs["ignore_nan"] = True

        return simplejson.dumps(*args, **kwargs)

    def loads(self, *args, **kwargs):
        return simplejson.loads(*args, **kwargs)

    def load(self, *args, **kwargs):
        return simplejson.load(*args, **kwargs)

    def __getattr__(self, key):
        return getattr(simplejson, key)
