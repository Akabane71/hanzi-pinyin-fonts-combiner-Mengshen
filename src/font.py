# -*- coding: utf-8 -*-
#!/usr/bin/env python'

import shell
import orjson
import os
import re
import pinyin_getter as pg
import pinyin_glyph as py_glyph
import utility
import path as p

class Font():
    def __init__(self, TAMPLATE_MAIN_JSON, TAMPLATE_GLYF_JSON, ALPHABET_FOR_PINYIN_JSON, \
                        PATTERN_ONE_TXT, PATTERN_TWO_JSON, EXCEPTION_PATTERN_JSON):
        self.TAMPLATE_MAIN_JSON     = TAMPLATE_MAIN_JSON
        self.TAMPLATE_GLYF_JSON     = TAMPLATE_GLYF_JSON
        self.PATTERN_ONE_TXT        = PATTERN_ONE_TXT
        self.PATTERN_TWO_JSON       = PATTERN_TWO_JSON
        self.EXCEPTION_PATTERN_JSON = EXCEPTION_PATTERN_JSON
        self.load_json()
        self.cmap_table = self.marged_font["cmap"]
        self.PINYIN_MAPPING_TABLE = pg.get_pinyin_table_with_mapping_table()

        # 発音のグリフを作成する
        pinyin_glyph = py_glyph.PinyinGlyph(TAMPLATE_MAIN_JSON, ALPHABET_FOR_PINYIN_JSON)
        pinyin_glyph.add_pronunciations_to_glyf_table()
        self.pinyin_glyf = pinyin_glyph.get_pronunciations_to_glyf_table()
        print("発音のグリフを作成完了")

        # 定義が重複している文字に関しては、基本的に同一のグリフが使われているはず
        # どれかがグリフに発音を追加したら無視する。
        # ⺎(U+2E8E) 兀(U+5140) 兀(U+FA0C)
        # 嗀(U+55C0) 嗀(U+FA0D)
        self.duplicate_definition_of_hanzes = {
            str(0x2E8E):0, str(0x5140):0, str(0xFA0C):0,
            str(0x55C0):1, str(0xFA0D):1
        }
        self.is_added_glyf = [False, False]

    def get_has_single_pinyin_hanzi(self):
        return [(ord(hanzi), pinyins) for hanzi, pinyins in self.PINYIN_MAPPING_TABLE.items() if 1 == len(pinyins)]

    def get_has_multiple_pinyin_hanzi(self):
        return [(ord(hanzi), pinyins) for hanzi, pinyins in self.PINYIN_MAPPING_TABLE.items() if 1 < len(pinyins)]

    def get_advance_size_of_hanzi(self):
        # なんでもいいが、とりあえず漢字の「一」でサイズを取得する
        cid = self.marged_font["cmap"][str(ord("一"))]
        advanceWidth   = self.marged_font["glyf"][cid]["advanceWidth"]
        advanceHeight  = self.marged_font["glyf"][cid]["advanceHeight"]
        verticalOrigin = self.marged_font["glyf"][cid]["verticalOrigin"]
        return (advanceWidth, advanceHeight, verticalOrigin)

    
    def add_cmap_uvs(self):
        IVS = 0xE01E0 #917984
        """
        e.g.:
        hanzi_glyf　　　　標準の読みの拼音
        hanzi_glyf.ss00　ピンインの無い漢字グリフ。設定を変更するだけで拼音を変更できる
        hanzi_glyf.ss01　（異読のピンインがあるとき）標準の読みの拼音（uni4E0D と重複しているが GSUB の置換（多音字のパターン）を無効にして強制的に置き換えるため）
        hanzi_glyf.ss02　（異読のピンインがあるとき）以降、異読
        ...
        """

        for (ucode, pinyins) in self.get_has_single_pinyin_hanzi():
            str_unicode = str(ucode)
            if not (str_unicode in self.cmap_table):
                raise Exception("グリフが見つかりません.\n  unicode: {}".format(str_unicode))
            cid = self.cmap_table[str_unicode]
            self.marged_font["cmap_uvs"]["{0} {1}".format(str_unicode, IVS)] = "{}.ss00".format(cid)
        
        for (ucode, pinyins) in self.get_has_multiple_pinyin_hanzi():
            str_unicode = str(ucode)
            if not (str_unicode in self.cmap_table):
                raise Exception("グリフが見つかりません.\n  unicode: {}".format(str_unicode))
            cid = self.cmap_table[str_unicode]
            # ss00 は ピンインのないグリフ なので、ピンインのグリフは "ss{:02}".format(len) まで
            for i in range( len(pinyins)+1 ):
                self.marged_font["cmap_uvs"]["{0} {1}".format(str_unicode, IVS + i)] = "{}.ss{:02}".format(cid, i)

    def add_glyph_order(self):
        """
        e.g.: 
        "glyph_order": [
            ...
            "uni4E0D","uni4E0D.ss00","uni4E0D.ss01","uni4E0D.ss02","uni4E0D.ss03",
            ...
        ]
        """
        # 漢字グリフ追加
        set_glyph_order = set(self.marged_font["glyph_order"])
        for (ucode, pinyins) in self.get_has_single_pinyin_hanzi():
            str_unicode = str(ucode)
            if not (str_unicode in self.cmap_table):
                raise Exception("グリフが見つかりません.\n  unicode: {}".format(str_unicode))
            cid = self.cmap_table[str_unicode]
            set_glyph_order.add("{}.ss00".format(cid))

        for (ucode, pinyins) in self.get_has_multiple_pinyin_hanzi():
            str_unicode = str(ucode)
            if not (str_unicode in self.cmap_table):
                raise Exception("グリフが見つかりません.\n  unicode: {}".format(str_unicode))
            # ss00 は ピンインのないグリフ なので、ピンインのグリフは "ss{:02}".format(len) まで
            for i in range( len(pinyins)+1 ):
                cid = self.cmap_table[str_unicode]
                set_glyph_order.add("{}.ss{:02}".format(cid, i))
        
        # ピンインのグリフを追加
        set_glyph_order = set_glyph_order | set(self.pinyin_glyf.keys())
        new_glyph_order = list(set_glyph_order)
        new_glyph_order.sort()
        self.marged_font["glyph_order"] = new_glyph_order
        # print(self.marged_font["glyph_order"])

    def generate_hanzi_glyf_with_normal_pinyin(self, cid):
        (advanceWidth, advanceHeight, verticalOrigin) = self.get_advance_size_of_hanzi()
        hanzi_glyf = {
                         "advanceWidth": advanceWidth,
                         "advanceHeight": advanceHeight,
                         "verticalOrigin": verticalOrigin,
                         "references": [
                             {"glyph":"{}.ss01".format(cid),"x":0, "y":0, "a":1, "b":0, "c":0, "d":1}
                         ]
                     }
        return hanzi_glyf

    def generate_hanzi_glyf_with_pinyin(self, cid, pronunciation):
        (advanceWidth, advanceHeight, verticalOrigin) = self.get_advance_size_of_hanzi()
        simpled_pronunciation = utility.simplification_pronunciation( pronunciation )
        hanzi_glyf = {
                         "advanceWidth": advanceWidth,
                         "advanceHeight": advanceHeight,
                         "verticalOrigin": verticalOrigin,
                         "references": [
                             {"glyph":"arranged_{}".format(simpled_pronunciation),"x":0, "y":0, "a":1, "b":0, "c":0, "d":1},
                             {"glyph":"{}.ss00".format(cid),                      "x":0, "y":0, "a":1, "b":0, "c":0, "d":1}
                         ]
                     }
        return hanzi_glyf
    
    
    # unicode 上に定義が重複している漢字があるとエラーになるので判定を入れる
    # Exception: otfccbuild : Build : [WARNING] [Stat] Circular glyph reference found in gid 11663 to gid 11664. The reference will be dropped.
    def is_added_glyf_4_duplicate_definition_of_hanzi(self, str_unicode):
        duplicate_definition_of_hanzes = [str_unicode for str_unicode, _ in self.duplicate_definition_of_hanzes.items()]
        if str_unicode in duplicate_definition_of_hanzes:
            idx = self.duplicate_definition_of_hanzes[str_unicode]
            return self.is_added_glyf[idx]
        return False

    def update_status_is_added_glyf_4_duplicate_definition_of_hanzi(self, str_unicode):
        duplicate_definition_of_hanzes = [str_unicode for str_unicode, _ in self.duplicate_definition_of_hanzes.items()]
        if str_unicode in duplicate_definition_of_hanzes:
            idx = self.duplicate_definition_of_hanzes[str_unicode]
            self.is_added_glyf[idx] = True
                
    def add_glyf(self):
        """
        e.g.: 
        hanzi_glyf　　　　標準の読みの拼音
        hanzi_glyf.ss00　ピンインの無い漢字グリフ。設定を変更するだけで拼音を変更できる
        hanzi_glyf.ss01　（異読のピンインがあるとき）標準の読みの拼音（uni4E0D と重複しているが GSUB の置換（多音字のパターン）を無効にして強制的に置き換えるため）
        hanzi_glyf.ss02　（異読のピンインがあるとき）以降、異読
        """
        """
        Sawarabi
        "uni4E00": {
            "advanceWidth": 1000,
            "advanceHeight": 1000,
            "verticalOrigin": 952,
        """
        # グリフ数削減のために最低限のグリフのみを作成する
        # if "hanzi_glyf" has normal pronunciation only
        # hanzi_glyf -> hanzi_glyf.ss00
        # hanzi_glyf = hanzi_glyf.ss00 + normal pronunciation
        for (ucode, pinyins) in self.get_has_single_pinyin_hanzi():
            str_unicode = str(ucode)
            if not (str_unicode in self.cmap_table):
                raise Exception("グリフが見つかりません.\n  unicode: {}".format(str_unicode))
            if self.is_added_glyf_4_duplicate_definition_of_hanzi(str_unicode):
                continue
            cid = self.cmap_table[str_unicode]
            glyf_data = self.font_glyf_table[cid]
            self.font_glyf_table.update( { "{}.ss00".format(cid) : glyf_data } )
            normal_pronunciation = pinyins[pg.NORMAL_PRONUNCIATION]
            glyf_data = self.generate_hanzi_glyf_with_pinyin(cid, normal_pronunciation)
            self.font_glyf_table.update( { cid : glyf_data } )

        # if "hanzi_glyf" has variational pronunciation
        # hanzi_glyf -> hanzi_glyf.ss00
        # hanzi_glyf.ss01 = hanzi_glyf.ss00 + normal pronunciation
        # hanzi_glyf = hanzi_glyf.ss01
        # hanzi_glyf.ss02 = hanzi_glyf.ss00 + variational pronunciation
        for (ucode, pinyins) in self.get_has_multiple_pinyin_hanzi():
            str_unicode = str(ucode)
            if not (str_unicode in self.cmap_table):
                raise Exception("グリフが見つかりません.\n  unicode: {}".format(str_unicode))
            if self.is_added_glyf_4_duplicate_definition_of_hanzi(str_unicode):
                continue
            cid = self.cmap_table[str_unicode]
            glyf_data = self.font_glyf_table[cid]
            # hanzi_glyf -> hanzi_glyf.ss00
            self.font_glyf_table.update( { "{}.ss00".format(cid) : glyf_data } )
            # hanzi_glyf.ss01 = hanzi_glyf.ss00 + normal pronunciation
            normal_pronunciation = pinyins[pg.NORMAL_PRONUNCIATION]
            glyf_data = self.generate_hanzi_glyf_with_pinyin(cid, normal_pronunciation)
            self.font_glyf_table.update( { "{}.ss01".format(cid) : glyf_data } )
            # hanzi_glyf = hanzi_glyf.ss01
            glyf_data = self.generate_hanzi_glyf_with_normal_pinyin(cid)
            self.font_glyf_table.update( { cid : glyf_data } )
            # if hanzi_glyf has variational pronunciation
            # hanzi_glyf.ss01 = hanzi_glyf.ss00 + variational pronunciation
            for i in range( 1,len(pinyins) ):
                variational_pronunciation = pinyins[i]
                glyf_data = self.generate_hanzi_glyf_with_pinyin(cid, variational_pronunciation)
                self.font_glyf_table.update( { "{}.ss{:02}".format(cid, pg.VARIATIONAL_PRONUNCIATION + i) : glyf_data } )
            self.update_status_is_added_glyf_4_duplicate_definition_of_hanzi(str_unicode)

        new_glyf = self.marged_font["glyf"]
        new_glyf.update( self.pinyin_glyf )
        new_glyf.update( self.font_glyf_table )
        self.marged_font["glyf"] = new_glyf
        print("  ==> glyf num : {}".format(len(self.marged_font["glyf"])))
        if len(self.marged_font["glyf"]) > 65536:
            raise Exception("glyf は 65536 個以上格納できません。")

    def convert_str_hanzi_2_cid(self, str_hanzi):
        return self.cmap_table[ str(ord(str_hanzi)) ]

    # calt も rclt も featute の数が多いと有効にならない。 feature には上限がある？
    # rclt は calt と似ていて、かつ無効にできないタグ [Tag:'rclt'](https://docs.microsoft.com/en-us/typography/opentype/spec/features_pt#-tag-rclt)
    # 代替文字の指定、置換条件の指定
    def add_GSUB(self):
        # 初期化
        self.marged_font["GSUB"] = {
            # 文字体系 ごとに使用する feature を指定する
            "languages": {
                "DFLT_DFLT": {
                    "features": [
                        "aalt_00000",
                        "rclt_00000"
                    ]
                },
                # 'hani' = CJK (中国語/日本語/韓国語)
                "hani_DFLT": {
                    "features": [
                        "aalt_00001",
                        "rclt_00001"
                    ]
                },
            },
            "lookups": {
                # aalt_0 は拼音が一つのみの漢字 + 記号とか。置き換え対象が一つのみのとき
                "lookup_aalt_0" : {
                    "type": "gsub_single",
                    "flags": {},
                    "subtables": [{}]
                },
                # aalt_1 は拼音が複数の漢字
                "lookup_aalt_1" : {
                    "type": "gsub_alternate",
                    "flags": {},
                    "subtables": [{}]
                },
                # pattern one
                "lookup_rclt_0": {
                    "type": "gsub_chaining",
                    "flags": {},
                    "subtables": [
                        # {
                        #     "match": [[],[]],
                        #     "apply": [
                        #         {
                        #             "at": -1, 
                        #             "lookup": ""
                        #         }
                        #     ],
                        #     "inputBegins": -1,
                        #     "inputEnds": -1
                        # }
                    ]
                },
                # pattern two
                "lookup_rclt_1": {
                    "type": "gsub_chaining",
                    "flags": {},
                    "subtables": [
                        # {
                        #     "match": [[],[]],
                        #     "apply": [
                        #         {
                        #             "at": -1, 
                        #             "lookup": ""
                        #         }
                        #     ],
                        #     "inputBegins": -1,
                        #     "inputEnds": -1
                        # }
                    ]
                },
                # exception pattern
                "lookup_rclt_2": {
                    "type": "gsub_chaining",
                    "flags": {},
                    "subtables": [
                        # {
                        #     "match": [[],[]],
                        #     "apply": [
                        #         {
                        #             "at": -1, 
                        #             "lookup": ""
                        #         }
                        #     ],
                        #     "inputBegins": -1,
                        #     "inputEnds": -1
                        # }
                    ]
                },
            },
            # feature ごとに使用する lookup table を指定する
            "features": {
                "aalt_00000": ["lookup_aalt_0","lookup_aalt_1"],
                "aalt_00001": ["lookup_aalt_0","lookup_aalt_1"],
                "rclt_00000": ["lookup_rclt_0","lookup_rclt_1","lookup_rclt_2"],
                "rclt_00001": ["lookup_rclt_0","lookup_rclt_1","lookup_rclt_2"]
            }, 
            "lookupOrder": ["lookup_aalt_0","lookup_aalt_1","lookup_rclt_0","lookup_rclt_1","lookup_rclt_2"]
        }
        lookup_order = set()
        
        """
        e.g.:
        "lookups": {
            "lookup_aalt_0": {
                "type": "gsub_single",
                "flags": {},
                "subtables": [
                    {   
                        ...
                        "uni4E01": "uni4E01.ss00",
                        "uni4E03": "uni4E03.ss00",
                        "uni4E08": "uni4E08.ss00",
                        ...
                    }
                ]
            },
            "lookup_aalt_1": {
                "type": "gsub_alternate",
                "flags": {},
                "subtables": [
                    {
                        "uni4E00": [
                            "uni4E00.ss00",
                            "uni4E00.ss01",
                            "uni4E00.ss02"
                        ],
                        "uni4E07": [
                            "uni4E07.ss00",
                            "uni4E07.ss01"
                        ],
                        ...
                    }
                ]
            }
        }
        """
        
        lookup_tables = self.marged_font["GSUB"]["lookups"]
        aalt_0_subtables = lookup_tables["lookup_aalt_0"]["subtables"][0]
        aalt_1_subtables = lookup_tables["lookup_aalt_1"]["subtables"][0]

        # add
        for (ucode, _) in self.get_has_single_pinyin_hanzi():
            str_unicode = str(ucode)
            cid = self.cmap_table[str_unicode]
            aalt_0_subtables.update( {cid : "{}.ss00".format(cid) } )
        lookup_order.add( "lookup_aalt_0" )

        for (ucode, pinyins) in self.get_has_multiple_pinyin_hanzi():
            str_unicode = str(ucode)
            cid = self.cmap_table[str_unicode]
            alternate_list = []
            # ss00 は ピンインのないグリフ なので、ピンインのグリフは "ss{:02}".format(len) まで
            for i in range( len(pinyins)+1 ):
                alternate_list.append("{}.ss{:02}".format(cid, i))
            aalt_1_subtables.update( {cid : alternate_list } )
        lookup_order.add( "lookup_aalt_1" )



        # lookups の rclt
        """
        e.g.:
        adobe version
        lookup rclt0 {
            sub [uni4E0D uni9280] uni884C' lookup lookup_0 ;
        } rclt0;
        """
        """
        json version
        "lookups": {
            "lookup_rclt_0": {
                "type": "gsub_chaining",
                "flags": {},
                "subtables": [
                    {
                        "match": [
                            ["uni4E0D","uni9280"],
                            ["uni884C"]
                        ],
                        "apply": [
                            {
                                "at": 1,
                                "lookup": "lookup_11_3"
                            }
                        ],
                        "inputBegins": 1,
                        "inputEnds": 2
                    }
                ]
            },
            ...
        }
        """
        pattern_one = [{}]
        pattern_two = {}
        exception_pattern = {}
        with open(self.PATTERN_ONE_TXT, mode='r', encoding='utf-8') as read_file:
            for line in read_file:
                [str_order, hanzi, pinyin, patterns] = line.rstrip('\n').split(', ')
                order = int(str_order)
                # self.PATTERN_ONE_TXT の order = 1 は標準的なピンインなので無視する
                if 1 == order:
                    continue
                # 2 から異読のピンイン。添字に使うために -2 して 0 にする。
                idx = order-2
                if len(pattern_one) <= idx:
                    pattern_one.append({})
                tmp = pattern_one[idx]
                tmp.update(
                    {
                        hanzi:{
                            "variational_pronunciation": pinyin,
                            "patterns": patterns
                        }
                    }
                )
        with open(self.PATTERN_TWO_JSON, "rb") as read_file:
            pattern_two = orjson.loads(read_file.read())
        with open(self.EXCEPTION_PATTERN_JSON, "rb") as read_file:
            exception_pattern = orjson.loads(read_file.read())

        # pattern one
        max_num_of_variational_pinyin = len(pattern_one)
        """
        pattern_one の中身
        e.g.:
        [
            {
                "行":{
                    "variational_pronunciation":"háng",
                    "patterns":"[~当|~家|~间|~列|~情|~业|发~|同~|外~|银~|~话|~会|~距]"
                },
                "作":{
                    "variational_pronunciation":"zuō",
                    "patterns":"[~坊|~弄|~揖]"
                }
            },
            {
                "行":{
                    "variational_pronunciation":"hàng",
                    "patterns":"[树~子]"
                },
                "作":{
                    "variational_pronunciation":"zuó",
                    "patterns":"[~料]"
                }
            },
            {
                "行":{
                    "variational_pronunciation":"héng",
                    "patterns":"[道~]"
                },
                "作":{
                    "variational_pronunciation":"zuo",
                    "patterns":"[做~]"
                }
            }
        ]
        """
        lookup_tables = self.marged_font["GSUB"]["lookups"]
        # init 
        if max_num_of_variational_pinyin > 10:
            raise Exception("ピンインは10通りまでしか対応していません")
        for idx in range(max_num_of_variational_pinyin):
            lookup_name = "lookup_pattern_0{}".format(idx)
            lookup_tables.update( 
                { 
                    lookup_name : {
                        "type": "gsub_single",
                        "flags": {},
                        "subtables": [{}]
                    }
                } 
            )
            lookup_order.add( lookup_name )
        # add
        list_rclt_0_subtables = lookup_tables["lookup_rclt_0"]["subtables"]
        for idx in range(max_num_of_variational_pinyin):
            # to lookup table for replacing
            lookup_name = "lookup_pattern_0{}".format(idx)
            lookup_table_subtables = lookup_tables[lookup_name]["subtables"][0]
            for apply_hanzi in pattern_one[idx].keys():
                apply_hanzi_cid = self.convert_str_hanzi_2_cid(apply_hanzi)
                lookup_table_subtables.update( { apply_hanzi_cid : "{}.ss{:02}".format(apply_hanzi_cid, pg.SS_VARIATIONAL_PRONUNCIATION + idx) } )
                # to rclt0
                str_patterns = pattern_one[idx][apply_hanzi]["patterns"]
                
                patterns = str_patterns.strip("[]").split('|') 
                # まとめて記述できるもの
                # e.g.:
                # sub [uni4E0D uni9280] uni884C' lookup lookup_0 ;
                # sub uni884C' lookup lookup_0　[uni4E0D uni9280] ;
                left_match  = [s for s in patterns if re.match("^~.$", s)]
                right_match = [s for s in patterns if re.match("^.~$", s)]
                # 一つ一つ記述するもの
                # e.g.:
                # sub uni85CF' lookup lookup_0 uni7D05 uni82B1 ;
                other_match = [s for s in patterns if not (s in (left_match + right_match))]

                if len(left_match) > 0:
                    context_hanzi_cids = [ self.convert_str_hanzi_2_cid(context_hanzi) for context_hanzi in [context_hanzi.replace("~","") for context_hanzi in left_match] ]
                    list_rclt_0_subtables.append(
                        {
                            "match": [ [apply_hanzi_cid], context_hanzi_cids ],
                            "apply": [
                                {
                                "at": 0,
                                "lookup": lookup_name
                                }
                            ],
                            "inputBegins": 0,
                            "inputEnds": 1
                        }
                    )
                
                if len(right_match) > 0:
                    context_hanzi_cids = [ self.convert_str_hanzi_2_cid(context_hanzi) for context_hanzi in [context_hanzi.replace("~","") for context_hanzi in right_match] ]
                    list_rclt_0_subtables.append(
                        {
                            "match": [ context_hanzi_cids, [apply_hanzi_cid] ],
                            "apply": [
                                {
                                "at": 1,
                                "lookup": "lookup_pattern_0{}".format(idx)
                                }
                            ],
                            "inputBegins": 1,
                            "inputEnds": 2
                        }
                    )

                for match_pattern in other_match:
                    at = match_pattern.index("~")
                    list_rclt_0_subtables.append(
                        {
                            "match": [ [self.convert_str_hanzi_2_cid(hanzi)] for hanzi in match_pattern.replace("~", apply_hanzi) ],
                            "apply": [
                                {
                                "at": at,
                                "lookup": "lookup_pattern_0{}".format(idx)
                                }
                            ],
                            "inputBegins": at,
                            "inputEnds": at + 1
                        }
                    )
        
        # pattern two
        lookup_tables = self.marged_font["GSUB"]["lookups"]
        # to lookup table for replacing
        for lookup_name, table in pattern_two["lookup_table"].items():
            # init
            lookup_tables.update( 
                { 
                    lookup_name : {
                        "type": "gsub_single",
                        "flags": {},
                        "subtables": [{}]
                    }
                } 
            )
            # add
            lookup_table_subtables = lookup_tables[lookup_name]["subtables"][0]
            # e,g. "差": "差.ss05", -> "cid16957": "cid16957.ss05"
            lookup_table_subtables.update( { self.convert_str_hanzi_2_cid(k): v.replace(k,self.convert_str_hanzi_2_cid(k)) for k,v in table.items() } )
            lookup_order.add( lookup_name )
        # to rclt1
        list_rclt_1_subtables = lookup_tables["lookup_rclt_1"]["subtables"]
        for phrase, list_pattern_table in pattern_two["patterns"].items():
            applies = [] 
            ats = [] 
            for i in range(len(list_pattern_table)):
                table = list_pattern_table[i]
                # 要素は一つしかない. ほかに綺麗に取り出す方法が思いつかない.
                lookup_name = list(table.values())[0]
                if lookup_name != None:
                    ats.append(i)
                    applies.append(
                        {
                            "at": i,
                            "lookup": lookup_name
                        }
                    )
            
            list_rclt_1_subtables.append(
                        {
                            "match": [ [self.convert_str_hanzi_2_cid(hanzi)] for hanzi in phrase ],
                            "apply": applies,
                            "inputBegins": min(ats),
                            "inputEnds": max(ats) + 1
                        }
                    )

        
        # exception pattern
        lookup_tables = self.marged_font["GSUB"]["lookups"]
        # to lookup table for replacing
        for lookup_name, table in exception_pattern["lookup_table"].items():
            # init
            lookup_tables.update( 
                { 
                    lookup_name : {
                        "type": "gsub_single",
                        "flags": {},
                        "subtables": [{}]
                    }
                } 
            )
            # add
            lookup_table_subtables = lookup_tables[lookup_name]["subtables"][0]
            # e,g. "着": "着.ss02",, -> "cid28651": "cid28651.ss05"
            lookup_table_subtables.update( { self.convert_str_hanzi_2_cid(k): v.replace(k,self.convert_str_hanzi_2_cid(k)) for k,v in table.items() } )
            lookup_order.add( lookup_name )
        # to rclt2
        list_rclt_2_subtables = lookup_tables["lookup_rclt_2"]["subtables"]
        for phrase, setting_of_phrase in exception_pattern["patterns"].items():
            ignore_pattern     = setting_of_phrase["ignore"]
            list_pattern_table = setting_of_phrase["pattern"]

            # ignore のパターンがあれば記述する
            if ignore_pattern != None:
                list_ignore_pattern = ignore_pattern.split(' ')
                tmp = [ hanzi for hanzi in list_ignore_pattern if re.match(".'", hanzi) ]
                if len(tmp) == 1:
                    apply_hanzi = tmp[0]
                else:
                    # 現在は、対象('がある)漢字はひとつだけと想定している
                    raise Exception("exception pattern の ignore 記述が間違っています。: \n {}".format(ignore_pattern))
                # 空白とシングルコートを削除
                ignore_phrase = ignore_pattern.replace(" ", "").replace("'", "")
                print(ignore_phrase)
                at     = list_ignore_pattern.index(apply_hanzi)
                list_rclt_2_subtables.append(
                        {
                            "match": [ [self.convert_str_hanzi_2_cid(hanzi)] for hanzi in ignore_phrase ],
                            "apply": [],
                            "inputBegins": at,
                            "inputEnds": at + 1
                        }
                    )
            # 期待する普通のパターン
            applies = [] 
            ats = [] 
            for i in range(len(list_pattern_table)):
                table = list_pattern_table[i]
                # 要素は一つしかない. ほかに綺麗に取り出す方法が思いつかない.
                lookup_name = list(table.values())[0]
                if lookup_name != None:
                    ats.append(i)
                    applies.append(
                        {
                            "at": i,
                            "lookup": lookup_name
                        }
                    )
            list_rclt_2_subtables.append(
                        {
                            "match": [ [self.convert_str_hanzi_2_cid(hanzi)] for hanzi in phrase ],
                            "apply": applies,
                            "inputBegins": min(ats),
                            "inputEnds": max(ats) + 1
                        }
                    )

        

        # lookup order
        """
        e.g.:
        "lookupOrder": [
            "lookup_rclt_0",
            "lookup_rclt_1",
            "lookup_ccmp_2",
            "lookup_11_3"
        ]
        """
        union_lookup_order = set(self.marged_font["GSUB"]["lookupOrder"]) | lookup_order
        list_lookup_order = list(union_lookup_order)
        list_lookup_order.sort()
        gsub_table = self.marged_font["GSUB"]
        gsub_table.update( {"lookupOrder" : list_lookup_order} )
        self.marged_font["GSUB"] = gsub_table

        # 保存して確認する
        # with open("GSUB.json", "wb") as f:
        #     serialized_glyf = orjson.dumps(self.marged_font["GSUB"], option=orjson.OPT_INDENT_2)
        #     f.write(serialized_glyf)

    def load_json(self):
        with open(self.TAMPLATE_MAIN_JSON, "rb") as read_file:
            self.marged_font = orjson.loads(read_file.read())
        with open(self.TAMPLATE_GLYF_JSON, "rb") as read_file:
            self.font_glyf_table = orjson.loads(read_file.read())

    def save_as_json(self, TAMPLATE_MARGED_JSON):
        with open(TAMPLATE_MARGED_JSON, "wb") as f:
            serialized_glyf = orjson.dumps(self.marged_font, option=orjson.OPT_INDENT_2)
            f.write(serialized_glyf)
    
    def convert_json2otf(self, TAMPLATE_JSON, OUTPUT_FONT):
        cmd = "otfccbuild {} -o {}".format(TAMPLATE_JSON, OUTPUT_FONT)
        print(cmd)
        shell.process(cmd)

    def build(self, OUTPUT_FONT):
        self.add_cmap_uvs()
        print("cmap_uvs table を追加完了")
        self.add_glyph_order()
        print("glyph_order table を追加完了")
        self.add_glyf()
        print("glyf table を追加完了")
        self.add_GSUB()
        print("GSUB table を追加完了")
        TAMPLATE_MARGED_JSON = os.path.join(p.DIR_TEMP, "template.json")
        self.save_as_json(TAMPLATE_MARGED_JSON)
        self.convert_json2otf(TAMPLATE_MARGED_JSON, OUTPUT_FONT)