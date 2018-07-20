import socket
from contextlib import closing
from unittest import TestCase

import assertpy
import mock
import pytest

from golem_messages.message import Ping

from middleman_protocol.constants import FRAME_SEPARATOR
from middleman_protocol.constants import PayloadType
from middleman_protocol.exceptions import MiddlemanProtocolError
from middleman_protocol.message import AbstractMiddlemanMessage
from middleman_protocol.message import AuthenticationChallengeMiddlemanMessage
from middleman_protocol.message import AuthenticationResponseMiddlemanMessage
from middleman_protocol.message import ErrorMiddlemanMessage
from middleman_protocol.message import GolemMessageMiddlemanMessage


class TestInitMessagesFromMiddlemanProtocol:

    request_id = 99

    @pytest.mark.parametrize(('expected_middleman_message_type', 'payload_type', 'payload'), [
        (GolemMessageMiddlemanMessage,            PayloadType.GOLEM_MESSAGE,            Ping()),
        (ErrorMiddlemanMessage,                   PayloadType.ERROR,                    ('error_message', 'error.code')),
        (AuthenticationChallengeMiddlemanMessage, PayloadType.AUTHENTICATION_CHALLENGE, b'random_bytes'),
        (AuthenticationResponseMiddlemanMessage,  PayloadType.AUTHENTICATION_RESPONSE,  b'TODO'),
    ])  # pylint: disable=no-self-use
    def test_that_abstract_middleman_message_factory_with_different_payload_types_should_create_proper_middleman_message(
        self,
        expected_middleman_message_type,
        payload_type,
        payload,
    ):
        message = AbstractMiddlemanMessage.factory(
            payload_type,
            payload,
            self.request_id,
        )

        assertpy.assert_that(message).is_instance_of(expected_middleman_message_type)
        assertpy.assert_that(message.payload_type).is_equal_to(payload_type)

    def test_that_abstract_middleman_message_instantiation_should_raise_exception(self):
        with pytest.raises(NotImplementedError):
            AbstractMiddlemanMessage(
                Ping(),
                self.request_id,
            )


class TestSerializeMessagesFromMiddlemanProtocol:

    request_id = 99

    @pytest.mark.parametrize(('middleman_message_type', 'payload'), [
        (GolemMessageMiddlemanMessage,            Ping()),
        (ErrorMiddlemanMessage,                   ('error_message', 'error.code')),
        (AuthenticationChallengeMiddlemanMessage, b'random_bytes'),
        (AuthenticationResponseMiddlemanMessage,  b'TODO'),
    ])  # pylint: disable=no-self-use
    def test_that_serializing_and_deserializing_message_should_preserve_original_data(
        self,
        middleman_message_type,
        payload,
    ):
        middleman_message = middleman_message_type(payload, self.request_id)
        raw_message = middleman_message.serialize()
        deserialized_message = AbstractMiddlemanMessage.deserialize(raw_message)

        assert isinstance(deserialized_message, type(payload))
        assert deserialized_message == payload


class TestTransferMessagesFromMiddlemanProtocol:

    request_id = 99

    @pytest.mark.parametrize(('middleman_message_type', 'payload'), [
        (GolemMessageMiddlemanMessage,            Ping()),
        (ErrorMiddlemanMessage,                   ('error_message', 'error.code')),
        (AuthenticationChallengeMiddlemanMessage, b'random_bytes'),
        (AuthenticationResponseMiddlemanMessage,  b'TODO'),
    ])  # pylint: disable=no-self-use
    def test_that_sending_message_over_tcp_socket_should_preserve_original_data(
        self,
        middleman_message_type,
        payload,
    ):
        middleman_message = middleman_message_type(payload, self.request_id)
        raw_message = middleman_message.serialize()

        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as server_socket:
            with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as client_socket:
                server_socket.bind(('127.0.0.1', 8001))
                server_socket.listen(1)

                client_socket.connect(('127.0.0.1', 8001))

                connection, address = server_socket.accept()

                client_socket.send(raw_message)

                received_data = b''
                while received_data[len(received_data) - len(FRAME_SEPARATOR):] != FRAME_SEPARATOR:
                    received_data += connection.recv(1)

        deserialized_message = AbstractMiddlemanMessage.deserialize(received_data)

        assert isinstance(deserialized_message, type(payload))
        assert deserialized_message == payload
