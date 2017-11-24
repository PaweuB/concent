import json
import datetime
from base64                         import b64decode

from django.http                    import HttpResponse
from django.http                    import JsonResponse
from django.views.decorators.http   import require_POST
from django.utils                   import timezone
from django.conf                    import settings

from golem_messages.message         import MessageAckReportComputedTask
from golem_messages.message         import MessageForceReportComputedTask
from golem_messages.message         import MessageRejectReportComputedTask
from golem_messages.message         import MessageCannotComputeTask
from golem_messages.message         import MessageTaskFailure
from golem_messages.message         import MessageTaskToCompute
from golem_messages.message         import MessageVerdictReportComputedTask
from golem_messages.shortcuts       import dump
from golem_messages.shortcuts       import load

from utils.api_view                 import api_view
from utils.api_view                 import Http400
from .models                        import Message
from .models                        import ReceiveStatus


@api_view
@require_POST
def send(request, message):
    client_public_key = decode_client_public_key(request)
    current_time      = int(datetime.datetime.now().timestamp())
    if isinstance(message, MessageForceReportComputedTask):
        try:
            loaded_message = load(
                message.message_task_to_compute,
                settings.CONCENT_PRIVATE_KEY,
                client_public_key
            )
        except AttributeError:
            # TODO: Make error handling more granular when golem-messages adds starts raising more specific exceptions
            return JsonResponse(
                {'error': "Failed to decode ForceReportComputedTask. Message and/or key are malformed or don't match."},
                status = 400
            )

        validate_golem_message_task_to_compute(loaded_message)

        if Message.objects.filter(task_id = loaded_message.task_id).exists():
            raise Http400("{} is already being processed for this task.".format(message.__class__.__name__))

        if loaded_message.deadline < current_time:
            return MessageRejectReportComputedTask(
                reason                  = "deadline-exceeded",
                message_task_to_compute = message.message_task_to_compute,
            )

        golem_message, message_timestamp = store_message(
            type(message).__name__,
            loaded_message.task_id,
            request.body
        )
        store_receive_message_status(
            golem_message,
            message_timestamp,
        )
        return HttpResponse("", status = 202)

    elif isinstance(message, MessageAckReportComputedTask):
        loaded_message = load(
            message.message_task_to_compute,
            settings.CONCENT_PRIVATE_KEY,
            client_public_key
        )
        validate_golem_message_task_to_compute(loaded_message)

        if current_time <= loaded_message.deadline + settings.CONCENT_MESSAGING_TIME:
            force_task_to_compute   = Message.objects.filter(task_id = loaded_message.task_id, type = "MessageForceReportComputedTask")
            previous_ack_message    = Message.objects.filter(task_id = loaded_message.task_id, type = "MessageAckReportComputedTask")
            reject_message          = Message.objects.filter(task_id = loaded_message.task_id, type = "MessageRejectReportComputedTask")

            if not force_task_to_compute.exists():
                raise Http400("'ForceReportComputedTask' for this task has not been initiated yet. Can't accept your 'AckReportComputedTask'.")
            if previous_ack_message.exists() or reject_message.exists():
                raise Http400(
                    "Received AckReportComputedTask but RejectReportComputedTask "
                    "or another AckReportComputedTask for this task has already been submitted."
                )

            golem_message, message_timestamp = store_message(
                type(message).__name__,
                loaded_message.task_id,
                request.body
            )
            store_receive_message_status(
                golem_message,
                message_timestamp,
            )
            return HttpResponse("", status = 202)
        else:
            raise Http400("Time to acknowledge this task is already over.")

    elif isinstance(message, MessageRejectReportComputedTask):
        message_cannot_compute_task = load(
            message.message_cannot_compute_task,
            settings.CONCENT_PRIVATE_KEY,
            client_public_key
        )
        validate_golem_message_reject(message_cannot_compute_task)

        force_report_computed_task_message = Message.objects.filter(task_id = message_cannot_compute_task.task_id, type = "MessageForceReportComputedTask")

        if not force_report_computed_task_message.exists():
            raise Http400("'ForceReportComputedTask' for this task has not been initiated yet. Can't accept your 'RejectReportComputedTask'.")

        force_report_computed_task = load(
            force_report_computed_task_message.last().data.tobytes(),
            settings.CONCENT_PRIVATE_KEY,
            client_public_key,
        )
        assert hasattr(force_report_computed_task, 'message_task_to_compute')

        message_task_to_compute = load(
            force_report_computed_task.message_task_to_compute,
            settings.CONCENT_PRIVATE_KEY,
            client_public_key,
        )
        assert message_task_to_compute.task_id == message_cannot_compute_task.task_id
        if message_cannot_compute_task.reason == "deadline-exceeded":

            store_message(
                type(message).__name__,
                message_task_to_compute.task_id,
                request.body
            )
            return HttpResponse("", status = 202)

        if current_time <= message_task_to_compute.deadline + settings.CONCENT_MESSAGING_TIME:
            ack_message             = Message.objects.filter(task_id = message_cannot_compute_task.task_id, type = "MessageAckReportComputedTask")
            previous_reject_message = Message.objects.filter(task_id = message_cannot_compute_task.task_id, type = "MessageRejectReportComputedTask")

            if ack_message.exists() or previous_reject_message.exists():
                raise Http400("Received RejectReportComputedTask but AckReportComputedTask or another RejectReportComputedTask for this task has already been submitted.")

            golem_message, message_timestamp = store_message(
                type(message).__name__,
                message_task_to_compute.task_id,
                request.body
            )
            store_receive_message_status(
                golem_message,
                message_timestamp,
            )
            return HttpResponse("", status = 202)
        else:
            raise Http400("Time to acknowledge this task is already over.")
    else:
        if hasattr(message, 'TYPE'):
            raise Http400("This message type ({}) is either not supported or cannot be submitted to Concent.".format(message.TYPE))
        else:
            raise Http400("Unknown message type or not a Golem message.")


@api_view
@require_POST
def receive(request, _message):
    client_public_key               = decode_client_public_key(request)
    last_undelivered_message_status = ReceiveStatus.objects.filter(delivered = False).order_by('timestamp').last()
    if last_undelivered_message_status is None:
        last_delivered_message_status = ReceiveStatus.objects.all().order_by('timestamp').last()
        if last_delivered_message_status is None:
            return None

        if last_delivered_message_status.message.type == 'MessageForceReportComputedTask':
            message_force_report_task_from_database = last_delivered_message_status.message.data.tobytes()
            try:
                message_force_report_task = load(
                    message_force_report_task_from_database,
                    settings.CONCENT_PRIVATE_KEY,
                    client_public_key
                )
            except AttributeError:
                # TODO: Make error handling more granular when golem-messages adds starts raising more specific exceptions
                return JsonResponse(
                    {'error': "Failed to decode ForceReportComputedTask. Message and/or key are malformed or don't match."},
                    status = 400
                )

            try:
                message_task_to_compute = load(
                    message_force_report_task.message_task_to_compute,
                    settings.CONCENT_PRIVATE_KEY,
                    client_public_key
                )
            except AttributeError:
                # TODO: Make error handling more granular when golem-messages adds starts raising more specific exceptions
                return JsonResponse(
                    {'error': "Failed to decode AckReportComputedTask. Message and/or key are malformed or don't match."},
                    status = 400
                )

            message_ack_report_computed_task = MessageAckReportComputedTask(
                message_task_to_compute = message_force_report_task.message_task_to_compute
            )
            dumped_message_ack_report_computed_task = dump(
                message_ack_report_computed_task,
                settings.CONCENT_PRIVATE_KEY,
                client_public_key,
            )
            store_message(
                type(message_ack_report_computed_task).__name__,
                message_task_to_compute.task_id,
                dumped_message_ack_report_computed_task
            )

            return dumped_message_ack_report_computed_task

        return None

    current_time = int(datetime.datetime.now().timestamp())

    raw_message_data     = last_undelivered_message_status.message.data.tobytes()
    decoded_message_data = load(
        raw_message_data,
        settings.CONCENT_PRIVATE_KEY,
        client_public_key,
    )
    assert last_undelivered_message_status.message.type == type(decoded_message_data).__name__

    # Mark message as delivered
    if last_undelivered_message_status.message.type == "MessageForceReportComputedTask":
        message_task_to_compute_from_force = load(
            decoded_message_data.message_task_to_compute,
            settings.CONCENT_PRIVATE_KEY,
            client_public_key
        )

        if message_task_to_compute_from_force.deadline + settings.CONCENT_MESSAGING_TIME < current_time:
            last_undelivered_message_status.delivered = True
            last_undelivered_message_status.full_clean()
            last_undelivered_message_status.save()

            return dump(
                MessageAckReportComputedTask(message_task_to_compute = decoded_message_data.message_task_to_compute),
                settings.CONCENT_PRIVATE_KEY,
                client_public_key,
            )
    else:
        last_undelivered_message_status.delivered = True
        last_undelivered_message_status.full_clean()
        last_undelivered_message_status.save()

    if isinstance(decoded_message_data, MessageForceReportComputedTask):
        last_undelivered_message_status.delivered = True
        last_undelivered_message_status.full_clean()
        last_undelivered_message_status.save()
        return raw_message_data

    elif isinstance(decoded_message_data, MessageAckReportComputedTask):
        message_task_to_compute = load(
            decoded_message_data.message_task_to_compute,
            settings.CONCENT_PRIVATE_KEY,
            client_public_key
        )
        if current_time <= message_task_to_compute.deadline + 2 * settings.CONCENT_MESSAGING_TIME:
            return raw_message_data

        return None

    elif isinstance(decoded_message_data, MessageRejectReportComputedTask):
        message_cannot_compute_task = load(
            decoded_message_data.message_cannot_compute_task,
            settings.CONCENT_PRIVATE_KEY,
            client_public_key
        )
        message_to_compute = Message.objects.get(
            type    = 'MessageForceReportComputedTask',
            task_id = message_cannot_compute_task.task_id
        )
        raw_message_to_compute        = message_to_compute.data.tobytes()
        decoded_message_from_database = load(
            raw_message_to_compute,
            settings.CONCENT_PRIVATE_KEY,
            client_public_key,
        )
        message_task_to_compute = load(
            decoded_message_from_database.message_task_to_compute,
            settings.CONCENT_PRIVATE_KEY,
            client_public_key,
        )
        if current_time <= message_task_to_compute.deadline + 2 * settings.CONCENT_MESSAGING_TIME:
            if decoded_message_data.reason == "deadline-exceeded" or decoded_message_from_database.reason == "deadline-exceeded":
                message_ack_report_computed_task = MessageAckReportComputedTask(
                    timestamp               = current_time,
                    message_task_to_compute = decoded_message_from_database.message_task_to_compute,
                )
                return message_ack_report_computed_task
            return raw_message_data

        return None
    else:
        try:
            message_task_to_compute = load(
                decoded_message_data.message_task_to_compute,
                settings.CONCENT_PRIVATE_KEY,
                client_public_key
            )
        except AttributeError:
            # TODO: Make error handling more granular when golem-messages adds starts raising more specific exceptions
            return JsonResponse(
                {'error': "Failed to decode TaskToCompute. Message and/or key are malformed or don't match."},
                status = 400
            )

        if message_task_to_compute.deadline + settings.CONCENT_MESSAGING_TIME <= current_time <= message_task_to_compute.deadline + 2 * settings.CONCENT_MESSAGING_TIME:
            return MessageAckReportComputedTask(
                task_id                 = decoded_message_data.task_id,
                message_task_to_compute = decoded_message_data.message_task_to_compute,
                timestamp               = current_time,
            )
        if current_time <= message_task_to_compute.deadline + settings.CONCENT_MESSAGING_TIME:
            return decoded_message_data

        return None


@api_view
@require_POST
def receive_out_of_band(_request, _message):
    last_task_message = Message.objects.order_by('id').last()
    if last_task_message is None:
        return None

    raw_last_task_message     = last_task_message.data.tobytes()
    decoded_last_task_message = json.loads(raw_last_task_message.decode('utf-8'))
    current_time              = int(datetime.datetime.now().timestamp())
    message_verdict           = {
        "type":                               "MessageVerdictReportComputedTask",
        "timestamp":                          current_time,
        "message_force_report_computed_task": {},
        "message_ack_report_computed_task":   {
            "type":      "MessageAckReportComputedTask",
            "timestamp": current_time
        }
    }

    if decoded_last_task_message['type'] == "MessageForceReportComputedTask":
        task_deadline = decoded_last_task_message['message_task_to_compute']['deadline']
        if task_deadline + settings.CONCENT_MESSAGING_TIME <= current_time:
            message_verdict['message_force_report_computed_task'] = decoded_last_task_message
            return message_verdict

    if decoded_last_task_message['type'] == "MessageRejectReportComputedTask":
        if decoded_last_task_message['message_cannot_commpute_task']['reason'] == "deadline-exceeded":
            rejected_task_id                                      = decoded_last_task_message['message_cannot_commpute_task']['task_id']
            message_to_compute                                    = Message.objects.get(type = 'MessageForceReportComputedTask', task_id = rejected_task_id)
            raw_message_to_compute                                = message_to_compute.data.tobytes()
            decoded_message_to_compute                            = json.loads(raw_message_to_compute.decode('utf-8'))
            message_verdict['message_force_report_computed_task'] = decoded_message_to_compute
            return message_verdict

    return HttpResponse("", status = 204)


def validate_golem_message_task_to_compute(data):
    if not isinstance(data, MessageTaskToCompute):
        raise Http400("Expected MessageTaskToCompute.")

    if not isinstance(data.timestamp, float):
        raise Http400("Wrong type of message timestamp field. Not a float.")

    if data.task_id <= 0:
        raise Http400("task_id cannot be negative.")
    if not isinstance(data.deadline, int):
        raise Http400("Wrong type of deadline field.")


def validate_golem_message_reject(data):
    if not isinstance(data, MessageCannotComputeTask) and not isinstance(data, MessageTaskFailure):
        raise Http400("Expected MessageCannotComputeTask or MessageTaskFailure.")


def store_message(golem_message_type, task_id, raw_golem_message):
    message_timestamp = datetime.datetime.now(timezone.utc)
    golem_message = Message(
        type        = golem_message_type,
        timestamp   = message_timestamp,
        data        = raw_golem_message,
        task_id     = task_id
    )
    golem_message.full_clean()
    golem_message.save()
    return (golem_message, message_timestamp)


def store_receive_message_status(golem_message, message_timestamp):
    receive_message_status  = ReceiveStatus(
        message     = golem_message,
        timestamp   = message_timestamp
    )
    receive_message_status.full_clean()
    receive_message_status.save()


def decode_client_public_key(request):
    return b64decode(request.META['HTTP_CONCENT_CLIENT_PUBLIC_KEY'].encode('ascii'))
