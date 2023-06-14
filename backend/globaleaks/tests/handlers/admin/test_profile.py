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


class TestProfilesCollection(helpers.TestCollectionHandler):
    _handler = profile.ProfileCollection
    _test_desc = {
        'model': Profile,
        'create': profile.create_profile,
        'data': {
            'name': 'test'
        }
    }

    @inlineCallbacks
    def test_post_valid_json(self):
        self.test_data_dir = os.path.join(helpers.DATA_DIR, 'profiles')

        new_q = read_json_file(os.path.join(self.test_data_dir, 'valid.json'))

        handler = self.request(new_q, role='admin')
        handler.request.language = None

        yield handler.post()