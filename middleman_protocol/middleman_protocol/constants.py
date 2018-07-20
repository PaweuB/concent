from enum import IntEnum
from enum import unique


@unique
class PayloadType(IntEnum):
    GOLEM_MESSAGE               = 0  # A serialized Golem message.
    ERROR                       = 1  # An error code and an error message.
    AUTHENTICATION_CHALLENGE    = 2  # A random string of bytes.
    AUTHENTICATION_RESPONSE     = 3  # A digital signature of the content sent as authentication challenge.


PAYLOAD_TYPE_TO_MIDDLEMAN_MESSAGE_CLASS = {
    PayloadType.GOLEM_MESSAGE:                 'GolemMessageMiddlemanMessage',
    PayloadType.ERROR:                         'ErrorMiddlemanMessage',
    PayloadType.AUTHENTICATION_CHALLENGE:      'AuthenticationChallengeMiddlemanMessage',
    PayloadType.AUTHENTICATION_RESPONSE:       'AuthenticationResponseMiddlemanMessage',
}


FRAME_SEPARATOR = b'\x11\x11\x11\x11\x11\x11\x11\x11\x11\x11'
