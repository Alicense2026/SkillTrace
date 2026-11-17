"""无密钥 TOML 配置；明确端点路径，不猜测 /v1 或切换模型。"""
from dataclasses import dataclass, asdict
import os
from pathlib import Path
import re
import tomllib
from urllib.parse import urlsplit

@dataclass(frozen=True)
class ExperimentConfig:
    base_url: str = 'https://api.example.invalid'
    responses_path: str = '/responses'
    model: str = 'gpt-6-luna'
    api_key_env: str = 'LICENSE_API_KEY'
    api_key_file: str | None = None
    reasoning_effort: str = 'medium'
    max_output_tokens: int = 8192
    timeout_seconds: int = 120
    max_retries: int = 2
    max_input_chars: int = 180000

    @property
    def endpoint(self):
        return self.base_url.rstrip('/') + self.responses_path

    def public_dict(self):
        return asdict(self)

    def api_key(self):
        value = os.environ.get(self.api_key_env, '').strip()
        if value:
            return value
        if self.api_key_file:
            try:
                # The local file may be plain text or RTF. Extract only a token-shaped
                # credential and never include file contents in errors or logs.
                contents = Path(self.api_key_file).read_text(encoding='utf-8', errors='ignore')
            except OSError:
                raise ValueError('API key file is unavailable') from None
            candidates = set(re.findall(r'(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{20,}(?![A-Za-z0-9_-])', contents))
            if len(candidates) == 1:
                return candidates.pop()
            if len(candidates) > 1:
                raise ValueError('API key file contains multiple candidate tokens')
            raise ValueError('No API key token found in configured API key file')
        raise ValueError(f'Missing environment variable: {self.api_key_env}')

    def validate(self):
        for name in ('base_url','responses_path','model','api_key_env','reasoning_effort'):
            if not isinstance(getattr(self,name),str):raise ValueError('Invalid '+name)
        if self.api_key_file is not None and not isinstance(self.api_key_file, str):
            raise ValueError('Invalid api_key_file')
        u = urlsplit(self.base_url)
        if u.scheme != 'https' or not u.netloc or u.username or u.password or u.query or u.fragment:
            raise ValueError('base_url must be HTTPS without credentials/query/fragment')
        if not self.responses_path.startswith('/') or '?' in self.responses_path or '#' in self.responses_path or '://' in self.responses_path:
            raise ValueError('responses_path must be an absolute URL path')
        if not self.model or not self.api_key_env: raise ValueError('model and api_key_env are required')
        if self.reasoning_effort not in {'none','low','medium','high','xhigh','max'}: raise ValueError('Invalid reasoning_effort')
        for name in ('max_output_tokens','timeout_seconds','max_input_chars'):
            if type(getattr(self,name)) is not int or getattr(self,name) <= 0: raise ValueError('Invalid '+name)
        if type(self.max_retries) is not int or not 0 <= self.max_retries <= 5: raise ValueError('max_retries must be 0..5')
        return self


def load_config(path):
    config_path = Path(path).resolve()
    data = tomllib.loads(config_path.read_text(encoding='utf-8-sig'))
    if set(data) != {'experiment'} or not isinstance(data['experiment'],dict):
        raise ValueError('Config must have one [experiment] table')
    try:
        values = dict(data['experiment'])
        if values.get('api_key_file'):
            key_path = Path(values['api_key_file']).expanduser()
            if not key_path.is_absolute():
                key_path = config_path.parent / key_path
            values['api_key_file'] = str(key_path.resolve())
        return ExperimentConfig(**values).validate()
    except TypeError as exc: raise ValueError('Unknown configuration field') from exc
