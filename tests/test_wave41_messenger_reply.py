import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from binario_marketing.inbox_reply_store import InboxReplyConflict, InboxReplyStore
from binario_marketing.meta_graph import MetaGraphClient, MetaGraphError
from binario_marketing.meta_inbox_actions import MetaInboxWriter


class Wave41MessengerReplyTests(unittest.TestCase):
    @staticmethod
    def accounts():
        return {"data":[{"id":"page-1","access_token":"PAGE_SECRET"}]}

    def test_recipient_is_derived_and_success_is_not_resent(self):
        calls=[]; now=datetime.now(timezone.utc).isoformat()
        def transport(method,url,params):
            calls.append((method,url,dict(params)))
            if url.endswith('/me/accounts'): return self.accounts()
            if url.endswith('/msg-1'): return {"id":"msg-1","created_time":now,"from":{"id":"psid-customer"},"to":{"data":[{"id":"page-1"}]}}
            if method=='POST' and url.endswith('/page-1/messages'):
                self.assertEqual(json.loads(params['recipient']),{"id":"psid-customer"})
                self.assertEqual(json.loads(params['message']),{"text":"Claro, te ayudo"})
                self.assertEqual(params['messaging_type'],'RESPONSE')
                return {"message_id":"mid-reply-1"}
            raise AssertionError((method,url))
        with tempfile.TemporaryDirectory() as tmp:
            writer=MetaInboxWriter(MetaGraphClient('USER_SECRET',transport=transport),InboxReplyStore(Path(tmp)))
            first=writer.reply_facebook_message(company_id='company-1',page_id='page-1',message_id='msg-1',text='Claro, te ayudo')
            second=writer.reply_facebook_message(company_id='company-1',page_id='page-1',message_id='msg-1',text='Claro, te ayudo')
            self.assertFalse(first['reused']); self.assertTrue(second['reused'])
            self.assertEqual(sum(1 for method,url,_ in calls if method=='POST' and url.endswith('/page-1/messages')),1)
            persisted='\n'.join(path.read_text(encoding='utf-8') for path in Path(tmp).glob('*.json'))
            self.assertNotIn('Claro, te ayudo',persisted); self.assertNotIn('PAGE_SECRET',persisted)

    def test_expired_message_is_blocked_before_post(self):
        posts=[]; old=(datetime.now(timezone.utc)-timedelta(hours=25)).isoformat()
        def transport(method,url,params):
            if url.endswith('/me/accounts'): return self.accounts()
            if url.endswith('/msg-old'): return {"id":"msg-old","created_time":old,"from":{"id":"psid-customer"},"to":{"data":[{"id":"page-1"}]}}
            if method=='POST': posts.append(url); return {"message_id":"bad"}
            raise AssertionError((method,url))
        with tempfile.TemporaryDirectory() as tmp:
            writer=MetaInboxWriter(MetaGraphClient('token',transport=transport),InboxReplyStore(Path(tmp)))
            with self.assertRaisesRegex(ValueError,'24-hour'):
                writer.reply_facebook_message(company_id='company-1',page_id='page-1',message_id='msg-old',text='Hola')
            self.assertEqual(posts,[])

    def test_ambiguous_failure_blocks_blind_second_post(self):
        posts=0; now=datetime.now(timezone.utc).isoformat()
        def transport(method,url,params):
            nonlocal posts
            if url.endswith('/me/accounts'): return self.accounts()
            if url.endswith('/msg-1'): return {"id":"msg-1","created_time":now,"from":{"id":"psid-customer"},"to":{"data":[{"id":"page-1"}]}}
            if method=='POST' and url.endswith('/page-1/messages'): posts+=1; raise MetaGraphError('unknown outcome')
            raise AssertionError((method,url))
        with tempfile.TemporaryDirectory() as tmp:
            writer=MetaInboxWriter(MetaGraphClient('token',transport=transport),InboxReplyStore(Path(tmp)))
            with self.assertRaises(MetaGraphError): writer.reply_facebook_message(company_id='company-1',page_id='page-1',message_id='msg-1',text='Respuesta')
            with self.assertRaises(InboxReplyConflict): writer.reply_facebook_message(company_id='company-1',page_id='page-1',message_id='msg-1',text='Respuesta')
            self.assertEqual(posts,1)


if __name__=='__main__': unittest.main()
