"""Read embedded xLights timing data; never execute sequence contents."""
from __future__ import annotations
import array
import ctypes
import ctypes.util
import json
import math
from pathlib import Path
import re
import wave
import xml.etree.ElementTree as ET

MAX_UPLOAD = 512 * 1024 * 1024
MAX_XML = 24 * 1024 * 1024
PHONEMES = {'AI', 'E', 'O', 'U', 'L', 'FV', 'WQ', 'MBP', 'etc', 'rest'}
CAPS = {'AI':100, 'O':100, 'E':75, 'U':75, 'L':75, 'FV':50, 'WQ':50, 'etc':50}

def basename(name: str) -> str:
    if not isinstance(name, str) or not name or len(name.encode("utf-8"))>160 or name in {'.','..'} or any(c in name for c in '/\\') or any(ord(c)<32 or ord(c)==127 for c in name):
        raise ValueError('Use a filename without folders')
    return name

def decompress(data: bytes) -> bytes:
    lib = ctypes.util.find_library('zstd')
    if not lib:
        raise ValueError('The system zstd library is required for embedded xLights data')
    z=ctypes.CDLL(lib)
    z.ZSTD_getFrameContentSize.argtypes=[ctypes.c_void_p,ctypes.c_size_t]
    z.ZSTD_getFrameContentSize.restype=ctypes.c_ulonglong
    size=z.ZSTD_getFrameContentSize(data,len(data))
    if not 0 < size <= MAX_XML:
        raise ValueError('Embedded xLights data exceeds the supported size')
    z.ZSTD_decompress.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p,ctypes.c_size_t]
    z.ZSTD_decompress.restype=ctypes.c_size_t
    out=ctypes.create_string_buffer(size)
    actual=z.ZSTD_decompress(out,size,data,len(data))
    if actual!=size:
        raise ValueError('Invalid compressed xLights data')
    return out.raw[:actual]

def inspect(path: Path) -> dict:
    size=path.stat().st_size
    if size>MAX_UPLOAD: raise ValueError('FSEQ exceeds 512 MB')
    with path.open('rb') as f:
        base=f.read(32)
        if len(base)<32 or base[:4]!=b'PSEQ' or base[7]!=2:
            raise ValueError('This importer requires an FSEQ v2 file with embedded xLights data')
        offset=int.from_bytes(base[4:6],'little');fixed=int.from_bytes(base[8:10],'little')
        frames=int.from_bytes(base[14:18],'little');step=base[18];duration=frames*step
        if not 32<=fixed<=offset<=size or not 0<duration<=1800000 or step==0:
            raise ValueError('Invalid or unsupported FSEQ duration/header (maximum 30 minutes)')
        f.seek(0);header=f.read(offset);i=fixed;xml=None;media=''
        while i+4<=offset:
            length=int.from_bytes(header[i:i+2],'little')
            if length==0:break
            if length<4 or i+length>offset:raise ValueError('Truncated FSEQ metadata')
            code=header[i+2:i+4];data=header[i+4:i+length]
            if code==b'mf':
                media=data.rstrip(b'\0').decode('utf-8',errors='replace').replace('\\','/').split('/')[-1]
            if code==b'XS':xml=decompress(data)
            if code==b'ED' and data[:2]==b'XS':
                if len(data)!=14:raise ValueError('Invalid extended metadata')
                start=int.from_bytes(data[2:10],'little');count=int.from_bytes(data[10:14],'little')
                if not 0<count<=MAX_XML or start<offset or start+count>size:raise ValueError('Invalid embedded data range')
                f.seek(start);xml=decompress(f.read(count))
            i+=length
    if xml is None:raise ValueError('No embedded xLights sequence. Export with embedded sequence data, or use an audio file.')
    try: xml = xml.decode('utf-8-sig', errors='strict')
    except UnicodeError as exc: raise ValueError('Embedded xLights XML must use UTF-8') from exc
    if '\x00' in xml or '<!DOCTYPE' in xml.upper() or '<!ENTITY' in xml.upper():raise ValueError('XML declarations/entities are unsupported')
    try:root=ET.fromstring(xml)
    except ET.ParseError as exc:raise ValueError('Invalid embedded sequence XML') from exc
    if root.tag != 'xsequence':raise ValueError('Invalid xLights sequence document')
    if sum(1 for _ in root.iter())>200000:raise ValueError('Too many elements in embedded sequence')
    tracks=[]
    total_cues=0
    for element in root.iter('Element'):
        if element.get('type')!='timing':continue
        for index,layer in enumerate(element.findall('EffectLayer')):
            effects=layer.findall('Effect')
            if not effects or len(effects)>100000:continue
            labels={e.get('label','') for e in effects}
            if not labels.intersection(PHONEMES-{'rest'}) or not labels.issubset(PHONEMES|{''}):continue
            cues=[]
            previous_end=0
            adjusted=0
            for e in effects:
                try:start=int(e.get('startTime',''));end=int(e.get('endTime',''))
                except ValueError as exc:raise ValueError('Invalid cue timing') from exc
                if not 0<=start<end<=86400000:raise ValueError('Invalid cue range')
                label=e.get('label','')
                if cues and [start,min(end,duration),label]==cues[-1]:
                    adjusted+=1
                    continue
                if start<previous_end:
                    if not cues or start<=cues[-1][0] or previous_end-start>step:
                        raise ValueError('Ambiguous overlapping or unsorted phoneme cues')
                    cues[-1][1]=start
                    adjusted+=1
                previous_end=end
                if start>=duration:continue
                cues.append([start,min(end,duration),e.get('label','')])
            if not cues:continue
            total_cues+=len(cues)
            if total_cues>100000 or len(tracks)>=128:raise ValueError('Too many phoneme tracks or cues')
            name=element.get('name','Unnamed')[:160]
            if any(t['name']==name for t in tracks):raise ValueError('Ambiguous duplicate phoneme track names')
            tracks.append({'name':name,'layer':index+1,'cue_count':len(cues),'adjusted_cues':adjusted,'cues':cues})
    if not tracks:raise ValueError('No phoneme layers found. Use a singing timing track with phonemes.')
    return {'duration_ms':duration,'step_ms':step,'media_name':media,'tracks':tracks}

def summary(info:dict)->dict:
    return {**info,'tracks':[{k:v for k,v in t.items() if k!='cues'} for t in info['tracks']]}

def render(info:dict,track_name:str,path:Path,offset_ms:int=0)->None:
    if type(offset_ms) is not int or not -5000<=offset_ms<=5000:raise ValueError('Timing adjustment must be between -5000 and 5000 ms')
    track=next((t for t in info['tracks'] if t['name']==track_name),None)
    if track is None:raise ValueError('Choose one of the available phoneme tracks')
    sr=22050;count=round(info['duration_ms']*sr/1000);audio=array.array('h',[0])*count
    for start,end,label in track['cues']:
        if label in {'MBP','rest',''}:continue
        length=min(CAPS.get(label,50),(end-start)*.65)
        begin=start+offset_ms;stop=begin+length
        lo=max(0,round(begin*sr/1000));hi=min(count,round(stop*sr/1000))
        for i in range(lo,hi):
            ramp=max(0,min(1,(i-begin*sr/1000)/(sr*.002),(stop*sr/1000-i)/(sr*.002)))
            audio[i]=int(6500*ramp*math.sin(2*math.pi*200*i/sr))
    import sys
    if sys.byteorder!='little':audio.byteswap()
    with wave.open(str(path),'wb') as w:
        w.setparams((1,2,sr,0,'NONE','not compressed'));w.writeframes(audio.tobytes())

class SequenceLibrary:
    def __init__(self,data_dir:Path):
        self.root=Path(data_dir)/'fseq-imports';self.map_path=Path(data_dir)/'fpp-sequence-map.json'
    async def receive(self,chunks)->dict:
        import uuid
        self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        token=uuid.uuid4().hex;path=self.root/(token+'.fseq');total=0
        try:
            with path.open('xb') as f:
                path.chmod(0o600)
                async for chunk in chunks:
                    total+=len(chunk)
                    if total>MAX_UPLOAD:raise ValueError('FSEQ exceeds 512 MB')
                    import shutil
                    if shutil.disk_usage(self.root).free < len(chunk)+1024**3:raise ValueError('Not enough free space to import sequence')
                    f.write(chunk)
            from .fseq_worker import run_worker
            target=self.root/(token+'.json')
            try:
                await run_worker('inspect',str(path),str(target))
                info=json.loads(target.read_text())
            except BaseException:
                target.unlink(missing_ok=True)
                raise
            self.prune(exclude=target)
            return {'id':token,**summary(info)}
        finally:path.unlink(missing_ok=True)
    def prune(self, *, exclude: Path):
        # Imported metadata is a bounded temporary cache; linked WAVs are separate.
        import time
        paths=sorted(self.root.glob('*.json'),key=lambda p:p.stat().st_mtime,reverse=True)
        for index,path in enumerate(paths):
            if path!=exclude and (index>=31 or time.time()-path.stat().st_mtime>86400):
                path.unlink(missing_ok=True)

    def info_path(self,token:str)->Path:
        if not isinstance(token,str) or not re.fullmatch('[a-f0-9]{32}',token):raise ValueError('Invalid imported sequence identifier')
        return self.root/(token+'.json')

    def load(self,token:str)->dict:
        try:return json.loads(self.info_path(token).read_text())
        except (FileNotFoundError,json.JSONDecodeError) as exc:raise ValueError('Import the sequence first') from exc
    def mapping(self)->dict:
        try:
            if self.map_path.stat().st_size>1024**2:raise ValueError('Sequence links file exceeds supported size')
            result=json.loads(self.map_path.read_text())
            if not isinstance(result,dict) or len(result)>4096:raise ValueError('Invalid sequence links')
            for media,entry in result.items():
                basename(media)
                if not isinstance(entry,dict):raise ValueError('Invalid sequence link')
                basename(entry.get('file'));
                if not isinstance(entry.get('track'),str):raise ValueError('Invalid singing track')
            return result
        except FileNotFoundError:return {}
        except (ValueError,OSError) as exc:raise ValueError('Sequence links file is damaged or unreadable; restore it before changing links') from exc
    def unlink(self,media:str):
        basename(media);mapping=self.mapping();mapping.pop(media,None);self.save_mapping(mapping)

    def save_mapping(self,mapping:dict):
        self.map_path.parent.mkdir(parents=True,exist_ok=True)
        import os
        temp=self.map_path.with_suffix('.tmp')
        try:
            with temp.open('w') as output:
                temp.chmod(0o600);json.dump(mapping,output);output.flush();os.fsync(output.fileno())
            temp.replace(self.map_path)
        finally:
            temp.unlink(missing_ok=True)

    def link(self,media:str,generated:str,track:str):
        basename(media);basename(generated);mapping=self.mapping();mapping[media]={'file':generated,'track':track,'source':'sequence'}
        self.save_mapping(mapping)
