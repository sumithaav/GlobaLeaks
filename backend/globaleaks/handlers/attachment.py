# -*- coding: utf-8 -*-
#
# files
#  *****
#
# API handling submissions file uploads and subsequent submissions attachments
import os

from twisted.internet.defer import inlineCallbacks

from globaleaks import models
from globaleaks.handlers.base import BaseHandler
from globaleaks.models import serializers, get
from globaleaks.orm import transact
from globaleaks.rest import errors
from globaleaks.security import directory_traversal_check
from globaleaks.settings import Settings
from globaleaks.utils.token import TokenList
from globaleaks.utils.utility import datetime_now


@transact
def register_ifile_on_db(store, tid, uploaded_file, internaltip_id):
    now = datetime_now()

    store.find(models.InternalTip, id=internaltip_id, tid=tid).set(update_date=now,
                                                                   wb_last_access=now)

    new_file = models.InternalFile()
    new_file.tid = tid
    new_file.name = uploaded_file['name']
    new_file.content_type = uploaded_file['type']
    new_file.size = uploaded_file['size']
    new_file.internaltip_id = internaltip_id
    new_file.submission = uploaded_file['submission']
    new_file.file_path = uploaded_file['path']
    store.add(new_file)

    return serializers.serialize_ifile(store, new_file)


class SubmissionAttachment(BaseHandler):
    """
    WhistleBlower interface to upload a new file for a non-finalized submission
    """
    check_roles = 'unauthenticated'
    upload_handler = True

    @inlineCallbacks
    def handle_attachment(self):
        self.uploaded_file['body'].avoid_delete()
        self.uploaded_file['body'].close()

        dst = os.path.join(Settings.attachments_path,
                           os.path.basename(self.uploaded_file['path']))

        directory_traversal_check(Settings.attachments_path, dst)

        yield self.write_upload_encrypted_to_disk(dst)

    @inlineCallbacks
    def post(self, token_id):
        """
        Errors: TokenFailure
        """
        token = TokenList.get(token_id)

        yield self.handle_attachment()

        self.uploaded_file['submission'] = True

        token.associate_file(self.uploaded_file)


class PostSubmissionAttachment(SubmissionAttachment):
    """
    WhistleBlower interface to upload a new file for an existing submission
    """
    check_roles = 'whistleblower'
    upload_handler = True

    @inlineCallbacks
    def post(self):
        """
        Errors: ModelNotFound
        """
        itip_id = yield models.get(models.WhistleblowerTip.id, models.WhistleblowerTip.id==self.current_user.user_id,
                                                                      models.WhistleblowerTip.tid==self.request.tid)

        yield self.handle_attachment()

        self.uploaded_file['submission'] = False

        # Second: register the file in the database
        yield register_ifile_on_db(self.request.tid, self.uploaded_file, itip_id)
