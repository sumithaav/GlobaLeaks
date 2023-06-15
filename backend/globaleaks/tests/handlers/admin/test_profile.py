# -*- coding: utf-8 -*-
import os

from twisted.internet.defer import inlineCallbacks

from globaleaks import models
from globaleaks.handlers.admin import profile
from globaleaks.models import Profile
from globaleaks.orm import transact
from globaleaks.rest import errors
from globaleaks.tests import helpers
from globaleaks.utils.fs import read_json_file


class TestProfilesCollection(helpers.TestHandlerWithPopulatedDB):
    _handler = profile.ProfileCollection


    @inlineCallbacks
    def test_post_invalid_json(self):
        self.test_data_dir = os.path.join(helpers.DATA_DIR, 'profiles')

        invalid_test_cases = [
            ('invalid.json', errors.InputValidationError)
        ]

        for fname, err in invalid_test_cases:
            new_p = read_json_file(os.path.join(self.test_data_dir, fname))
            handler = self.request(new_p, role='admin')
            handler.request.language = None
            try:
                yield self.assertFailure(handler.post(), err)
            except errors.InputValidationError as e:
                yield self.assertEqual(type(e), err)


    @inlineCallbacks
    def test_post_valid_json(self):
        self.test_data_dir = os.path.join(helpers.DATA_DIR, 'profiles')

        new_p = read_json_file(os.path.join(self.test_data_dir, 'valid.json'))

        handler = self.request(new_p, role='admin')
        handler.request.language = None

        yield handler.post()

    @inlineCallbacks
    def test_get_all(self):
        """
        Create a new profile, then attempt to retrieve it.
        """
        self.test_data_dir = os.path.join(helpers.DATA_DIR, 'profiles')

        new_p = read_json_file(os.path.join(self.test_data_dir, 'valid.json'))
        new_p = yield profile.create_profile(1, None, new_p)

        handler = self.request(role='admin')
        yield handler.get()


class TestProfileInstance(helpers.TestHandler):
    _handler = profile.ProfileInstance

    @inlineCallbacks
    def test_delete(self):
        """
        Create a new profile, then attempt to delete it.
        """
        self.test_data_dir = os.path.join(helpers.DATA_DIR, 'profiles')

        new_p = read_json_file(os.path.join(self.test_data_dir, 'valid.json'))
        new_p = yield profile.create_profile(1, None, new_p)
        
        handler = self.request(role='admin')
        yield handler.delete(new_p['id'])