"""Bounded snapshots of native managed object lists."""


def object_list(observer,items,maximum=32):
    if not items:return ()
    reader=observer.r
    count=observer.integer(items,'_size')
    version_offset=observer.field(items,'_version')['offset']
    version=reader.read(items+version_offset,4)
    if not 0<=count<=maximum:raise ValueError('Scene list outside bounds')
    field=observer.field(items,'_items')
    array=reader.ptr(items+field['offset']) if field['type_code']==29 else observer.ref(items,'_items')
    if count and (not array or reader.ptr(array+24)<count):raise ValueError('Invalid scene array')
    values=tuple(reader.ptr(array+32+8*i) for i in range(count))
    if version!=reader.read(items+version_offset,4):raise ValueError('Scene list changed')
    return values
