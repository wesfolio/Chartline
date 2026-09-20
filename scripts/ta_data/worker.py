"""One bounded AKShare call in a disposable subprocess; preserve public responses."""
import sys, json, time, hashlib, inspect, traceback, re
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

def utc_now(): return datetime.now(timezone.utc).isoformat()
def safe_url(url):
    p=urlsplit(url)
    query=[(k,'REDACTED' if any(w in k.lower() for w in ('token','key','auth','password','secret','cookie')) else v) for k,v in parse_qsl(p.query,keep_blank_values=True)]
    return urlunsplit((p.scheme,p.hostname or '',p.path,urlencode(query),''))

def main():
    job_path=Path(sys.argv[1]);dest=Path(sys.argv[2]);dest.mkdir(parents=True,exist_ok=False)
    job=json.loads(job_path.read_text(encoding='utf8'));start=utc_now();events=[]
    result={'job':job,'started_at':start,'status':'FETCH_ERROR','http_capture_scope':'requests.Session.send only; curl transport if used is not captured'}
    (dest/'job.json').write_text(json.dumps(job,ensure_ascii=False,indent=2),encoding='utf8')
    try:
        import requests, akshare as ak
        original=requests.sessions.Session.send
        def capture(session,request,**kwargs):
            if len(events)>=25:raise RuntimeError('Per-job HTTP request budget exhausted')
            if kwargs.get('timeout') is None:kwargs['timeout']=(5,15)
            entry={'url':safe_url(request.url),'method':request.method,'started_at':utc_now()};events.append(entry)
            try:
                response=original(session,request,**kwargs);payload=response.content
                entry.update(status_code=response.status_code,bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),received_at=utc_now())
                if len(payload)<=8_000_000:
                    filename=f'http-{len(events):02d}.body';(dest/filename).write_bytes(payload);entry['body_file']=filename
                else:entry['body_file']=None;entry['not_saved_reason']='Response exceeded 8MB capture budget'
                return response
            except Exception as exc:
                entry['error_type']=type(exc).__name__;raise
            finally:(dest/'http-log.json').write_text(json.dumps(events,ensure_ascii=False,indent=2),encoding='utf8')
        requests.sessions.Session.send=capture
        function=getattr(ak,job['api']);source=inspect.getsource(function)
        (dest/'adapter-source.py').write_text(source,encoding='utf8')
        result['akshare_version']=ak.__version__;result['adapter_source_sha256']=hashlib.sha256(source.encode()).hexdigest()
        df=function(**job['kwargs'])
        if not hasattr(df,'to_json'):raise TypeError('AKShare did not return a DataFrame')
        df.to_json(dest/'api-return.json',orient='table',date_format='iso',force_ascii=False,double_precision=15)
        result.update(status='EMPTY' if df.empty else 'FETCH_OK',rows=len(df),columns=list(df.columns),api_return_sha256=hashlib.sha256((dest/'api-return.json').read_bytes()).hexdigest())
    except Exception as exc:
        message=re.sub(r'(https?://)[^/@\s]+:[^/@\s]+@',r'\1REDACTED@',str(exc))
        result.update(error_type=type(exc).__name__,error_message=message[:800])
    result['finished_at']=utc_now();result['http_requests']=len(events)
    (dest/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({k:result.get(k) for k in ('status','rows','error_type','error_message')},ensure_ascii=False))

if __name__=='__main__':main()
