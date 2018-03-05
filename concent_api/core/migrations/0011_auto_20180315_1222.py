# -*- coding: utf-8 -*-
# Generated by Django 1.11.9 on 2018-03-15 12:22
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
import utils.fields


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0010_auto_20180311_2101'),
    ]

    operations = [
        migrations.CreateModel(
            name='PaymentInfo',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('payment_ts', models.DateTimeField()),
                ('task_owner_key', utils.fields.Base64Field(db_column='task_owner_key', max_length=64)),
                ('provider_eth_account', utils.fields.Base64Field(db_column='provider_eth_account', max_length=64)),
                ('amount_paid', models.DecimalField(decimal_places=2, max_digits=10)),
                ('recipient_type', models.CharField(choices=[('Provider', 'provider'), ('Requestor', 'requestor')], max_length=32)),
                ('amount_pending', models.DecimalField(decimal_places=2, max_digits=10)),
            ],
        ),
        migrations.CreateModel(
            name='PendingResponse',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('response_type', models.CharField(choices=[('ForceReportComputedTask', 'ForceReportComputedTask'), ('ForceSubtaskResultsSettled', 'ForceSubtaskResultsSettled'), ('AckReportComputedTask', 'AckReportComputedTask'), ('RejectReportComputedTask', 'RejectReportComputedTask'), ('VerdictReportComputedTask', 'VerdictReportComputedTask'), ('ForceGetTaskResult', 'ForceGetTaskResult'), ('ForceGetTaskResultRejected', 'ForceGetTaskResultRejected'), ('ForceGetTaskResultFailed', 'ForceGetTaskResultFailed'), ('ForceGetTaskResultUpload', 'ForceGetTaskResultUpload'), ('ForceGetTaskResultDownload', 'ForceGetTaskResultDownload'), ('ForceSubtaskResults', 'ForceSubtaskResults'), ('SubtaskResultsSettled', 'SubtaskResultsSettled'), ('ForceSubtaskResultsResponse', 'ForceSubtaskResultsResponse'), ('SubtaskResultsRejected', 'SubtaskResultsRejected'), ('ForcePaymentCommitted', 'ForcePaymentCommitted')], max_length=32)),
                ('queue', models.CharField(choices=[('Receive', 'receive'), ('ReceiveOutOfBand', 'receive_out_of_band')], max_length=32)),
                ('delivered', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('client', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='core.Client')),
                ('subtask', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='core.Subtask')),
            ],
        ),
        migrations.AddField(
            model_name='paymentinfo',
            name='pending_response',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='payments', to='core.PendingResponse'),
        ),
    ]
