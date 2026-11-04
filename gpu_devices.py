"""Read DXGI adapter order so DirectML selects NVIDIA, not integrated graphics."""
import ctypes as c
import uuid

class Description(c.Structure):
    _fields_=[('name',c.c_wchar*128),('vendor',c.c_uint),('device',c.c_uint),('subsystem',c.c_uint),('revision',c.c_uint),('dedicated_video',c.c_size_t),('dedicated_system',c.c_size_t),('shared_system',c.c_size_t),('luid_low',c.c_uint),('luid_high',c.c_long),('flags',c.c_uint)]

def adapters():
    factory=c.c_void_p();iid=(c.c_ubyte*16).from_buffer_copy(uuid.UUID('770aae78-f26f-4dba-a829-253c83d1b387').bytes_le)
    create=c.WinDLL('dxgi').CreateDXGIFactory1;create.argtypes=[c.c_void_p,c.POINTER(c.c_void_p)];create.restype=c.c_long
    if create(c.byref(iid),c.byref(factory))<0:raise RuntimeError('Cannot enumerate DXGI adapters')
    def method(obj,index,restype,*types):
        ptr=c.cast(obj,c.POINTER(c.POINTER(c.c_void_p))).contents[index]
        return c.WINFUNCTYPE(restype,c.c_void_p,*types)(ptr)
    output=[]
    try:
        for index in range(16):
            adapter=c.c_void_p();hr=method(factory,12,c.c_long,c.c_uint,c.POINTER(c.c_void_p))(factory,index,c.byref(adapter))
            if hr<0:break
            try:
                desc=Description();hr=method(adapter,10,c.c_long,c.POINTER(Description))(adapter,c.byref(desc))
                if hr<0:raise RuntimeError('Cannot read DXGI adapter description')
                output.append(dict(index=index,name=desc.name,vendor=desc.vendor,dedicated_video_bytes=desc.dedicated_video))
            finally:method(adapter,2,c.c_ulong)(adapter)
    finally:method(factory,2,c.c_ulong)(factory)
    return output

def nvidia_adapter():
    return next(a for a in adapters() if a['vendor']==0x10de)

if __name__=='__main__':
    import json
    print(json.dumps(adapters(),ensure_ascii=False))
