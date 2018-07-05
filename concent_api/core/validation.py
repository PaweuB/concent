from logging import getLogger
from typing import List
from typing import Union

from golem_messages import message
from golem_messages.exceptions import MessageError

from common.constants import ErrorCode
from common.logging import log_error_message
from common.validations import validate_secure_hash_algorithm
from core.constants import ETHEREUM_ADDRESS_LENGTH
from core.constants import GOLEM_PUBLIC_KEY_HEX_LENGTH
from core.constants import GOLEM_PUBLIC_KEY_LENGTH
from core.constants import MESSAGE_TASK_ID_MAX_LENGTH
from core.constants import VALID_ID_REGEX
from core.exceptions import FrameNumberValidationError
from core.exceptions import GolemMessageValidationError
from core.exceptions import Http400
from core.utils import hex_to_bytes_convert


logger = getLogger(__name__)


def validate_int_value(value):
    """
    Checks if value is an integer. If not, tries to cast it to an integer.
    Then checks if value is non-negative.

    """
    if not isinstance(value, int):
        try:
            value = int(value)
        except (ValueError, TypeError):
            raise Http400(
                "Wrong type, expected a value that can be converted to an integer.",
                error_code=ErrorCode.MESSAGE_VALUE_NOT_INTEGER,
            )
    if value < 0:
        raise Http400(
            "Wrong type, expected non-negative integer but negative integer provided.",
            error_code=ErrorCode.MESSAGE_VALUE_WRONG_TYPE,
        )


def validate_id_value(value, field_name):
    if not isinstance(value, str):
        raise Http400(
            "{} must be string.".format(field_name),
            error_code=ErrorCode.MESSAGE_VALUE_WRONG_TYPE,
        )

    if value == '':
        raise Http400(
            "{} cannot be blank.".format(field_name),
            error_code=ErrorCode.MESSAGE_VALUE_BLANK,
        )

    if len(value) > MESSAGE_TASK_ID_MAX_LENGTH:
        raise Http400(
            "{} cannot be longer than {} chars.".format(field_name, MESSAGE_TASK_ID_MAX_LENGTH),
            error_code=ErrorCode.MESSAGE_VALUE_WRONG_LENGTH,
        )

    if VALID_ID_REGEX.fullmatch(value) is None:
        raise Http400(
            f'{field_name} must contain only alphanumeric chars.',
            error_code=ErrorCode.MESSAGE_VALUE_NOT_ALLOWED,
        )


def validate_hex_public_key(value, field_name):
    validate_key_with_desired_parameters(field_name, value, str, GOLEM_PUBLIC_KEY_HEX_LENGTH)


def validate_bytes_public_key(value, field_name):
    validate_key_with_desired_parameters(field_name, value, bytes, GOLEM_PUBLIC_KEY_LENGTH)


def validate_key_with_desired_parameters(
        key_name: str,
        key_value: Union[bytes, str],
        expected_type,
        expected_length: int
):

    if not isinstance(key_value, expected_type):
        raise Http400(
            f"{key_name} must be {expected_type.__name__}.",
            error_code=ErrorCode.MESSAGE_VALUE_WRONG_TYPE,
        )

    if len(key_value) != expected_length:
        raise Http400(
            "The length of {} must be exactly {} characters.".format(key_name, expected_length),
            error_code=ErrorCode.MESSAGE_VALUE_WRONG_LENGTH,
        )


def validate_task_to_compute(task_to_compute: message.TaskToCompute):
    if not isinstance(task_to_compute, message.TaskToCompute):
        raise Http400(
            f"Expected TaskToCompute instead of {type(task_to_compute).__name__}.",
            error_code=ErrorCode.MESSAGE_INVALID,
        )

    if any(map(lambda x: x is None, [getattr(task_to_compute, attribute) for attribute in [
        'compute_task_def',
        'provider_public_key',
        'requestor_public_key'
    ]])):
        raise Http400(
            "Invalid TaskToCompute",
            error_code=ErrorCode.MESSAGE_WRONG_FIELDS,
        )

    validate_int_value(task_to_compute.compute_task_def['deadline'])

    validate_id_value(task_to_compute.compute_task_def['task_id'], 'task_id')
    validate_id_value(task_to_compute.compute_task_def['subtask_id'], 'subtask_id')

    validate_hex_public_key(task_to_compute.provider_public_key, 'provider_public_key')
    validate_hex_public_key(task_to_compute.requestor_public_key, 'requestor_public_key')
    validate_secure_hash_algorithm(task_to_compute.package_hash)
    validate_subtask_price_task_to_compute(task_to_compute)
    validate_frames(task_to_compute.compute_task_def['extra_data']['frames'])


def validate_report_computed_task_time_window(report_computed_task):
    assert isinstance(report_computed_task, message.ReportComputedTask)

    if report_computed_task.timestamp < report_computed_task.task_to_compute.timestamp:
        raise Http400(
            "ReportComputedTask timestamp is older then nested TaskToCompute.",
            error_code=ErrorCode.MESSAGE_TIMESTAMP_TOO_OLD,
        )


def validate_all_messages_identical(golem_messages_list: List[message.Message]):
    assert isinstance(golem_messages_list, list)
    assert len(golem_messages_list) >= 1
    assert all(isinstance(golem_message, message.Message) for golem_message in golem_messages_list)
    assert len(set(type(golem_message) for golem_message in golem_messages_list)) == 1

    base_golem_message = golem_messages_list[0]

    for i, golem_message in enumerate(golem_messages_list[1:], start=1):
        for slot in base_golem_message.__slots__:
            if getattr(base_golem_message, slot) != getattr(golem_message, slot):
                raise Http400(
                    '{} messages are not identical. '
                    'There is a difference between messages with index 0 on passed list and with index {}'
                    'The difference is on field {}: {} is not equal {}'.format(
                        type(base_golem_message).__name__,
                        i,
                        slot,
                        getattr(base_golem_message, slot),
                        getattr(golem_message, slot),
                    ),
                    error_code=ErrorCode.MESSAGES_NOT_IDENTICAL,
                )


def is_golem_message_signed_with_key(
    public_key: bytes,
    golem_message: message.base.Message,
) -> bool:
    """
    Validates if given Golem message is signed with given public key.

    :param golem_message: Instance of golem_messages.base.Message object.
    :param public_key: Client public key in bytes.
    :return: True if given Golem message is signed with given public key, otherwise False.
    """
    assert isinstance(golem_message, message.base.Message)

    validate_bytes_public_key(public_key, 'public_key')

    try:
        is_valid = golem_message.verify_signature(public_key)
    except MessageError as exception:
        is_valid = False
        log_error_message(
            logger,
            f'There was an exception when validating if golem_message {golem_message.__class__.__name__} is signed '
            f'with public key {public_key}, exception: {exception}.'
        )

    return is_valid


def validate_golem_message_subtask_results_rejected(subtask_results_rejected: message.tasks.SubtaskResultsRejected):
    if not isinstance(subtask_results_rejected,  message.tasks.SubtaskResultsRejected):
        raise Http400(
            "subtask_results_rejected should be of type:  SubtaskResultsRejected",
            error_code=ErrorCode.MESSAGE_INVALID,
        )
    validate_task_to_compute(subtask_results_rejected.report_computed_task.task_to_compute)


def validate_subtask_price_task_to_compute(task_to_compute: message.tasks.TaskToCompute):
    if not isinstance(task_to_compute.price, int):
        raise Http400(
            "Price must be a integer",
            error_code=ErrorCode.MESSAGE_VALUE_NOT_INTEGER,
        )
    if task_to_compute.price < 0:
        raise Http400(
            "Price cannot be a negative value",
            error_code=ErrorCode.MESSAGE_VALUE_NEGATIVE,
        )


def validate_ethereum_addresses(requestor_ethereum_address, provider_ethereum_address):
    if not isinstance(requestor_ethereum_address, str):
        raise Http400(
            "Requestor's ethereum address must be a string",
            error_code=ErrorCode.MESSAGE_VALUE_NOT_STRING,
        )

    if not isinstance(provider_ethereum_address, str):
        raise Http400(
            "Provider's ethereum address must be a string",
            error_code=ErrorCode.MESSAGE_VALUE_NOT_STRING,
        )

    if not len(requestor_ethereum_address) == ETHEREUM_ADDRESS_LENGTH:
        raise Http400(
            f"Requestor's ethereum address must contains exactly {ETHEREUM_ADDRESS_LENGTH} characters ",
            error_code=ErrorCode.MESSAGE_VALUE_WRONG_LENGTH,
        )

    if not len(provider_ethereum_address) == ETHEREUM_ADDRESS_LENGTH:
        raise Http400(
            f"Provider's ethereum address must contains exactly {ETHEREUM_ADDRESS_LENGTH} characters ",
            error_code=ErrorCode.MESSAGE_VALUE_WRONG_LENGTH,
        )


def get_validated_client_public_key_from_client_message(golem_message: message.base.Message):
    if isinstance(golem_message, message.concents.ForcePayment):
        if (
            isinstance(golem_message.subtask_results_accepted_list, list) and
            len(golem_message.subtask_results_accepted_list) > 0
        ):
            task_to_compute = golem_message.subtask_results_accepted_list[0].task_to_compute
        else:
            raise Http400(
                "subtask_results_accepted_list must be a list type and contains at least one message",
                error_code=ErrorCode.MESSAGE_VALUE_WRONG_LENGTH,
            )

    elif isinstance(golem_message, message.tasks.TaskMessage):
        if not golem_message.is_valid():
            raise GolemMessageValidationError(
                "Golem message invalid",
                error_code=ErrorCode.MESSAGE_INVALID
            )
        task_to_compute = golem_message.task_to_compute
    else:
        raise Http400(
            "Unknown message type",
            error_code=ErrorCode.MESSAGE_UNKNOWN,
        )

    if task_to_compute is not None:
        if isinstance(golem_message, (
            message.ForceReportComputedTask,
            message.concents.ForceSubtaskResults,
            message.concents.ForcePayment,
            message.concents.SubtaskResultsVerify,
        )):
            client_public_key = task_to_compute.provider_public_key
            validate_hex_public_key(client_public_key, 'provider_public_key')
        elif isinstance(golem_message, (
            message.AckReportComputedTask,
            message.RejectReportComputedTask,
            message.concents.ForceGetTaskResult,
            message.concents.ForceSubtaskResultsResponse,
        )):
            client_public_key = task_to_compute.requestor_public_key
            validate_hex_public_key(client_public_key, 'requestor_public_key')
        else:
            raise Http400(
                "Unknown message type",
                error_code=ErrorCode.MESSAGE_UNKNOWN,
            )

        return hex_to_bytes_convert(client_public_key)

    return None


def validate_frames(frames_list: List[int]):
    if not isinstance(frames_list, list) or not len(frames_list) > 0:
        raise FrameNumberValidationError(
            'TaskToCompute must contain list of frames.',
            ErrorCode.MESSAGE_FRAME_WRONG_TYPE
        )

    for frame in frames_list:
        if not isinstance(frame, int):
            raise FrameNumberValidationError(
                'Frame must be integer',
                ErrorCode.MESSAGE_FRAME_VALUE_NOT_POSITIVE_INTEGER
            )

        if not frame > 0:
            raise FrameNumberValidationError(
                'Frame number must be grater than 0',
                ErrorCode.MESSAGE_FRAME_VALUE_NOT_POSITIVE_INTEGER
            )
