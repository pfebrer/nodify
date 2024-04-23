from .json import CustomJSONEncoder, as_jsonable

def for_js(obj):

    encoder = CustomJSONEncoder()

    return as_jsonable(encoder, obj)
