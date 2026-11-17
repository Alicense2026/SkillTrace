"""读取 JSON / 中文列名 CSV；不猜测或重写集成结论。"""
import csv
import json
from pathlib import Path

CSV_COLUMNS = {'GitHub仓库名':'github_repo','GitHub URL':'github_url','GitHub许可证':'github_license',
               'AI模型/数据集/工具名':'artifact_name','资产URL':'artifact_url','资产许可证':'artifact_license',
               '调用方式':'integration','代码集成是否修改':'modified','调用证据':'evidence','批次':'batch'}


def load_input(path):
    source=Path(path)
    if source.is_dir():
        if (source/'result.json').exists():source=source/'result.json'
        else:source=source/'result.csv'
    if source.suffix.lower()=='.json':
        data=json.loads(source.read_text(encoding='utf-8-sig'))
    elif source.suffix.lower()=='.csv':
        with source.open(encoding='utf-8-sig',newline='') as f:
            reader=csv.DictReader(f)
            if reader.fieldnames and {'GitHub许可证','资产许可证原文标题/标签','调用方式（代码修改）','数量'}<=set(reader.fieldnames):
                from .llm.aggregate_input import adapt_aggregate_rows
                rows=adapt_aggregate_rows(list(reader),source)
                data={'rows':rows,'summary':{'rows':len(rows),'input_format':'license_combination_csv',
                                             'represented_relationships':sum(r['_aggregate_weight'] for r in rows),
                                             'skipped_unmapped_groups':sum(bool(r['_aggregate_skip_reason']) for r in rows)}}
                return data,source
            required=set(CSV_COLUMNS)-{'批次'}
            if not required<=set(reader.fieldnames or []):raise ValueError('CSV missing required chain columns')
            rows=[]
            for line,row in enumerate(reader,2):
                if None in row or any(row.get(k) is None for k in required):raise ValueError(f'Malformed CSV record at line {line}')
                normalized={target:row.get(header,'') for header,target in CSV_COLUMNS.items()}
                normalized['artifact_kind']='unspecified'
                rows.append(normalized)
        data={'rows':rows,'summary':{'rows':len(rows),'input_format':'csv'}}
    else:raise ValueError('Only .json or .csv chain input is supported')
    if not isinstance(data,dict) or not isinstance(data.get('rows'),list):raise ValueError('Input requires rows array')
    return data,source
