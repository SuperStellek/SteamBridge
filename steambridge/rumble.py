"""Relay the uinput FF transaction protocol to a physical evdev device."""
import copy
import errno

class Rumble:
    def __init__(self, physical, virtual):
        self.physical, self.virtual = physical, virtual
        self.effects = {}

    def event(self, event):
        if event.type == 0x101 and event.code == 1:
            upload = self.virtual.begin_upload(event.value)
            try:
                if upload.effect.type != 0x50:
                    upload.retval = -errno.EINVAL
                else:
                    effect = copy.deepcopy(upload.effect)
                    virtual_id = effect.id
                    effect.id = self.effects.get(virtual_id, -1)
                    self.effects[virtual_id] = self.physical.upload_effect(effect)
                    upload.retval = 0
            except OSError as exc:
                upload.retval = -(exc.errno or errno.EIO)
            finally:
                self.virtual.end_upload(upload)
        elif event.type == 0x101 and event.code == 2:
            erase = self.virtual.begin_erase(event.value)
            try:
                physical_id = self.effects.get(erase.effect_id)
                if physical_id is not None:
                    self.physical.write(21, physical_id, 0)
                    self.physical.erase_effect(physical_id)
                    del self.effects[erase.effect_id]
                erase.retval = 0
            except OSError as exc:
                erase.retval = -(exc.errno or errno.EIO)
            finally:
                self.virtual.end_erase(erase)
        elif event.type == 21 and event.code in self.effects:
            self.physical.write(21, self.effects[event.code], event.value)

    def read(self):
        try:
            for event in self.virtual.read():
                self.event(event)
        except BlockingIOError:
            pass

    def close(self):
        for effect in self.effects.values():
            try:
                self.physical.write(21, effect, 0)
                self.physical.erase_effect(effect)
            except OSError:
                pass
        self.effects.clear()
