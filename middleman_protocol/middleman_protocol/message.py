import sys
from hashlib import sha256

from construct import Byte
from construct import Bytes
from construct import Const
from construct import Container
from construct import Enum
from construct import GreedyBytes
from construct import Int16ub
from construct import Int32ub
from construct import Prefixed
from construct import Struct
from construct import VarInt

from golem_messages.message.base import Message as BaseGolemMessage

from .constants import FRAME_SEPARATOR
from .constants import PayloadType
from .constants import PAYLOAD_TYPE_TO_MIDDLEMAN_MESSAGE_CLASS
from .exceptions import MiddlemanProtocolError


class AbstractMiddlemanMessage:

    __slots__ = [
        'payload',
        'payload_type',
        'request_id',
    ]

    def __init__(self, payload, request_id):
        if type(self) == AbstractMiddlemanMessage:
            raise NotImplementedError(
                'AbstractMiddlemanMessage cannot be instantiated directly.'
            )

        self._validate_request_id(request_id)
        self.request_id = request_id

        self._validate_payload(payload)
        self.payload = self._serialize_payload(payload)

    @classmethod
    def factory(cls, payload_type, payload, request_id):
        assert payload_type in PayloadType
        assert hasattr(sys.modules[__name__], PAYLOAD_TYPE_TO_MIDDLEMAN_MESSAGE_CLASS[payload_type])

        return getattr(
            sys.modules[__name__],
            PAYLOAD_TYPE_TO_MIDDLEMAN_MESSAGE_CLASS[payload_type]
        )(payload, request_id)

    @classmethod
    def get_message_format(cls) -> Struct:
        message_format = Struct(
            frame_signature=Bytes(64),  # TODO: How we gonna serialize
            signed_part_of_the_frame=Struct(
                request_id=Int32ub,
                payload_length=Int16ub,
                payload_type=Enum(Byte, PayloadType),
                payload=Prefixed(VarInt, GreedyBytes),
            ),
            frame_separator=Const(FRAME_SEPARATOR),
        )
        return message_format

    @classmethod
    def deserialize(cls, raw_message):
        message_format = cls.get_message_format()

        deserialized_message = message_format.parse(raw_message)

        cls._validate_signature(deserialized_message)
        cls._validate_length(deserialized_message)

        deserialized_payload = getattr(
            sys.modules[__name__],
            PAYLOAD_TYPE_TO_MIDDLEMAN_MESSAGE_CLASS[
                PayloadType[str(deserialized_message.signed_part_of_the_frame.payload_type)]
            ]
        )._deserialize_payload(deserialized_message.signed_part_of_the_frame.payload)

        return deserialized_payload

    @classmethod
    def _deserialize_payload(cls, payload):
        return payload

    @classmethod
    def _validate_length(cls, message):
        if not len(message.signed_part_of_the_frame.payload) == message.signed_part_of_the_frame.payload_length:
            raise MiddlemanProtocolError(
                f'Deserialized message payload length is {len(message.signed_part_of_the_frame.payload)} '
                f'instead of {message.signed_part_of_the_frame.payload_length}.'
            )

    @classmethod
    def _validate_signature(cls, message):
        if not message.frame_signature:  # TODO: Really verify signature
            raise MiddlemanProtocolError(
                f'Deserialized message signature wrong.'
            )

    def serialize(self) -> bytes:
        assert isinstance(self.payload, bytes)

        message_format = self.get_message_format()

        signed_part_of_the_frame = Container(
            request_id=self.request_id,
            payload_length=len(self.payload),
            payload_type=self.payload_type,
            payload=self.payload,
        )

        raw_signed_part_of_the_frame = message_format.signed_part_of_the_frame.build(
            signed_part_of_the_frame
        )

        #frame_signature = sha256(raw_signed_part_of_the_frame).hexdigest().encode()  # TODO: TMP

        frame_signature = b'x' * 64

        message = Container(
            frame_signature=frame_signature,
            signed_part_of_the_frame=signed_part_of_the_frame,
        )

        raw_message = message_format.build(message)
        return raw_message

    def _serialize_payload(self, payload):
        return payload

    def _validate_request_id(self, request_id):
        if not isinstance(request_id, int):
            raise MiddlemanProtocolError(
                f'request_id  is {type(request_id)} instead of int.'
            )

    def _validate_payload(self, payload):
        pass


class GolemMessageMiddlemanMessage(AbstractMiddlemanMessage):

    payload_type = PayloadType.GOLEM_MESSAGE

    @classmethod
    def _deserialize_payload(cls, payload: bytes) -> BaseGolemMessage:
        return BaseGolemMessage.deserialize(payload, None, check_time=False)

    def _serialize_payload(self, payload: BaseGolemMessage) -> bytes:
        return payload.serialize()

    def _validate_payload(self, payload: BaseGolemMessage) -> None:
        if not isinstance(payload, BaseGolemMessage):
            raise MiddlemanProtocolError(
                f'Trying to create GolemMessageMiddlemanMessage but passed payload type is {type(payload)} '
                f'instead of Golem Message.'
            )


class ErrorMiddlemanMessage(AbstractMiddlemanMessage):

    payload_type = PayloadType.ERROR

    @classmethod
    def _deserialize_payload(cls, payload: bytes) -> tuple:
        return tuple(payload.decode().split('---'))

    def _serialize_payload(self, payload: tuple) -> bytes:
        return ('---'.join(payload)).encode()

    def _validate_payload(self, payload: tuple) -> None:
        if not isinstance(payload, tuple):
            raise MiddlemanProtocolError(
                f'Trying to create ErrorMiddlemanMessage but passed type payload is '
                f'{type(payload)} instead of tuple.'
            )
        if len(payload) != 2:
            raise MiddlemanProtocolError(
                f'Trying to create ErrorMiddlemanMessage but passed payload tuple has length '
                f'{len(payload)} instead of 2.'
            )


class AuthenticationChallengeMiddlemanMessage(AbstractMiddlemanMessage):

    payload_type = PayloadType.AUTHENTICATION_CHALLENGE


class AuthenticationResponseMiddlemanMessage(AbstractMiddlemanMessage):

    payload_type = PayloadType.AUTHENTICATION_RESPONSE
