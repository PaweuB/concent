from functools import wraps
import os
import time
#
# from celery import shared_task
from celery import shared_task
import django
# from django.db import IntegrityError
#
# from common.constants import ErrorCode
# from core.exceptions import Http400
from django.db import transaction, DatabaseError
#
from common.constants import ErrorCode


# from core.models import Subtask
from common.decorators import log_task_errors
from core.models import Subtask


# def get_subtask_id(*args, **kwargs) -> str:
#     if 'subtask_id' in kwargs.keys():
#         return kwargs.get('subtask_id')
#     else:
#         return args[0]


def ensure_retry_of_locked_calls(func):
    """
    Important! - if you use this decorator on function, ensure that subtask_id is first argument in this function
    declaration. This way it can be called both as positional and keyword arguments.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        repeat_handler = RepeatHandler()
        print('wrapper')

        should_repeat = True
        result = None

        while should_repeat:
            try:
                result = func(*args, **kwargs)
                should_repeat = False
            except DatabaseError:
                repeat_handler.is_max_number_of_tries_exceeded()

        return result

    return wrapper


class RepeatHandler:

    def __init__(self):
        self.max_number_of_short_retries = 10
        self.max_number_of_long_retries = 10
        self.current_number_of_retries = 0
        self.wait_time_in_sec_short = 0.05
        self.wait_time_in_sec_long = 1

    def is_max_number_of_tries_exceeded(self):
        if self.current_number_of_retries < self.max_number_of_short_retries:
            self.current_number_of_retries = self.current_number_of_retries + 1
            time.sleep(self.wait_time_in_sec_short)

        elif self.current_number_of_retries - self.max_number_of_short_retries < self.max_number_of_long_retries:
            self.current_number_of_retries = self.current_number_of_retries + 1
            time.sleep(self.wait_time_in_sec_long)
        else:
            raise DatabaseError("Maximum number of retries of function updating Subtask extended",
                                error_code=ErrorCode.CONCENT_APPLICATION_CRASH
                                )
#
#
