# -*- coding: utf-8 -*-
# Generated by Django 1.11.13 on 2018-07-19 12:41
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0006_auto_20180719_1213'),
    ]

    operations = [
        migrations.AlterField(
            model_name='subtask',
            name='computation_deadline',
            field=models.DateTimeField(),
        ),
        migrations.AlterField(
            model_name='subtask',
            name='result_package_size',
            field=models.IntegerField(),
        ),
    ]
