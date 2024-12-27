# -*- coding: utf-8 -*-
#!/usr/bin/env python

# python3 src/retrieve_latin_alphabet.py ./res/fonts/mplus-1m-medium.ttf
import os
import sys
import re
import argparse
import subprocess
import json
import utility
import path as p
import getSystem as gs

# できた
# cat alphabet4pinyin.json | jq '.glyf | with_entries(select(.key|match("^a$|^b$")))' > out.json

# 一文字なら、これの方がわかりやすい。置換のときに使えるかな
# cat alphabet4pinyin.json | jq '.glyf | with_entries(select(.key == "a"))' > out.json

"""
指定された任意のフォントからピンイン表示のために利用するグリフを取得する
グリフ名はcid のままだとわかりづらいので、unicode に修正する
"""

ALPHABET_FOR_PINYIN_JSON = "alphabet4pinyin.json"
OUTPUT_JSON = "output_for_pinyin.json"

# 呣 m̀, 嘸 m̄ を使うが、これは unicode ではないので除外する。グリフが収録されていない事が多い。
ALPHABET = ["a","ā","á","ǎ","à","b","c","d","e","ē","é","ě","è","f","g","h","i","ī","í","ǐ","ì","j","k","l","m","ḿ","n","ń","ň","ǹ","o","ō","ó","ǒ","ò","p","q","r","s","t","u","ū","ú","ǔ","ù","ü","ǖ","ǘ","ǚ","ǜ","v","w","x","y","z"]

UNICODE_ALPHABET = [ord(c) for c in ALPHABET]

def process_shell(cmd=""):
    # print('start')
    completed_process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    # print(f'returncode: {completed_process.returncode},stdout: {completed_process.stdout},stderr: {completed_process.stderr}')
    if b'' != completed_process.stderr:
        print("line 38")
        raise Exception(completed_process.stderr)
    return completed_process.stdout

def convert_otf2json(source_font_name, output_json):
    cmd = "otfccdump -o {} --pretty {}".format(output_json, source_font_name)
    try:
        process_shell(cmd)
    except Exception as e:
        print("line 46")
        print(e)

# cmap の大きさなら、全部取得しても 65536 程度だから、フィルターしなくてもいいな
def get_cmap_table(source_font_json):
    if gs.SYSTEM_NAME == gs.W:
        cmd = 'type {} | jq ".cmap" '.format(source_font_json)
    else:
        cmd = 'cat {} | jq ".cmap" '.format(source_font_json)
    try:
        cmap_table = json.loads( process_shell(cmd) )
    except Exception as e:
        print("line 55")
        print(e)
    return cmap_table

def expand_pattern_list2match_pattern(ALPHABET):
    match_pattern = ""
    for c in ALPHABET:
        match_pattern += "^{}$|".format(c) if ALPHABET[-1] != c else "^{}$".format(c)
    # return ' "{}" '.format(match_pattern)
    return match_pattern  # 使用原版的python


def get_reversed_cmap_table():
    output_json = os.path.join(p.DIR_TEMP, OUTPUT_JSON)
    cmap_table = get_cmap_table( output_json )

    reversed_cmap_table = {}
    for ucode in UNICODE_ALPHABET:
        cid = cmap_table[str(ucode)]
        reversed_cmap_table.update( { cid : "py_alphablet_" + utility.SIMPLED_ALPHABET[chr(ucode)] } )

    return reversed_cmap_table

def rename_cid_of_alphabet_for_pinyin(alphabet_glyf4pinyin_json):
    with open(alphabet_glyf4pinyin_json, mode='r', encoding='utf-8') as read_file:
        glyf_json = json.load(read_file) 
    
    reversed_cmap_table = get_reversed_cmap_table()

    new_glyf_json = {}
    for cid, glyf_data in glyf_json.items():
        new_glyf_json.update( {reversed_cmap_table[cid] : glyf_data} )
    
    with open(alphabet_glyf4pinyin_json, mode='w', encoding='utf-8') as write_file:
        json.dump(new_glyf_json, write_file, indent=4, ensure_ascii=False)


def filter_glyf_by_pattern(input_json_path, output_json_path, match_pattern):
    # 读取 JSON 文件
    with open(input_json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # 获取 glyf 表
    glyf_table = data.get('glyf', {})

    # 编译正则表达式
    pattern = re.compile(match_pattern)

    # 筛选 glyf 表中符合条件的项
    filtered_glyf = {key: value for key, value in glyf_table.items() if pattern.match(key)}

    # 创建新的 JSON 结构
    filtered_data = filtered_glyf

    # 将结果写入到新的 JSON 文件中
    with open(output_json_path, 'w', encoding='utf-8') as f:
        json.dump(filtered_data, f, ensure_ascii=False, indent=4)


def make_alphabet_glyf_json(source_font_name):
    output_json = os.path.join(p.DIR_TEMP, OUTPUT_JSON)
    convert_otf2json( source_font_name, output_json )
    cmap_table = get_cmap_table( output_json )
    cid_table_of_alphabet  = [cmap_table[str(ucode)] for ucode in UNICODE_ALPHABET]
    match_pattern = expand_pattern_list2match_pattern( cid_table_of_alphabet )
    
    alphabet_glyf4pinyin_json = os.path.join(p.DIR_TEMP, ALPHABET_FOR_PINYIN_JSON)
    # match_pattern = ' "^a$|^b$" '
    # cmd = 'cat {} | jq ".glyf | with_entries(select(.key|match({})))" > {}'.format(output_json, match_pattern, alphabet_glyf4pinyin_json)
    try:
        # print(cmd)
        # process_shell(cmd)
        filter_glyf_by_pattern(output_json, alphabet_glyf4pinyin_json, match_pattern)
        rename_cid_of_alphabet_for_pinyin(alphabet_glyf4pinyin_json)
    except Exception as e:
        print("line 130")
        print(e)

def parse_args(args):
    parser = argparse.ArgumentParser(
        description="Convert OpenType font (.otf/.ttf) to .json ")
    parser.add_argument(
        "source_font_name", metavar="source_font_name", help="Source font name")

    return parser.parse_args(args)

def main(args=None):
    options = parse_args(args)
    # 変換するフォント
    source_font_name = options.source_font_name
    extension = os.path.splitext(source_font_name)[-1]

    if (".otf" == extension or ".ttf" == extension):
        if not os.path.exists(p.DIR_TEMP):
            os.makedirs(p.DIR_TEMP)
        make_alphabet_glyf_json(source_font_name)
        
    else:
        print("invalid argument:")
        print("  input file is font file (.otf/.ttf) only.")

if __name__ == "__main__":
    sys.exit(main())