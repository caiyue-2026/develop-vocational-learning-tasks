#!/usr/bin/env python3
"""Check a learning-task design record; does not assess pedagogical validity."""
import argparse
import json
import math
import re
import sys
from pathlib import Path

SECTIONS = ['学习情境', '学习目标', '任务要求', '任务分工', '获取信息',
            '制定计划', '任务实施', '检查交付', '评价反思', '相关知识与技术资料']
STAGES = SECTIONS[4:8]
BLOOM = {'记忆', '理解', '应用', '分析', '评价', '创造'}
PLACEHOLDER = re.compile(r'替换为|待补充|待撰写|TODO|TBD|\.\.\.|……')


def check(data):
    errors, warnings = [], []
    if not isinstance(data, dict):
        return ['开发记录必须为 JSON 对象'], warnings

    def prose(value, label):
        if not isinstance(value, str) or not value.strip():
            errors.append(f'{label}必须为非空文字')
        elif PLACEHOLDER.search(value):
            errors.append(f'{label}含未完成的占位文字')

    def records(value, label):
        if not isinstance(value, list) or not value:
            errors.append(f'{label}必须为非空列表')
            return []
        result = []
        for i, row in enumerate(value, 1):
            if not isinstance(row, dict):
                errors.append(f'{label}第{i}项必须为对象')
            else:
                result.append(row)
        return result

    def collect(rows, label, pattern):
        ids = set()
        for row in rows:
            key = row.get('id')
            if not isinstance(key, str) or not re.fullmatch(pattern, key):
                errors.append(f'{label}编号格式无效：{key!r}')
            elif key in ids:
                errors.append(f'{label}编号重复：{key}')
            else:
                ids.add(key)
        return ids

    def links(row, field, allowed, label, required=True):
        values = row.get(field)
        if not isinstance(values, list) or (required and not values):
            errors.append(f'{label}缺少有效{field}列表')
            return set()
        valid = set()
        for value in values:
            if not isinstance(value, str) or value not in allowed:
                errors.append(f'{label}引用不存在的{field}：{value!r}')
            else:
                valid.add(value)
        return valid

    prose(data.get('title'), '任务名称')
    if data.get('sections') != SECTIONS:
        errors.append('十部分标题或顺序与固定体例不符')
    objs = records(data.get('objectives'), '学习目标')
    questions = records(data.get('questions'), '引导问题')
    knowledge = records(data.get('knowledge_sections'), '理论小节')
    sources = records(data.get('sources'), '资料来源')
    obj_ids = collect(objs, '目标', r'O[1-9]\d*')
    question_ids = collect(questions, '问题', r'Q\d{2,}')
    know_ids = collect(knowledge, '知识', r'K[1-9]\d*(?:\.[1-9]\d*)*')
    source_ids = collect(sources, '来源', r'S[1-9]\d*')
    for row in objs:
        prose(row.get('text'), f'{row.get("id")}目标')
    for row in sources:
        label = str(row.get('id'))
        for field in ['title', 'issuer', 'locator', 'version_or_date', 'scope']:
            prose(row.get(field), label + '.' + field)
        if not isinstance(row.get('status'), str) or row.get('status') not in {'已提供', '已核实', '待核实'}:
            errors.append(f'{label}来源状态无效')
        elif row.get('status') != '已核实':
            warnings.append(f'{label}尚未独立核实，需判断适用范围及是否影响实施')
    activity_coverage, theory_coverage, assessed = set(), set(), set()
    stage_counts = dict.fromkeys(STAGES, 0)
    for i, row in enumerate(questions, 1):
        label = str(row.get('id'))
        if row.get('id') != f'Q{i:02d}':
            errors.append(f'{label}问题编号须从 Q01 连续递增')
        stage = row.get('stage')
        if stage not in STAGES + ['评价反思']:
            errors.append(f'{label}环节名称无效')
        elif stage in stage_counts:
            stage_counts[stage] += 1
        if not isinstance(row.get('bloom'), str) or row.get('bloom') not in BLOOM:
            errors.append(f'{label}认知层级无效')
        for field in ['prompt', 'activity', 'evidence']:
            prose(row.get(field), label + '.' + field)
        activity_coverage |= links(row, 'objective_ids', obj_ids, label)
        links(row, 'knowledge_ids', know_ids, label)
    for stage, count in stage_counts.items():
        if not count:
            errors.append(f'{stage}缺少引导问题')
    if question_ids and not any(isinstance(q.get('bloom'), str) and q.get('bloom') in {'分析', '评价', '创造'} for q in questions):
        warnings.append('未记录较高认知要求，请按任务目标检查递进设计')
    for row in knowledge:
        label = str(row.get('id'))
        prose(row.get('title'), label + '.title')
        prose(row.get('body'), label + '.body')
        body = row.get('body', '')
        if isinstance(body, str) and len(body.strip()) < 200:
            warnings.append(f'{label}正文较短，请人工检查是否充分解释概念、原理和方法')
        theory_coverage |= links(row, 'objective_ids', obj_ids, label)
        links(row, 'source_ids', source_ids, label)
    assessment = data.get('assessment')
    if not isinstance(assessment, dict):
        errors.append('缺少 assessment 评价对象')
        assessment = {}
    items = records(assessment.get('items'), '评价项目')
    collect(items, '评价', r'A[1-9]\d*')
    points = []
    for row in items:
        label = str(row.get('id'))
        for field in ['criterion', 'evidence']:
            prose(row.get(field), label + '.' + field)
        assessed |= links(row, 'objective_ids', obj_ids, label)
        value = row.get('points')
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            errors.append(f'{label}分值必须为有限非负数')
        else:
            points.append(value)
    total = assessment.get('max_score')
    if isinstance(total, bool) or not isinstance(total, (int, float)) or not math.isfinite(total) or total <= 0:
        errors.append('评价满分必须为有限正数')
    elif not math.isclose(math.fsum(points), total, abs_tol=0.001):
        errors.append(f'分值合计 {math.fsum(points):g} 与满分 {total:g} 不符')
    for label, covered in [('问题活动', activity_coverage), ('系统理论', theory_coverage), ('评价项目', assessed)]:
        for key in sorted(obj_ids - covered):
            errors.append(f'{key}未被{label}覆盖')
    return errors, warnings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('record', type=Path)
    args = parser.parse_args()
    try:
        data = json.loads(args.record.read_text(encoding='utf-8'))
        errors, warnings = check(data)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(json.dumps({'ok': False, 'errors': [str(exc)], 'warnings': []}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps({'ok': not errors, 'errors': errors, 'warnings': warnings,
                      'scope': '结构校核，不代替教学、理论、技术及版式人工审查'}, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
