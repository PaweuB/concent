from middleman_protocol.constants import PayloadType
from middleman_protocol.registry import PAYLOAD_TYPE_TO_MIDDLEMAN_MESSAGE_CLASS


def create_middleman_protocol_message(payload_type, payload, request_id):
    assert payload_type in PayloadType
    assert payload_type in PAYLOAD_TYPE_TO_MIDDLEMAN_MESSAGE_CLASS

    return PAYLOAD_TYPE_TO_MIDDLEMAN_MESSAGE_CLASS[payload_type](payload, request_id)
