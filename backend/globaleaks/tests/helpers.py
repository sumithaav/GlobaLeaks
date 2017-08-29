# -*- coding: UTF-8

"""
Utilities and basic TestCases.
"""

import sys
reload(sys)
sys.setdefaultencoding('utf8')

from globaleaks import db, models, security, event, jobs, __version__
from globaleaks.anomaly import Alarm
from globaleaks.db.appdata import load_appdata, read_json_file
from globaleaks.orm import transact
from globaleaks.handlers import rtip, wbtip
from globaleaks.handlers.authentication import db_get_wbtip_by_receipt
from globaleaks.handlers.base import BaseHandler, GLSessions, new_session, \
    write_upload_encrypted_to_disk
from globaleaks.handlers.admin.context import create_context, get_context
from globaleaks.handlers.admin.receiver import create_receiver
from globaleaks.handlers.admin.field import db_create_field
from globaleaks.handlers.admin.step import create_step
from globaleaks.handlers.admin.questionnaire import get_questionnaire, db_get_questionnaire
from globaleaks.handlers.admin.user import create_admin_user, create_custodian_user
from globaleaks.handlers.submission import create_submission
from globaleaks.rest.apicache import GLApiCache
from globaleaks.rest import errors
from globaleaks.settings import GLSettings
from globaleaks.security import GLSecureTemporaryFile
from globaleaks.utils import tempdict, token, utility
from globaleaks.utils.structures import fill_localized_keys
from globaleaks.utils.utility import datetime_null, datetime_now, datetime_to_ISO8601, \
    log, sum_dicts

from globaleaks.workers import process
from globaleaks.workers.supervisor import ProcessSupervisor

from . import TEST_DIR, config as test_config

import base64
import copy
import json
import os
import shutil
import signal

from datetime import timedelta

from twisted.web.test.requesthelper import DummyRequest
from twisted.internet import threads, defer, task
from twisted.internet.address import IPv4Address
from twisted.internet.defer import inlineCallbacks, Deferred, returnValue
from twisted.trial import unittest
from twisted.internet.protocol import ProcessProtocol
from storm.twisted.testing import FakeThreadPool


## constants
VALID_PASSWORD1 = u'ACollectionOfDiplomaticHistorySince_1966_ToThe_Pr esentDay#'
VALID_PASSWORD2 = VALID_PASSWORD1
VALID_SALT1 = security.generateRandomSalt()
VALID_SALT2 = security.generateRandomSalt()
VALID_HASH1 = security.hash_password(VALID_PASSWORD1, VALID_SALT1)
VALID_HASH2 = security.hash_password(VALID_PASSWORD2, VALID_SALT2)
VALID_BASE64_IMG = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVQYV2NgYAAAAAMAAWgmWQ0AAAAASUVORK5CYII='
INVALID_PASSWORD = u'antani'

PGPKEYS = {}

DATA_DIR = os.path.join(TEST_DIR, 'data')
kp = os.path.join(DATA_DIR, 'gpg')
for filename in os.listdir(kp):
    with open(os.path.join(kp, filename)) as pgp_file:
        PGPKEYS[filename] = unicode(pgp_file.read())

def deferred_sleep_mock(seconds):
    return

utility.deferred_sleep = deferred_sleep_mock


class UTlog:
    @staticmethod
    def mlog(flag):
        def log(msg, *args):
            msg = (msg % args) if len(args) else msg

            with open('./test.log', 'a') as f:
                f.write('[{}] {}\n'.format(flag, msg))

        return log

log.err = UTlog.mlog('E')
log.debug = UTlog.mlog('D')
log.info = UTlog.mlog('I')


def init_glsettings_for_unit_tests():
    GLSettings.testing = True
    GLSettings.set_devel_mode()
    GLSettings.logging = None
    GLSettings.failed_login_attempts = 0
    GLSettings.working_path = './working_path'

    GLSettings.eval_paths()

    GLSettings.set_ramdisk_path()

    GLSettings.remove_directories()
    GLSettings.create_directories()

    GLSettings.orm_tp = FakeThreadPool()

    GLSettings.memory_copy.hostname = 'localhost'

    GLSessions.clear()


def export_fixture(*models):
    """
    Return a valid json object holding all informations handled by the fields.

    :param field: the field we want to export.
    :rtype: str
    :return: a valid JSON string exporting the field.
    """
    return json.dumps([{
        'fields': model.dict(),
        'class': model.__class__.__name__,
    } for model in models], default=str, indent=2)


@transact
def update_node_setting(store, var_name, value):
    models.config.NodeFactory(store).set_val(var_name, value)


def get_dummy_step():
    return {
        'id': '',
        'label': u'Step 1',
        'description': u'Step Description',
        'presentation_order': 0,
        'triggered_by_score': 0,
        'questionnaire_id': '',
        'children': []
    }

def get_dummy_field():
    return {
        'id': '',
        'instance': 'template',
        'editable': True,
        'template_id': '',
        'step_id': '',
        'fieldgroup_id': '',
        'label': u'antani',
        'type': u'inputbox',
        'preview': False,
        'description': u'field description',
        'hint': u'field hint',
        'multi_entry': False,
        'multi_entry_hint': '',
        'stats_enabled': False,
        'required': False,
        'attrs': {},
        'options': [],
        'children': [],
        'y': 1,
        'x': 1,
        'width': 0,
        'triggered_by_score': 0
    }


files_count = 0

def get_dummy_file(filename=None, content_type=None, content=None):
    global files_count
    files_count += 1
    filename = ''.join(unichr(x) for x in range(0x400, 0x40A)).join('-%d' % files_count)

    content_type = 'application/octet'

    content = base64.b64decode(VALID_BASE64_IMG)

    temporary_file = GLSecureTemporaryFile(GLSettings.tmp_upload_path)

    temporary_file.write(content)
    temporary_file.avoid_delete()

    return {
        'name': filename,
        'description': 'description',
        'body': temporary_file,
        'size': len(content),
        'path': temporary_file.filepath,
        'type': content_type,
        'submission': False
    }

def get_file_upload(self):
    return get_dummy_file()

BaseHandler.get_file_upload = get_file_upload


class TestGL(unittest.TestCase):
    initialize_test_database_using_archived_db = True
    encryption_scenario = 'ENCRYPTED'

    @inlineCallbacks
    def setUp(self):
        test_config.skipCase(self)
        self.test_reactor = task.Clock()

        jobs.base.test_reactor = self.test_reactor
        tempdict.test_reactor = self.test_reactor
        token.TokenList.reactor = self.test_reactor
        GLSessions.reactor = self.test_reactor

        init_glsettings_for_unit_tests()

        self.setUp_dummy()

        if self.initialize_test_database_using_archived_db:
            shutil.copy(
                os.path.join(TEST_DIR, 'db', 'empty', GLSettings.db_file_name),
                os.path.join(GLSettings.working_path, 'db', GLSettings.db_file_name)
            )
        else:
            yield db.init_db(use_single_lang=True)

        allow_unencrypted = self.encryption_scenario in ['PLAINTEXT', 'MIXED']

        yield update_node_setting('allow_unencrypted', allow_unencrypted)

        yield db.refresh_memory_variables()

        sup = ProcessSupervisor([], '127.0.0.1', 8082)
        GLSettings.appstate.process_supervisor = sup

        Alarm.reset()
        event.EventTrackQueue.clear()
        GLSettings.reset_hourly()

        GLSettings.submission_minimum_delay = 0

        self.internationalized_text = load_appdata()['node']['whistleblowing_button']


    def call_spigot(self):
        """
        Required for clearing scheduled callbacks in the testReactor that have yet to run.
        If a unittest has scheduled something, we execute it before moving on.
        """
        deferred_fns = self.test_reactor.getDelayedCalls()
        i = 0
        while len(deferred_fns) != 0:
            yield deferred_fns[0].getTime()
            if i >= 30:
                raise Exception("stuck in callback loop")
            i += 1
            deferred_fns = self.test_reactor.getDelayedCalls()
        raise StopIteration

    def tearDown(self):
        self.test_reactor.pump(self.call_spigot())

    def setUp_dummy(self):
        dummyStuff = MockDict()

        self.dummyContext = dummyStuff.dummyContext
        self.dummySubmission = dummyStuff.dummySubmission
        self.dummyAdminUser = self.get_dummy_user('admin', 'admin')
        self.dummyAdminUser['deletable'] = False
        self.dummyCustodianUser = self.get_dummy_user('custodian', 'custodian1')
        self.dummyReceiverUser_1 = self.get_dummy_user('receiver', 'receiver1')
        self.dummyReceiverUser_2 = self.get_dummy_user('receiver', 'receiver2')
        self.dummyReceiver_1 = self.get_dummy_receiver('receiver1')  # the one without PGP
        self.dummyReceiver_2 = self.get_dummy_receiver('receiver2')  # the one with PGP

        if self.encryption_scenario == 'ENCRYPTED':
            self.dummyReceiver_1['pgp_key_public'] = PGPKEYS['VALID_PGP_KEY1_PUB']
            self.dummyReceiver_2['pgp_key_public'] = PGPKEYS['VALID_PGP_KEY2_PUB']
        elif self.encryption_scenario == 'ENCRYPTED_WITH_ONE_KEY_MISSING':
            self.dummyReceiver_1['pgp_key_public'] = PGPKEYS['VALID_PGP_KEY1_PUB']
            self.dummyReceiver_2['pgp_key_public'] = ''
        elif self.encryption_scenario == 'ENCRYPTED_WITH_ONE_KEY_EXPIRED':
            self.dummyReceiver_1['pgp_key_public'] = PGPKEYS['VALID_PGP_KEY1_PUB']
            self.dummyReceiver_2['pgp_key_public'] = PGPKEYS['EXPIRED_PGP_KEY_PUB']
        if self.encryption_scenario == 'MIXED':
            self.dummyReceiver_1['pgp_key_public'] = ''
            self.dummyReceiver_2['pgp_key_public'] = PGPKEYS['VALID_PGP_KEY1_PUB']
        elif self.encryption_scenario == 'PLAINTEXT':
            self.dummyReceiver_1['pgp_key_public'] = ''
            self.dummyReceiver_2['pgp_key_public'] = ''

        self.dummyNode = dummyStuff.dummyNode

        self.assertEqual(os.listdir(GLSettings.submission_path), [])
        self.assertEqual(os.listdir(GLSettings.tmp_upload_path), [])

    def localization_set(self, dict_l, dict_c, language):
        ret = dict(dict_l)

        for attr in getattr(dict_c, 'localized_keys'):
            ret[attr] = {}
            ret[attr][language] = unicode(dict_l[attr])

        return ret

    def get_dummy_user(self, role, username):
        new_u = dict(MockDict().dummyUser)
        new_u['role'] = role
        new_u['username'] = username
        new_u['name'] = new_u['public_name'] = new_u['mail_address'] = \
            unicode("%s@%s.xxx" % (username, username))
        new_u['description'] = u''
        new_u['password'] = VALID_PASSWORD1
        new_u['state'] = u'enabled'
        new_u['deletable'] = True

        return new_u

    def get_dummy_receiver(self, username):
        new_u = self.get_dummy_user('receiver', username)
        new_r = dict(MockDict().dummyReceiver)

        return sum_dicts(new_r, new_u)

    @transact
    def create_dummy_field(self, store, **custom_attrs):
        field = get_dummy_field()

        fill_localized_keys(field, models.Field.localized_keys, 'en')

        field.update(custom_attrs)

        f = models.Field(field)

        store.add(f)

        return f.id

    def fill_random_field_recursively(self, answers, field):
        field_type = field['type']

        if field_type == 'checkbox':
            value = {}
            for option in field['options']:
                value[option['id']] = 'True'
        elif field_type in ['selectbox', 'multichoice']:
            value = {'value': field['options'][0]['id']}
        elif field_type == 'date':
            value = {'value': datetime_to_ISO8601(datetime_now())}
        elif field_type == 'tos':
            value = {'value': 'True'}
        elif field_type == 'fieldgroup':
            value = {}
            for child in field['children']:
                self.fill_random_field_recursively(value, child)
        else:
            value = {'value': unicode(''.join(unichr(x) for x in range(0x400, 0x4FF)))}

        answers[field['id']] = [value]

    @transact
    def fill_random_answers(self, store, questionnaire_id, value=None):
        """
        return randomly populated questionnaire
        """
        answers = {}

        questionnaire = db_get_questionnaire(store, questionnaire_id, 'en')

        for step in questionnaire['steps']:
            for field in step['children']:
                self.fill_random_field_recursively(answers, field)

        return answers

    @inlineCallbacks
    def get_dummy_submission(self, context_id):
        """
        this may works until the content of the fields do not start to be validated. like
        numbers shall contain only number, and not URL.
        This validation would not be implemented in validate_jmessage but in structures.Fields

        need to be enhanced generating appropriate data based on the fields.type
        """
        context = yield get_context(context_id, 'en')
        answers = yield self.fill_random_answers(context['questionnaire_id'])

        defer.returnValue({
            'context_id': context_id,
            'receivers': context['receivers'],
            'files': [],
            'human_captcha_answer': 0,
            'proof_of_work_answer': 0,
            'identity_provided': False,
            'total_score': 0,
            'answers': answers
        })

    def get_dummy_file(self):
        return get_dummy_file(filename)

    def get_dummy_shorturl(self, x = ''):
        return {
          'shorturl': '/s/shorturl' + str(x),
          'longurl': '/longurl' + str(x)
        }

    @inlineCallbacks
    def emulate_file_upload(self, token, n):
        """
        This emulates the file upload of an incomplete submission
        """
        for _ in range(n):
            dummyFile = self.get_dummy_file()


            dst = os.path.join(GLSettings.submission_path,
                               os.path.basename(dummyFile['path']))

            dummyFile = yield threads.deferToThread(write_upload_encrypted_to_disk, dummyFile, dst)
            dummyFile['date'] = datetime_null()

            token.associate_file(dummyFile)

            dummyFile['body'].close()

    @transact
    def _exists(self, store, model, *id_args, **id_kwargs):
        if not id_args and not id_kwargs:
            raise ValueError
        return model.get(store, *id_args, **id_kwargs) is not None

    @inlineCallbacks
    def assert_model_exists(self, model, *id_args, **id_kwargs):
        existing = yield self._exists(model, *id_args, **id_kwargs)
        msg = 'The following has *NOT* been found on the store: {} {}'.format(id_args, id_kwargs)
        self.assertTrue(existing, msg)

    @inlineCallbacks
    def assert_model_not_exists(self, model, *id_args, **id_kwargs):
        existing = yield self._exists(model, *id_args, **id_kwargs)
        msg = 'The following model has been found on the store: {} {}'.format(id_args, id_kwargs)
        self.assertFalse(existing, msg)

    def pollute_events(self, number_of_times=10):
        for _ in range(number_of_times):
            for event_obj in event.events_monitored:
                for x in range(2):
                    event.EventTrack(event_obj, timedelta(seconds=1.0 * x))

    def pollute_events_and_perform_synthesis(self, number_of_times=10):
        for _ in range(number_of_times):
            for event_obj in event.events_monitored:
                for x in range(2):
                    event.EventTrack(event_obj, timedelta(seconds=1.0 * x)).synthesis()
    @transact
    def get_rtips(self, store):
        ret = []
        for tip in store.find(models.ReceiverTip):
            x = rtip.serialize_rtip(store, tip, 'en')
            x['receiver_id'] = tip.receiver_id
            ret.append(x)

        return ret

    @transact
    def get_rfiles(self, store, rtip_id):
        return [{'id': rfile.id} for rfile in store.find(models.ReceiverFile, models.ReceiverFile.receivertip_id == rtip_id)]

    @transact
    def get_wbtips(self, store):
        ret = []
        for tip in store.find(models.WhistleblowerTip):
            x = wbtip.serialize_wbtip(store, tip, 'en')
            x['receivers_ids'] = [rtip.receiver_id for rtip in tip.internaltip.receivertips]
            ret.append(x)

        return ret

    @transact
    def get_wbfiles(self, store, wbtip_id):
        return [{'id': wbfile.id} for wbfile in store.find(models.WhistleblowerFile,
                                                           models.WhistleblowerFile.receivertip_id == models.ReceiverTip.id,
                                                           models.WhistleblowerTip.id == wbtip_id,
                                                           models.ReceiverTip.internaltip_id == models.WhistleblowerTip.id)]

    @transact
    def get_internalfiles_by_receipt(self, store, receipt):
        wbtip = db_get_wbtip_by_receipt(store, receipt)
        ifiles = store.find(models.InternalFile, models.InternalFile.internaltip_id == unicode(wbtip.id))

        return [models.serializers.serialize_ifile(ifile) for ifile in ifiles]


    @transact
    def get_receiverfiles_by_receipt(self, store, receipt):
        wbtip = db_get_wbtip_by_receipt(store, receipt)
        rfiles = store.find(models.ReceiverFile, models.ReceiverFile.receivertip_id == models.ReceiverTip.id,
                                                 models.ReceiverTip.internaltip_id == unicode(wbtip.id))

        ret = []
        for rfile in rfiles:
            f = models.serializers.serialize_rfile(rfile)
            f['status'] = rfile.status
            ret.append(f)

        return ret

    def db_test_model_count(self, store, model, n):
        self.assertEqual(store.find(model).count(), n)

    @transact
    def test_model_count(self, store, model, n):
        self.db_test_model_count(store, model, n)


class TestGLWithPopulatedDB(TestGL):
    complex_field_population = False
    population_of_recipients = 2
    population_of_submissions = 2
    population_of_attachments = 2

    @inlineCallbacks
    def setUp(self):
        yield TestGL.setUp(self)
        yield self.fill_data()

    @inlineCallbacks
    def fill_data(self):
        # fill_data/create_admin
        self.dummyAdminUser = yield create_admin_user(copy.deepcopy(self.dummyAdminUser), 'en')

        # fill_data/create_custodian
        self.dummyCustodianUser = yield create_custodian_user(copy.deepcopy(self.dummyCustodianUser), 'en')

        # fill_data/create_receiver
        self.dummyReceiver_1 = yield create_receiver(copy.deepcopy(self.dummyReceiver_1), 'en')
        self.dummyReceiverUser_1['id'] = self.dummyReceiver_1['id']
        self.dummyReceiver_2 = yield create_receiver(copy.deepcopy(self.dummyReceiver_2), 'en')
        self.dummyReceiverUser_2['id'] = self.dummyReceiver_2['id']
        receivers_ids = [self.dummyReceiver_1['id'], self.dummyReceiver_2['id']]

        # fill_data/create_context
        self.dummyContext['receivers'] = receivers_ids
        self.dummyContext = yield create_context(copy.deepcopy(self.dummyContext), 'en')

        self.dummyQuestionnaire = yield get_questionnaire(self.dummyContext['questionnaire_id'], 'en')

        self.dummyQuestionnaire['steps'].append(get_dummy_step())
        self.dummyQuestionnaire['steps'][1]['questionnaire_id'] = self.dummyContext['questionnaire_id']
        self.dummyQuestionnaire['steps'][1]['label'] = 'Whistleblower identity'
        self.dummyQuestionnaire['steps'][1]['presentation_order'] = 1
        self.dummyQuestionnaire['steps'][1] = yield create_step(self.dummyQuestionnaire['steps'][1], 'en')

        if self.complex_field_population:
            yield self.add_whistleblower_identity_field_to_step(self.dummyQuestionnaire['steps'][1]['id'])

    @transact
    def add_whistleblower_identity_field_to_step(self, store, step_id):
        wbf = store.find(models.Field, models.Field.id == u'whistleblower_identity').one()

        reference_field = get_dummy_field()
        reference_field['instance'] = 'reference'
        reference_field['template_id'] = wbf.id
        reference_field['step_id'] = step_id
        db_create_field(store, reference_field, 'en')

    def perform_submission_start(self):
        self.dummyToken = token.Token('submission')
        self.dummyToken.solve()

    @inlineCallbacks
    def perform_submission_uploads(self):
        yield self.emulate_file_upload(self.dummyToken, self.population_of_attachments)

    @inlineCallbacks
    def perform_submission_actions(self):
        self.dummySubmission['context_id'] = self.dummyContext['id']
        self.dummySubmission['receivers'] = self.dummyContext['receivers']
        self.dummySubmission['identity_provided'] = False
        self.dummySubmission['answers'] = yield self.fill_random_answers(self.dummyContext['questionnaire_id'])
        self.dummySubmission['total_score'] = 0

        self.dummySubmission = yield create_submission(self.dummySubmission,
                                                       self.dummyToken.uploaded_files,
                                                       True, 'en')

    @inlineCallbacks
    def perform_post_submission_actions(self):
        commentCreation = {
            'content': 'comment!'
        }

        messageCreation = {
            'content': 'message!'
        }

        identityaccessrequestCreation = {
            'request_motivation': 'request motivation'
        }

        self.dummyRTips = yield self.get_rtips()

        for rtip_desc in self.dummyRTips:
            yield rtip.create_comment(rtip_desc['receiver_id'],
                                      rtip_desc['id'],
                                      commentCreation)

            yield rtip.create_message(rtip_desc['receiver_id'],
                                      rtip_desc['id'],
                                      messageCreation)

            yield rtip.create_identityaccessrequest(rtip_desc['receiver_id'],
                                                    rtip_desc['id'],
                                                    identityaccessrequestCreation,
                                                    'en')

        self.dummyWBTips = yield self.get_wbtips()

        for wbtip_desc in self.dummyWBTips:
            yield wbtip.create_comment(wbtip_desc['id'],
                                       commentCreation)

            for receiver_id in wbtip_desc['receivers_ids']:
                yield wbtip.create_message(wbtip_desc['id'], receiver_id, messageCreation)

    @inlineCallbacks
    def perform_full_submission_actions(self):
        """Populates the DB with tips, comments, messages and files"""
        for x in range(self.population_of_submissions):
            self.perform_submission_start()
            yield self.perform_submission_uploads()
            yield self.perform_submission_actions()

        yield self.perform_post_submission_actions()

        yield self.test_model_count(models.SecureFileDelete, 0)

    @inlineCallbacks
    def perform_minimal_submission(self):
        self.perform_submission_start()
        yield self.perform_submission_uploads()
        yield self.perform_submission_actions()

    @transact
    def force_wbtip_expiration(self, store):
        store.find(models.InternalTip).set(wb_last_access = datetime_null())

    @transact
    def force_itip_expiration(self, store):
        store.find(models.InternalTip).set(expiration_date = datetime_null())

    @transact
    def set_contexts_timetolive(self, store, ttl):
        store.find(models.Context).set(tip_timetolive = ttl)


class TestHandler(TestGLWithPopulatedDB):
    """
    :attr _handler: handler class to be tested
    """
    _handler = None
    _test_desc = None
    #_test_desc = {
    #  'model': Context
    #  'create': context.create_context
    #  'data': {
    #
    #  }
    #}

    @inlineCallbacks
    def setUp(self):
        """
        override default handlers get_store with a mock store used for testing
        """
        # we bypass TestGLWith Populated DB to test against clean DB.
        yield TestGL.setUp(self)

        self.initialization()

    def initialization(self):
        # we need to reset settings.session to keep each test independent
        GLSessions.clear()

        # we need to reset GLApiCache to keep each test independent
        GLApiCache.invalidate()

    def request(self, jbody=None, user_id=None, role=None, headers=None, body='', path=None,
                remote_ip='0.0.0.0', method='MOCK', handler_cls=None, attached_file={}, kwargs={}):
        """
        Constructs a handler for preforming mock requests using the bag of params described below.

        Args:

            jbody:
                The body of the request as a dict (it will be automatically
                converted to string)

            body:
                The body of the request as a string

            user_id:
                when simulating authentication the session should be bound
                to a certain user_id.

            role:
                when simulating authentication the session should be bound
                to a certain role.

            method:
                HTTP method, e.g. "GET" or "POST"

            headers:
                Dict of headers to pass on the request

            remote_ip:
                If a particular remote_ip should be set.

            handler_cls:
                The type of handler that will respond to the request. If this is not set self._handler is used.

            attached_file:
                A dict to place in the request.args.files obj
        """
        if jbody and not body:
            body = json.dumps(jbody)
        elif body and jbody:
            raise ValueError('jbody and body in conflict')

        if handler_cls is None:
            handler_cls = self._handler

        request = DummyRequest([''])

        def getResponseBody():
            return ''.join(request.written)

        request.path = ''
        request.code = 200
        request.language = 'en'
        request.client_ip = '127.0.0.1'
        request.client_proto = 'https'
        request.client_using_tor = False

        request.getResponseBody = getResponseBody

        request.client = IPv4Address('TCP', '1.2.3.4', 12345)

        request.args = {}
        if attached_file is not None:
            request.args = {'file': [attached_file]}

        if headers is not None:
            for k, v in headers.iteritems():
                request.requestHeaders.setRawHeaders(bytes(k), [bytes(v)])

        request.headers = request.getAllHeaders()

        from globaleaks.rest import api
        x = api.APIResourceWrapper()
        x.preprocess(request)

        if path is not None:
            if not path.startswith('/'):
                raise ValueError('Must pass a valid url path')
            request.path = path

        class fakeBody(object):
            def read(self):
                return body

            def close(self):
                pass

        request.content = fakeBody()

        from globaleaks.rest.api import decorate_method
        if not getattr(handler_cls, 'decorated', False):
            for method in ['get', 'post', 'put', 'delete']:
                if getattr(handler_cls, method, None) is not None:
                    decorate_method(handler_cls, method)
                    handler_cls.decorated = True

        handler = handler_cls(request, **kwargs)

        if user_id is None and role is not None:
            if role == 'admin':
                user_id = self.dummyAdminUser['id']
            elif role == 'receiver':
                user_id = self.dummyReceiverUser_1['id']
            elif role == 'custodian':
                user_id = self.dummyCustodianUser['id']

        if role is not None:
            session = new_session(user_id, role, 'enabled')
            handler.request.headers['x-session'] = session.id

        return handler

    def ss_serial_desc(self, safe_set, request_desc):
        """
        Constructs a request_dec parser of a handler that uses a safe_set in its serialization
        """
        return {k : v for k, v in request_desc.iteritems() if k in safe_set}

    def get_dummy_request(self):
        return self._test_desc['model']().dict()


class TestCollectionHandler(TestHandler):
    @inlineCallbacks
    def test_get(self):
        if self._test_desc is None:
            return

        data = self.get_dummy_request()

        data = yield self._test_desc['create'](data, 'en')

        handler = self.request(role='admin')


    @inlineCallbacks
    def test_post(self):
        if self._test_desc is None:
            return

        data = self.get_dummy_request()

        handler = self.request(data, role='admin')

        data = yield handler.post()


class TestInstanceHandler(TestHandler):
    @inlineCallbacks
    def test_put(self):
        if self._test_desc is None:
            return

        data = self.get_dummy_request()

        data = yield self._test_desc['create'](data, 'en')

        handler = self.request(data, role='admin')
        data = yield handler.put(data['id'])

    @inlineCallbacks
    def test_delete(self):
        if self._test_desc is None:
            return

        data = self.get_dummy_request()

        data = yield self._test_desc['create'](data, 'en')

        handler = self.request(data, role='admin')

        yield handler.delete(data['id'])

        yield self.assertFailure(handler.delete(data['id']),
                                 errors.ResourceNotFound)



class TestHandlerWithPopulatedDB(TestHandler):
    @inlineCallbacks
    def setUp(self):
        """
        override default handlers' get_store with a mock store used for testing/
        """
        yield TestGLWithPopulatedDB.setUp(self)
        self.initialization()


class MockDict:
    """
    This class just create all the shit we need for emulate a GLNode
    """
    def __init__(self):
        self.dummyUser = {
            'id': '',
            'username': u'maker@iz.cool.yeah',
            'password': VALID_PASSWORD1,
            'old_password': '',
            'salt': VALID_SALT1,
            'role': u'receiver',
            'state': u'enabled',
            'name': u'Generic User',
            'description': u'King MockDummy',
            'public_name': u'Charlie Brown',
            'last_login': u'1970-01-01 00:00:00.000000',
            'language': u'en',
            'password_change_needed': False,
            'password_change_date': u'1970-01-01 00:00:00.000000',
            'pgp_key_fingerprint': u'',
            'pgp_key_public': u'',
            'pgp_key_expiration': u'1970-01-01 00:00:00.000000',
            'pgp_key_remove': False
        }

        self.dummyReceiver = copy.deepcopy(self.dummyUser)

        self.dummyReceiver = sum_dicts(self.dummyReceiver, {
            'can_delete_submission': True,
            'can_postpone_expiration': True,
            'contexts': [],
            'tip_notification': True,
            'presentation_order': 0,
            'configuration': 'default'
        })

        self.dummyContext = {
            'id': '',
            'name': u'Already localized name',
            'description': u'Already localized desc',
            'recipients_clarification': u'',
            'presentation_order': 0,
            'receivers': [],
            'questionnaire_id': '',
            'select_all_receivers': True,
            'tip_timetolive': 20,
            'maximum_selectable_receivers': 0,
            'show_small_receiver_cards': False,
            'show_context': True,
            'show_recipients_details': True,
            'allow_recipients_selection': False,
            'enable_comments': True,
            'enable_messages': True,
            'enable_two_way_comments': True,
            'enable_two_way_messages': True,
            'enable_attachments': True,
            'enable_rc_to_wb_files': True,
            'show_receivers_in_alphabetical_order': False,
            'status_page_message': ''
        }

        self.dummySubmission = {
            'context_id': '',
            'answers': {},
            'receivers': [],
            'files': []
        }

        self.dummyNode = {
            'name': u'Please, set me: name/title',
            'description': u'Pleæs€, set m€: d€scription',
            'presentation': u'This is whæt æpp€ærs on top',
            'footer': u'check it out https://www.youtube.com/franksentus ;)',
            'security_awareness_title': u'',
            'security_awareness_text': u'',
            'whistleblowing_question': u'',
            'whistleblowing_button': u'',
            'whistleblowing_receipt_prompt': u'',
            'hostname': u'www.globaleaks.org',
            'onionservice': u'',
            'tb_download_link': u'https://www.torproject.org/download/download',
            'email': u'email@dummy.net',
            'languages_supported': [],  # ignored
            'languages_enabled': ['it', 'en'],
            'latest_version': __version__,
            'receipt_salt': '<<the Lannisters send their regards>>',
            'maximum_filesize': 30,
            'maximum_namesize': 120,
            'maximum_textsize': 4096,
            'tor2web_admin': True,
            'tor2web_custodian': True,
            'tor2web_whistleblower': True,
            'tor2web_receiver': True,
            'can_postpone_expiration': False,
            'can_delete_submission': False,
            'can_grant_permissions': False,
            'ahmia': False,
            'allow_indexing': False,
            'allow_unencrypted': True,
            'disable_encryption_warnings': False,
            'allow_iframes_inclusion': False,
            'custom_homepage': False,
            'disable_submissions': False,
            'disable_privacy_badge': False,
            'disable_security_awareness_badge': False,
            'disable_security_awareness_questions': False,
            'disable_key_code_hint': False,
            'disable_donation_panel': False,
            'default_language': u'en',
            'default_password': u'globaleaks',
            'default_questionnaire': u'default',
            'admin_language': u'en',
            'simplified_login': False,
            'enable_captcha': False,
            'enable_proof_of_work': False,
            'enable_experimental_features': False,
            'enable_custom_privacy_badge': False,
            'custom_privacy_badge_tor': u'',
            'custom_privacy_badge_none': u'',
            'header_title_homepage': u'',
            'header_title_submissionpage': u'',
            'header_title_receiptpage': u'',
            'header_title_tippage': u'',
            'landing_page': u'homepage',
            'context_selector_type': u'list',
            'contexts_clarification': u'',
            'show_contexts_in_alphabetical_order': False,
            'show_small_context_cards': False,
            'widget_comments_title': '',
            'widget_messages_title': '',
            'widget_files_title': '',
            'threshold_free_disk_megabytes_high': 200,
            'threshold_free_disk_megabytes_medium': 500,
            'threshold_free_disk_megabytes_low': 1000,
            'threshold_free_disk_percentage_high': 3,
            'threshold_free_disk_percentage_medium': 5,
            'threshold_free_disk_percentage_low': 10,
            'wbtip_timetolive': 90,
            'basic_auth': False,
            'basic_auth_username': '',
            'basic_auth_password': '',
            'reachable_via_web': False,
            'anonymize_outgoing_connections': False,
        }


class SimpleServerPP(ProcessProtocol):
    def __init__(self):
        self.welcome_msg = False
        self.start_defer = Deferred()
        process.set_pdeathsig(signal.SIGTERM)

    def outReceived(self, data):
        # When the HTTPServer is ready it will produce a msg which we can hook
        # the start_defer callback to.
        if not self.welcome_msg:
            self.start_defer.callback(None)
            self.welcome_msg = True
