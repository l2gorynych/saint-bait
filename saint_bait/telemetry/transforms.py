"""Read bounded Unity transform hierarchies; never invoke or write game code."""
import math
import struct


def rotate(q,v):
    x,y,z,w=q
    a,b,c=v
    tx,ty,tz=2*(y*c-z*b),2*(z*a-x*c),2*(x*b-y*a)
    return a+w*tx+y*tz-z*ty,b+w*ty+z*tx-x*tz,c+w*tz+x*ty-y*tx


def multiply(a,b):
    x,y,z,w=a
    i,j,k,s=b
    return (w*i+x*s+y*k-z*j,w*j-x*k+y*s+z*i,
            w*k+x*j-y*i+z*s,w*s-x*i-y*j-z*k)


def view_angles(rotation):
    x,y,z=rotate(rotation,(0.,0.,1.))
    return math.degrees(math.atan2(x,z)),math.degrees(math.atan2(y,math.hypot(x,z)))


def world_pose(reader,transform):
    if not transform:return None
    native=reader.ptr(transform+16)
    if not native:return None
    data=reader.ptr(native+0x38)
    index=struct.unpack('<i',reader.read(native+0x40,4))[0]
    if not data or not 0<=index<100000:raise ValueError('Invalid transform')
    matrices,parents=struct.unpack('<QQ',reader.read(data+0x18,16))
    seen=set()
    value=None
    rotation=None
    for _ in range(128):
        if not 0<=index<100000 or index in seen:raise ValueError('Invalid transform hierarchy')
        seen.add(index)
        row=struct.unpack('<12f',reader.read(matrices+48*index,48))
        if any(not math.isfinite(v) or abs(v)>1e7 for v in row):raise ValueError('Invalid transform data')
        if abs(sum(v*v for v in row[4:8])-1)>.05:raise ValueError('Invalid transform rotation')
        rotation=row[4:8] if rotation is None else multiply(row[4:8],rotation)
        value=row[:3] if value is None else tuple(a+b for a,b in zip(
            rotate(row[4:8],tuple(v*s for v,s in zip(value,row[8:11]))),row[:3]))
        index=struct.unpack('<i',reader.read(parents+4*index,4))[0]
        if index==-1:
            if any(not math.isfinite(v) or abs(v)>1e7 for v in value):raise ValueError('Invalid world position')
            return value,rotation
    raise ValueError('Transform hierarchy too deep')


def world_position(reader,transform):
    pose=world_pose(reader,transform)
    return pose[0] if pose is not None else None
