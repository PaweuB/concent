from django.http import JsonResponse
from golem_messages.message import FileTransferToken

from utils import logging


def gatekeeper_access_denied_response(
    message: str,
    operation: FileTransferToken.Operation,
    error_code=None,
    path=None,
    subtask_id=None,
    client_key=None
):
    data = {
        'message': message,
        'error_code': error_code.value,
        'path_to_file': path,
        'subtask_id': subtask_id,
        'client_key': client_key,
    }

    logging.log_operation_validation_failed(
        operation.capitalize(),
        message,
        error_code.value,
        path,
        subtask_id,
        client_key
    )

    # The status code here must be always 401 because auth_request module in nginx can only handle HTTP 401.
    response = JsonResponse(data, status=401)
    response["WWW-Authenticate"] = 'Golem realm="Concent Storage"'
    return response
