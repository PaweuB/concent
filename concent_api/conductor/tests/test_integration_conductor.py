import threading
from threading import Thread
import time
from unittest import TestCase

from django.core.management import BaseCommand
from django.db import connection, IntegrityError
from django.test import TransactionTestCase
import mock

from django.urls    import reverse

from common.helpers import get_current_utc_timestamp
from common.helpers import get_storage_result_file_path
from common.helpers import get_storage_source_file_path
from common.testing_helpers import generate_ecc_key_pair, generate_priv_and_pub_eth_account_key
from core.message_handlers import store_subtask
from core.models import Subtask
from core.tests.utils import ConcentIntegrationTestCase
from ..models       import BlenderSubtaskDefinition
from ..models       import UploadReport
from ..models       import VerificationRequest
from ..tasks        import blender_verification_request
from django.conf import settings


class ConductorVerificationIntegrationTest(ConcentIntegrationTestCase):

    multi_db = True

    def setUp(self):
        super().setUp()
        self.task_to_compute = self._get_deserialized_task_to_compute()
        self.compute_task_def = self.task_to_compute.compute_task_def
        self.source_package_path = get_storage_source_file_path(
            self.task_to_compute.subtask_id,
            self.task_to_compute.task_id,
        )
        self.result_package_path = get_storage_result_file_path(
            self.task_to_compute.subtask_id,
            self.task_to_compute.task_id,
        )
        self.report_computed_task = self._get_deserialized_report_computed_task(task_to_compute=self.task_to_compute)

        store_subtask(
            task_id=self.compute_task_def['task_id'],
            subtask_id=self.compute_task_def['subtask_id'],
            provider_public_key=self.PROVIDER_PUBLIC_KEY,
            requestor_public_key=self.REQUESTOR_PUBLIC_KEY,
            state=Subtask.SubtaskState.REPORTED,
            task_to_compute=self.report_computed_task.task_to_compute,
            report_computed_task=self.report_computed_task,
            next_deadline=None
        )

    def _prepare_verification_request_with_blender_subtask_definition(self):
        verification_request = VerificationRequest(
            subtask_id=self.compute_task_def['subtask_id'],
            source_package_path=self.source_package_path,
            result_package_path=self.result_package_path,
            verification_deadline=self._get_verification_deadline_as_datetime(
                get_current_utc_timestamp(),
                self.report_computed_task.task_to_compute,
            ),
        )
        verification_request.full_clean()
        verification_request.save()

        blender_subtask_definition = BlenderSubtaskDefinition(
            verification_request=verification_request,
            output_format=BlenderSubtaskDefinition.OutputFormat.JPG.name,  # pylint: disable=no-member
            scene_file=self.compute_task_def['extra_data']['scene_file'],
            blender_crop_script=self.compute_task_def['extra_data']['script_src'],
        )
        blender_subtask_definition.full_clean()
        blender_subtask_definition.save()

        return verification_request

    def test_conductor_should_return_404_when_file_path_parameter_not_matching_url_pattern_is_used(self):
        response = self.client.post(
            '/conductor/report-upload/',
            content_type = 'application/octet-stream',
        )

        self.assertEqual(response.status_code, 404)

    def test_conductor_should_create_upload_report(self):
        response = self.client.post(
            reverse(
                'conductor:report-upload',
                kwargs={
                    'file_path': self.source_package_path
                }
            ),
            content_type = 'application/octet-stream',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(UploadReport.objects.count(), 1)

        upload_report = UploadReport.objects.first()
        self.assertEqual(upload_report.path, self.source_package_path)
        self.assertEqual(upload_report.verification_request, None)

    def test_conductor_should_create_upload_report_and_link_to_related_verification_request(self):
        verification_request = self._prepare_verification_request_with_blender_subtask_definition()

        response = self.client.post(
            reverse(
                'conductor:report-upload',
                kwargs={
                    'file_path': self.source_package_path
                }
            ),
            content_type='application/octet-stream',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(UploadReport.objects.count(), 1)

        upload_report = UploadReport.objects.first()
        self.assertEqual(upload_report.path, self.source_package_path)
        self.assertEqual(upload_report.verification_request, verification_request)

    def test_conductor_should_create_upload_report_and_do_not_link_to_unrelated_verification_request(self):
        verification_request = VerificationRequest(
            subtask_id='1',
            source_package_path='blender/source/bad/bad.bad.zip',
            result_package_path='blender/result/bad/bad.bad.zip',
            verification_deadline=self._get_verification_deadline_as_datetime(
                get_current_utc_timestamp(),
                self.report_computed_task.task_to_compute,
            ),
        )
        verification_request.full_clean()
        verification_request.save()

        response = self.client.post(
            reverse(
                'conductor:report-upload',
                kwargs={
                    'file_path': self.source_package_path
                }
            ),
            content_type='application/octet-stream',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(UploadReport.objects.count(), 1)

        upload_report = UploadReport.objects.first()
        self.assertEqual(upload_report.path, self.source_package_path)
        self.assertEqual(upload_report.verification_request, None)

    def test_conductor_should_schedule_verification_order_task_if_all_related_upload_requests_have_reports(self):
        verification_request = self._prepare_verification_request_with_blender_subtask_definition()

        upload_report = UploadReport(
            path=verification_request.result_package_path,
            verification_request=verification_request,
        )
        upload_report.full_clean()
        upload_report.save()

        with mock.patch('conductor.views.upload_finished.delay') as mock_task:
            response = self.client.post(
                reverse(
                    'conductor:report-upload',
                    kwargs={
                        'file_path': self.source_package_path
                    }
                ),
                content_type='application/octet-stream',
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(UploadReport.objects.count(), 2)

        upload_report = UploadReport.objects.last()
        self.assertEqual(upload_report.path, self.source_package_path)

        mock_task.assert_called_once_with(self.compute_task_def['subtask_id'])

        verification_request.refresh_from_db()
        self.assertTrue(verification_request.upload_finished)

    def test_conductor_should_not_schedule_verification_order_task_if_it_was_already_scheduled_for_given_verification(self):
        verification_request = self._prepare_verification_request_with_blender_subtask_definition()

        upload_report = UploadReport(
            path=verification_request.result_package_path,
            verification_request=verification_request,
        )
        upload_report.full_clean()
        upload_report.save()

        with mock.patch('conductor.views.upload_finished.delay') as mock_task:
            response = self.client.post(
                reverse(
                    'conductor:report-upload',
                    kwargs={
                        'file_path': self.source_package_path
                    }
                ),
                content_type='application/octet-stream',
            )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(UploadReport.objects.count(), 2)

            mock_task.assert_called_once_with(self.compute_task_def['subtask_id'])

            verification_request.refresh_from_db()
            self.assertTrue(verification_request.upload_finished)

            response = self.client.post(
                reverse(
                    'conductor:report-upload',
                    kwargs={
                        'file_path': self.source_package_path
                    }
                ),
                content_type='application/octet-stream',
            )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(UploadReport.objects.count(), 3)
            self.assertEqual(mock_task.call_count, 1)

    def test_that_conductor_should_schedule_verification_order_task_if_uploaded_file_path_was_not_existing_before_and_other_requirements_are_met(self):
        verification_request = self._prepare_verification_request_with_blender_subtask_definition()

        upload_report = UploadReport(
            path=verification_request.result_package_path,
            verification_request=verification_request,
        )
        upload_report.full_clean()
        upload_report.save()

        with mock.patch('conductor.views.upload_finished.delay') as mock_task:
            response = self.client.post(
                reverse(
                    'conductor:report-upload',
                    kwargs={
                        'file_path': self.result_package_path
                    }
                ),
                content_type='application/octet-stream',
            )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(UploadReport.objects.count(), 2)

            mock_task.assert_not_called()

            verification_request.refresh_from_db()
            self.assertFalse(verification_request.upload_finished)

            response = self.client.post(
                reverse(
                    'conductor:report-upload',
                    kwargs={
                        'file_path': self.source_package_path
                    }
                ),
                content_type='application/octet-stream',
            )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(UploadReport.objects.count(), 3)

            mock_task.assert_called_once_with(self.compute_task_def['subtask_id'])

            verification_request.refresh_from_db()
            self.assertTrue(verification_request.upload_finished)

    def test_that_conductor_should_not_schedule_verification_order_task_if_same_file_was_uploaded_again(self):
        verification_request = self._prepare_verification_request_with_blender_subtask_definition()

        upload_report = UploadReport(
            path=verification_request.result_package_path,
            verification_request=verification_request,
        )
        upload_report.full_clean()
        upload_report.save()

        with mock.patch('conductor.views.upload_finished.delay') as mock_task:
            response = self.client.post(
                reverse(
                    'conductor:report-upload',
                    kwargs={
                        'file_path': self.result_package_path
                    }
                ),
                content_type='application/octet-stream',
            )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(UploadReport.objects.count(), 2)

            mock_task.assert_not_called()

            verification_request.refresh_from_db()
            self.assertFalse(verification_request.upload_finished)

    def test_blender_verification_request_task_should_create_verification_request_and_blender_subtask_definition(self):
        blender_verification_request(
            frames=self.compute_task_def['extra_data']['frames'],
            subtask_id=self.compute_task_def['subtask_id'],
            source_package_path=self.source_package_path,
            result_package_path=self.result_package_path,
            output_format=BlenderSubtaskDefinition.OutputFormat.JPG.name,  # pylint: disable=no-member
            scene_file = self.compute_task_def['extra_data']['scene_file'],
            verification_deadline=self._get_verification_deadline_as_timestamp(
                get_current_utc_timestamp(),
                self.report_computed_task.task_to_compute,
            ),
            blender_crop_script=self.compute_task_def['extra_data']['script_src'],
        )

        self.assertEqual(VerificationRequest.objects.count(), 1)

        verification_request = VerificationRequest.objects.first()
        self.assertEqual(verification_request.subtask_id,  self.compute_task_def['subtask_id'])
        self.assertEqual(verification_request.source_package_path, self.source_package_path)
        self.assertEqual(verification_request.result_package_path, self.result_package_path)
        self.assertEqual(verification_request.blender_subtask_definition.output_format, BlenderSubtaskDefinition.OutputFormat.JPG.name)  # pylint: disable=no-member
        self.assertEqual(verification_request.blender_subtask_definition.scene_file, self.compute_task_def['extra_data']['scene_file'])

    def test_blender_verification_request_task_should_not_link_upload_requests_to_unrelated_upload_reports(self):
        upload_report = UploadReport(
            path='blender/scene/bad/bad.bad.zip',
        )
        upload_report.full_clean()
        upload_report.save()

        blender_verification_request(
            frames=self.compute_task_def['extra_data']['frames'],
            subtask_id=self.compute_task_def['subtask_id'],
            source_package_path=self.source_package_path,
            result_package_path=self.result_package_path,
            output_format=BlenderSubtaskDefinition.OutputFormat.JPG.name,  # pylint: disable=no-member
            scene_file = self.compute_task_def['extra_data']['scene_file'],
            verification_deadline=self._get_verification_deadline_as_timestamp(
                get_current_utc_timestamp(),
                self.report_computed_task.task_to_compute,
            ),
            blender_crop_script=self.compute_task_def['extra_data']['script_src'],
        )

        self.assertEqual(VerificationRequest.objects.count(), 1)

        verification_request = VerificationRequest.objects.first()
        self.assertEqual(verification_request.upload_reports.count(), 0)
        self.assertFalse(verification_request.upload_reports.filter(path=self.source_package_path).exists())

    def test_blender_verification_request_task_should_schedule_upload_finished_task_if_all_related_upload_requests_have_reports(self):
        upload_report = UploadReport(
            path=self.source_package_path,
        )
        upload_report.full_clean()
        upload_report.save()

        upload_report = UploadReport(
            path=self.result_package_path,
        )
        upload_report.full_clean()
        upload_report.save()

        with mock.patch('conductor.tasks.tasks.upload_finished.delay') as mock_task:
            blender_verification_request(
                frames=self.compute_task_def['extra_data']['frames'],
                subtask_id=self.compute_task_def['subtask_id'],
                source_package_path=self.source_package_path,
                result_package_path=self.result_package_path,
                output_format=BlenderSubtaskDefinition.OutputFormat.JPG.name,  # pylint: disable=no-member
                scene_file = self.compute_task_def['extra_data']['scene_file'],
                verification_deadline=self._get_verification_deadline_as_timestamp(
                    get_current_utc_timestamp(),
                    self.report_computed_task.task_to_compute,
                ),
                blender_crop_script=self.compute_task_def['extra_data']['script_src'],
            )

        mock_task.assert_called_with(self.compute_task_def['subtask_id'])























class BlenderVerificationRequestParallelTest(ConcentIntegrationTestCase):

    def __init__(self):
        super().__init__()

        (self.PROVIDER_PRIVATE_KEY, self.PROVIDER_PUBLIC_KEY) = generate_ecc_key_pair()
        (self.REQUESTOR_PRIVATE_KEY, self.REQUESTOR_PUBLIC_KEY) = generate_ecc_key_pair()
        (self.PROVIDER_PRIV_ETH_KEY, self.PROVIDER_PUB_ETH_KEY) = generate_priv_and_pub_eth_account_key()
        (self.REQUESTOR_PRIV_ETH_KEY, self.REQUESTOR_PUB_ETH_KEY) = generate_priv_and_pub_eth_account_key()

        self.task_to_compute = self._get_deserialized_task_to_compute()
        self.compute_task_def = self.task_to_compute.compute_task_def
        self.source_package_path = get_storage_source_file_path(
            self.task_to_compute.subtask_id,
            self.task_to_compute.task_id,
        )
        self.result_package_path = get_storage_result_file_path(
            self.task_to_compute.subtask_id,
            self.task_to_compute.task_id,
        )
        self.report_computed_task = self._get_deserialized_report_computed_task(task_to_compute=self.task_to_compute)

        store_subtask(
            task_id=self.compute_task_def['task_id'],
            subtask_id=self.compute_task_def['subtask_id'],
            provider_public_key=self.PROVIDER_PUBLIC_KEY,
            requestor_public_key=self.REQUESTOR_PUBLIC_KEY,
            state=Subtask.SubtaskState.REPORTED,
            task_to_compute=self.report_computed_task.task_to_compute,
            report_computed_task=self.report_computed_task,
            next_deadline=None
        )

    def run_blender_verification_request(self):
        blender_verification_request(
            frames=self.compute_task_def['extra_data']['frames'],
            subtask_id=self.compute_task_def['subtask_id'],
            source_package_path=self.source_package_path,
            result_package_path=self.result_package_path,
            output_format=BlenderSubtaskDefinition.OutputFormat.JPG.name,  # pylint: disable=no-member
            scene_file=self.compute_task_def['extra_data']['scene_file'],
            verification_deadline=self._get_verification_deadline_as_timestamp(
                get_current_utc_timestamp(),
                self.report_computed_task.task_to_compute,
            ),
            blender_crop_script=self.compute_task_def['extra_data']['script_src'],
        )


class DatabaseHandler(BaseCommand):   # pylint: disable=abstract-method

    def deactivate_communication_with_database(self):  # pylint: disable=abstract-method, no-self-use
        cursor = connection.cursor()
        database_name = f"{settings.DATABASES['control']['NAME']}"
        database_name = f"{settings.DATABASES['storage']['NAME']}"

        cursor.execute(
            "SELECT pg_terminate_backend(pg_stat_activity.pid) FROM pg_stat_activity "
            "WHERE pg_stat_activity.datname = %s AND pid <> pg_backend_pid();", [database_name])






class TestEnsureRetryOfLockedCalls(ConcentIntegrationTestCase):

    def setUp(self):
        super().setUp()
        self.hepler = BlenderVerificationRequestParallelTest()

    def test_that_ensure_retry_of_locked_calls_should_handle_multiprocessing_calls(self):
        # self.hepler.run_blender_verification_request()


        for i in range(3):  # pylint: disable=unused-variable
            t = Thread(target=self.hepler.run_blender_verification_request, args=())
            t.start()


        # with self.assertRaises(IntegrityError)

        time.sleep(10)
        # self.assertEqual(threading.active_count(), 1)
        database_handler = DatabaseHandler()
        database_handler.deactivate_communication_with_database()


