"""Bounded saved-PNG crops for OCR. No desktop, focus or input APIs."""
import hashlib,json,struct,zlib
from pathlib import Path

def crop_saved_png(source,output,rect,scale=3,*,budget_root=None):
    source=Path(source);output=Path(output)
    data=source.read_bytes()
    if len(data)>16*1024*1024 or data[:8]!=b'\x89PNG\r\n\x1a\n':raise ValueError('unsupported_png')
    offset=8;packed=bytearray();header=None
    while offset<len(data):
        size=struct.unpack('>I',data[offset:offset+4])[0]
        kind=data[offset+4:offset+8];body=data[offset+8:offset+8+size]
        crc=data[offset+8+size:offset+12+size]
        if len(body)!=size or len(crc)!=4 or zlib.crc32(kind+body)!=struct.unpack('>I',crc)[0]:raise ValueError('png_crc')
        offset+=12+size
        if kind==b'IHDR':header=struct.unpack('>IIBBBBB',body)
        elif kind==b'IDAT':packed.extend(body)
        elif kind==b'IEND':break
    if header is None:raise ValueError('png_header_missing')
    width,height,depth,color,compression,filter_method,interlace=header
    if (width,height)!=(1450,869) or depth!=8 or color not in (2,6) or any((compression,filter_method,interlace)):
        raise ValueError('unsupported_capture_geometry_or_encoding')
    x,y,w,h=rect
    if not all(type(n)is int for n in (x,y,w,h,scale)) or scale not in (1,2,3):raise ValueError('crop_parameters')
    if not(0<=x<x+w<=width and 0<=y<y+h<=height) or max(w,h)*scale>2400:raise ValueError('crop_bounds')
    channels=3 if color==2 else 4;stride=width*channels;limit=(stride+1)*height
    dec=zlib.decompressobj();raw=dec.decompress(packed,limit+1)
    if len(raw)!=limit or not dec.eof or dec.unconsumed_tail:raise ValueError('png_data_length')
    previous=bytearray(stride);pixels=[]
    def paeth(a,b,c):
        p=a+b-c;pa,pb,pc=abs(p-a),abs(p-b),abs(p-c)
        return a if pa<=pb and pa<=pc else b if pb<=pc else c
    for row_index in range(height):
        start=row_index*(stride+1);mode=raw[start];row=bytearray(raw[start+1:start+1+stride])
        if mode not in range(5):raise ValueError('png_filter')
        for i in range(stride):
            left=row[i-channels] if i>=channels else 0;above=previous[i];diagonal=previous[i-channels] if i>=channels else 0
            prediction=(0,left,above,(left+above)//2,paeth(left,above,diagonal))[mode]
            row[i]=(row[i]+prediction)&255
        if y<=row_index<y+h:
            expanded=b''.join(bytes(row[j*channels:j*channels+3])*scale for j in range(x,x+w))
            pixels.extend([b'\x00'+expanded]*scale)
        previous=row
    def chunk(kind,body):return struct.pack('>I',len(body))+kind+body+struct.pack('>I',zlib.crc32(kind+body))
    encoded=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',w*scale,h*scale,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(b''.join(pixels)))+chunk(b'IEND',b'')
    from runtime.custom_setup import ensure_capture_capacity
    ensure_capture_capacity(output.parent if budget_root is None else budget_root,frames=1,frame_reserve=len(encoded))
    with output.open('xb')as f:f.write(encoded)
    ensure_capture_capacity(output.parent if budget_root is None else budget_root,frames=0)
    record={'source_image':str(source),'source_sha256':hashlib.sha256(data).hexdigest(),
            'image':str(output),'image_sha256':hashlib.sha256(encoded).hexdigest(),
            'source_rect':list(rect),'scale':scale,'transform':'nearest_neighbor_only','input_calls':0}
    with output.with_suffix('.roi.json').open('x',encoding='utf-8')as f:json.dump(record,f,indent=2)
    return record
