import tempfile
import unittest
from pathlib import Path

from binario_marketing.editor_store import EditorStore


class VisualReorderAtomicTests(unittest.TestCase):
    def test_reorder_to_moves_across_track_in_one_undo_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=EditorStore(Path(tmp))
            p='visual-order'
            state=store.apply(p,'add_clip',{'asset_id':'a','start':0,'end':1,'track':0})
            first=state['clips'][0]['id']
            state=store.apply(p,'add_clip',{'asset_id':'b','start':0,'end':1,'track':0})
            second=state['clips'][1]['id']
            state=store.apply(p,'add_clip',{'asset_id':'c','start':0,'end':1,'track':0})
            third=state['clips'][2]['id']
            state=store.apply(p,'add_clip',{'asset_id':'x','start':0,'end':1,'track':1})
            other=state['clips'][3]['id']

            state=store.apply(p,'reorder_to',{'clip_id':first,'target_position':2})
            track0=[row['id'] for row in state['clips'] if row['track']==0]
            self.assertEqual(track0,[second,third,first])
            self.assertIn(other,[row['id'] for row in state['clips'] if row['track']==1])

            undone=store.apply(p,'undo',{})
            self.assertEqual([row['id'] for row in undone['clips']],[first,second,third,other])

    def test_reorder_to_rejects_locked_boundary_and_bad_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=EditorStore(Path(tmp));p='visual-order-2'
            state=store.apply(p,'add_clip',{'asset_id':'a','start':0,'end':1,'track':0});clip=state['clips'][0]['id']
            store.apply(p,'lock',{'clip_id':clip,'value':True})
            with self.assertRaises(ValueError):store.apply(p,'reorder_to',{'clip_id':clip,'target_position':0})
            state=store.apply(p,'add_clip',{'asset_id':'b','start':0,'end':1,'track':0});other=state['clips'][1]['id']
            with self.assertRaises(ValueError):store.apply(p,'reorder_to',{'clip_id':other,'target_position':9})


if __name__=='__main__':unittest.main()
