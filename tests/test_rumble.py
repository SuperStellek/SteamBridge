import errno
from types import SimpleNamespace as N
import unittest
from steambridge.rumble import Rumble

class Physical:
    def __init__(self): self.uploads=[]; self.writes=[]; self.erased=[]; self.failure=None
    def upload_effect(self,effect):
        if self.failure: raise self.failure
        self.uploads.append(effect)
        return 7
    def write(self,*event): self.writes.append(event)
    def erase_effect(self,effect): self.erased.append(effect)
class Virtual:
    def __init__(self):
        self.upload=N(effect=N(id=2,type=0x50),retval=None)
        self.erase=N(effect_id=2,retval=None)
        self.ends=[]
    def begin_upload(self,request): return self.upload
    def end_upload(self,u): self.ends.append(('upload',u.retval))
    def begin_erase(self,request): return self.erase
    def end_erase(self,e): self.ends.append(('erase',e.retval))
class RumbleTests(unittest.TestCase):
    def setUp(self): self.p=Physical(); self.v=Virtual(); self.r=Rumble(self.p,self.v)
    def event(self,t,c,v=1): self.r.event(N(type=t,code=c,value=v))
    def test_upload_ids_not_overwritten(self):
        self.event(0x101,1)
        self.assertEqual(self.p.uploads[0].id,-1)
        self.assertEqual(self.v.upload.effect.id,2)
        self.assertEqual(self.r.effects,{2:7})
    def test_update_play_stop_erase(self):
        self.event(0x101,1)
        self.event(0x101,1)
        self.assertEqual(self.p.uploads[-1].id,7)
        self.event(21,2,1)
        self.event(21,2,0)
        self.assertEqual(self.p.writes,[(21,7,1),(21,7,0)])
        self.event(0x101,2)
        self.assertEqual(self.p.erased,[7])
        self.assertEqual(self.r.effects,{})
    def test_upload_failure_completes_transaction(self):
        self.p.failure=OSError(errno.ENOSPC,'full')
        self.event(0x101,1)
        self.assertEqual(self.v.ends,[('upload',-errno.ENOSPC)])
        self.assertEqual(self.r.effects,{})
    def test_unsupported_effect_rejected(self):
        self.v.upload.effect.type=0x51
        self.event(0x101,1)
        self.assertEqual(self.v.ends,[('upload',-errno.EINVAL)])
    def test_close_stops_and_erases(self):
        self.event(0x101,1)
        self.r.close()
        self.assertEqual(self.p.writes,[(21,7,0)])
        self.assertEqual(self.p.erased,[7])
    def test_unknown_play_ignored(self):
        self.event(21,3)
        self.assertEqual(self.p.writes,[])
