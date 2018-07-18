#!/usr/bin/env python3

import os
import sys
import time

from freezegun import freeze_time

from golem_messages import message
from golem_messages.utils import encode_hex

from common.helpers import get_current_utc_timestamp
from common.helpers import parse_timestamp_to_utc_datetime
from common.helpers import sign_message

from api_testing_common import api_request
from api_testing_common import count_fails
from api_testing_common import create_client_auth_message
from api_testing_common import create_signed_task_to_compute
from api_testing_common import get_task_id_and_subtask_id
from api_testing_common import run_tests
from api_testing_common import PROVIDER_PRIVATE_KEY
from api_testing_common import REQUESTOR_PRIVATE_KEY
from api_testing_common import REQUESTOR_PUBLIC_KEY
from api_testing_common import timestamp_to_isoformat

import requests

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "concent_api.settings")

"""
Average time for 2 blocks
Constans needed for test to get last 2 blocks
"""
AVERAGE_TIME_FOR_TWO_BLOCKS = 30


def force_payment(timestamp = None, subtask_results_accepted_list = None):
    with freeze_time(timestamp):
        return message.concents.ForcePayment(
            subtask_results_accepted_list = subtask_results_accepted_list
        )


def subtask_results_accepted(timestamp = None, payment_ts = None, task_to_compute = None):
    with freeze_time(timestamp):
        return sign_message(
            message.tasks.SubtaskResultsAccepted(
                payment_ts=payment_ts,
                task_to_compute=task_to_compute
            ),
            REQUESTOR_PRIVATE_KEY,
        )


@count_fails
def test_case_2d_send_correct_force_payment(cluster_consts, cluster_url, test_id):
    # Test CASE 2D - Send correct ForcePayment
    current_time = get_current_utc_timestamp()
    (task_id, subtask_id) = get_task_id_and_subtask_id(test_id, '2D')
    data = 'client_test_string'
    # correct_force_payment.sig = None
    api_request(
        cluster_url,
        'multiprocess_test_view',
        PROVIDER_PRIVATE_KEY,
        CONCENT_PUBLIC_KEY,
        data=data,

        headers={
            'Content-Type': 'application/octet-stream',
        },
        expected_status=200,
        expected_message_type=message.concents.ForcePaymentCommitted.TYPE,
        expected_content_type='application/octet-stream',
    )
    # time.sleep(5)
    # api_request(
    #     cluster_url,
    #     'receive-out-of-band',
    #     REQUESTOR_PRIVATE_KEY,
    #     CONCENT_PUBLIC_KEY,
    #     create_client_auth_message(REQUESTOR_PRIVATE_KEY, REQUESTOR_PUBLIC_KEY, CONCENT_PUBLIC_KEY),
    #     headers={
    #         'Content-Type': 'application/octet-stream',
    #     },
    #     expected_status=200,
    #     expected_message_type=message.concents.ForcePaymentCommitted.TYPE,
    #     expected_content_type='application/octet-stream',
    # )



if __name__ == '__main__':
    try:
        from concent_api.settings import CONCENT_PUBLIC_KEY
        from core.constants import GOLEM_PUBLIC_KEY_LENGTH
        run_tests(globals())
    except requests.exceptions.ConnectionError as exception:
        print("\nERROR: Failed connect to the server.\n", file = sys.stderr)
        sys.exit(str(exception))
