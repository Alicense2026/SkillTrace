"""Responses API 标准库 HTTP 客户端；不读 auth.json，不打印密钥。"""
import json
from pathlib import Path
import re
import ssl
import time
from urllib.request import Request, build_opener, HTTPRedirectHandler, HTTPSHandler
from urllib.error import HTTPError, URLError

class APIError(RuntimeError):
    def __init__(self,message,status=None):super().__init__(message);self.status=status

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):return None


def secure_opener():
    """Use normal TLS verification, falling back to macOS's CA bundle if Python lacks one."""
    context = ssl.create_default_context()
    paths = ssl.get_default_verify_paths()
    configured_ca = Path(paths.cafile) if paths.cafile else None
    system_ca = Path('/etc/ssl/cert.pem')
    if (not configured_ca or not configured_ca.is_file()) and system_ca.is_file():
        context = ssl.create_default_context(cafile=str(system_ca))
    return build_opener(NoRedirect(), HTTPSHandler(context=context))

class ResponsesClient:
    def __init__(self,config,opener=None,sleep=time.sleep):
        self.config=config;self.opener=opener or secure_opener();self.sleep=sleep

    def create(self,body):
        key=self.config.api_key()
        payload=json.dumps(body,ensure_ascii=False).encode('utf-8')
        for attempt in range(self.config.max_retries+1):
            request=Request(self.config.endpoint,data=payload,method='POST',headers={
                'Authorization':'Bearer '+key,'Content-Type':'application/json','Accept':'application/json'})
            try:
                with self.opener.open(request,timeout=self.config.timeout_seconds) as response:
                    raw=response.read(16*1024*1024+1)
                    if len(raw)>16*1024*1024:raise APIError('Response exceeded 16 MiB limit')
                    try:obj=json.loads(raw.decode('utf-8'))
                    except (UnicodeError,ValueError) as exc:raise APIError('Server returned non-JSON response') from exc
                    if not isinstance(obj,dict):raise APIError('Response must be an object')
                    return obj
            except HTTPError as exc:
                code=exc.code
                raw_error=exc.read(8192)
                exc.close()
                if code not in {429,500,502,503,504} or attempt==self.config.max_retries:
                    detail=''
                    try:
                        error_obj=json.loads(raw_error.decode('utf-8'))
                        candidate=error_obj.get('code') if isinstance(error_obj,dict) else None
                        if isinstance(candidate,str) and re.fullmatch(r'[A-Za-z0-9_.-]{1,64}',candidate):
                            detail=f' ({candidate})'
                    except (UnicodeError,ValueError):
                        pass
                    raise APIError(f'HTTP {code}{detail}; inspect endpoint/model/account configuration (response body omitted)',code) from None
            except (URLError,TimeoutError,OSError):
                if attempt==self.config.max_retries:raise APIError('Network/timeout failure (details omitted)') from None
            self.sleep(min(2**attempt,8))
        raise APIError('Retry limit exceeded')


def extract_text(response):
    if response.get('status')!='completed':raise APIError('Response not completed; no analysis accepted')
    if not isinstance(response.get('output'), list):raise APIError('Invalid Responses output array')
    texts=[]
    for item in response.get('output',[]):
        if not isinstance(item,dict):raise APIError('Invalid Responses output item')
        if item.get('type')!='message':continue
        if not isinstance(item.get('content'),list):raise APIError('Invalid message content array')
        for block in item['content']:
            if not isinstance(block,dict):raise APIError('Invalid message content item')
            if block.get('type')=='refusal':raise APIError('Model refusal; no analysis accepted')
            if block.get('type')=='output_text' and isinstance(block.get('text'),str):texts.append(block['text'])
    if not texts:raise APIError('No output_text in completed Responses output')
    return ''.join(texts)
