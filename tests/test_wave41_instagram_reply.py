import tempfile
import unittest
from pathlib import Path

from binario_marketing.inbox_reply_store import InboxReplyStore
from binario_marketing.meta_graph import MetaGraphClient
from binario_marketing.meta_inbox_actions import MetaInboxWriter


class Wave41InstagramReplyTests(unittest.TestCase):
    @staticmethod
    def accounts():
        return {"data":[{"id":"page-1","access_token":"PAGE_SECRET","instagram_business_account":{"id":"ig-1","username":"greenatics"}}]}

    def test_comment_must_belong_to_known_company_media(self):
        posts=[]
        def transport(method,url,params):
            if url.endswith('/me/accounts'): return self.accounts()
            if url.endswith('/media-1/comments'): return {"data":[{"id":"comment-1","from":{"id":"ig-customer"}}]}
            if method=='POST' and url.endswith('/comment-1/replies'): posts.append(url); return {"id":"reply-comment-1"}
            raise AssertionError((method,url))
        with tempfile.TemporaryDirectory() as tmp:
            writer=MetaInboxWriter(MetaGraphClient('token',transport=transport),InboxReplyStore(Path(tmp)))
            result=writer.reply_instagram_comment(company_id='company-1',instagram_id='ig-1',media_ids=['media-1'],comment_id='comment-1',text='Gracias')
            self.assertEqual(result['remote_id'],'reply-comment-1')
            with self.assertRaises(ValueError): writer.reply_instagram_comment(company_id='company-1',instagram_id='ig-1',media_ids=['media-1'],comment_id='comment-other',text='No enviar')
            self.assertEqual(len(posts),1)

    def test_self_authored_comment_is_blocked(self):
        posts=[]
        def transport(method,url,params):
            if url.endswith('/me/accounts'): return self.accounts()
            if url.endswith('/media-1/comments'): return {"data":[{"id":"comment-self","from":{"id":"ig-1"}}]}
            if method=='POST': posts.append(url); return {"id":"bad"}
            raise AssertionError((method,url))
        with tempfile.TemporaryDirectory() as tmp:
            writer=MetaInboxWriter(MetaGraphClient('token',transport=transport),InboxReplyStore(Path(tmp)))
            with self.assertRaisesRegex(ValueError,'authored by the company'):
                writer.reply_instagram_comment(company_id='company-1',instagram_id='ig-1',media_ids=['media-1'],comment_id='comment-self',text='No')
            self.assertEqual(posts,[])


if __name__=='__main__': unittest.main()
