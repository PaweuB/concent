from middleman_protocol.constants import PayloadType


PAYLOAD_TYPE_TO_MIDDLEMAN_MESSAGE_CLASS = {}


def register(cls):
    """
    This is decorator used to create registry of subclasses of middleman_protocol.message.AbstractMiddlemanMessage.

    Registry is used to get proper subclass depending on value from middleman_protocol.constants.PayloadType enum.
    It cannot be done directly as a dict because of circular import problem.
    """
    assert hasattr(cls, 'payload_type')
    assert cls.payload_type in PayloadType

    PAYLOAD_TYPE_TO_MIDDLEMAN_MESSAGE_CLASS[cls.payload_type] = cls
    return cls
