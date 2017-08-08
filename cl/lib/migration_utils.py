# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.core.management import call_command
from django.core.serializers import base, python


def load_migration_fixture(apps, schema_editor, fixture, app_label):
    """Load a fixture during a migration.
    
    This is a rather un-fun utility to load a fixture during a migration. It 
    works by monkey patching the normal fixture code with code that can load 
    fixtures at a certain point in a migration, ie, not using the current state
    of the models. 
    
    For more information, see this answer:
    
    https://stackoverflow.com/a/39743581/64911
        
    :param apps: Apps at the state of the migration.
    :param schema_editor: The schema at the time of the migration.
    :param fixture: A path to the fixture to be loaded.
    :param app_label: The app label the fixture should be loaded into.
    :return: None
    """
    # Save the old _get_model() function
    old_get_model = python._get_model

    # Define new _get_model() function here, which utilizes the apps argument to
    # get the historical version of a model. This piece of code is directly
    # stolen from django.core.serializers.python._get_model, unchanged.
    def _get_model(model_identifier):
        try:
            return apps.get_model(model_identifier)
        except (LookupError, TypeError):
            raise base.DeserializationError(
                "Invalid model identifier: '%s'" % model_identifier)

    # Replace the _get_model() function on the module so loaddata can utilize it
    python._get_model = _get_model

    try:
        # Call loaddata command
        call_command('loaddata', fixture, app_label=app_label)
    finally:
        # Restore old _get_model() function
        python._get_model = old_get_model
