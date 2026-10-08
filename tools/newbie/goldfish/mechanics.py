#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""机制注册表：data JSON 中全部机制 tag 的单一登记处。

三类条目：
  · 实体 handler（register_handler(tag, fn)，签名 (game, card, value)）：
    green 地落系 3 个（landfall_ctr / landfall_double / landfall_dblpow），
    在通用触发点按 tag 分发；
  · 纯标记位（register_handler(tag)）：由牌组代码内联消费（与原 sim 一致），
    注册仅为 data JSON 的 schema 校验与自我描述；
  · 共享通道 nc_channel(game, amt)：红系非战斗伤害入口
    （tomik +1 → double_nc 翻倍 → dmg → barbs team_pump），
    sim_red / sim_red_blind 原实现的并集（red 池无 double_nc 牌，等价）。
"""
from goldfish.engine import register_handler

# ---------------------------------------------------------------- 实体 handler
@register_handler('landfall_ctr')
def _landfall_ctr(game, card, value):
    """地落：放 value 颗 +1/+1 豆（Sazh's Chocobo）。"""
    card['ctr'] = card.get('ctr', 0) + value


@register_handler('landfall_double')
def _landfall_double(game, card, value):
    """地落：自身豆数翻倍（无豆则放 1 颗）（Mossborn Hydra）。"""
    c = card.get('ctr', 0)
    card['ctr'] = c * 2 if c else 1


@register_handler('landfall_dblpow')
def _landfall_dblpow(game, card, value):
    """地落：本回合力量 +（自身力量+豆数）（Mightform Harmonizer）。"""
    card['perm_pow'] = card.get('perm_pow', 0) + card['p'] + card.get('ctr', 0)


# ---------------------------------------------------------------- 共享通道
def nc_channel(game, amt):
    """非战斗伤害入口：Tomik(+1 替换) → double_nc 翻倍 → 伤害 → Barbs 全队膨胀。"""
    if amt <= 0:
        return
    if any(b['tags'].get('tomik') for b in game.bf):
        amt += 1
    if any(b['tags'].get('double_nc') for b in game.bf):
        amt *= 2
    game.dmg += amt
    nb = sum(1 for b in game.bf if b['tags'].get('barbs'))
    if nb:
        game.team_pump += nb


# ---------------------------------------------------------------- 纯标记位
_MARKER_TAGS = """
ally_ping archetype atk_ctr atk_drain atk_drain_cond atk_loot atk_ping atk_pump
barbs bella big big_spell_ctr blank bounce bounce_back burn
cost_reduce cost_reduce2 ctr_draw ctr_fight ctr_pump
deathtouch dies_token dig dino_lord dork dork2 double_nc drain draw draw3_token
drone_if_attacking effigy elf_lord emeritus etb etb_drain etb_draw etb_ping eulogist
extra_land ferocious first_strike flurry flurry_copy fly flying from_land
give_ctr grow_combat guttersnipe hare haste
inspire land_ramp lavarunner leg life_ctr life_draw life_src lifelink lock
lord3 lord_dork mass_trample menace mobilize mutagen
opus_ctr opus_dmg opus_draw opus_pump page pay_pump per_instant per_noncreature
perm_ctr power4_draw prowess pump pump1 pump2 pump_self
removal repartee_drain sac_draw sac_draw_unblock sd_copy sd_ctr sd_temp sd_token
second_spell_ctr second_spell_token sink_drain start_ctr
temp_pump tok_fs tokens tomik trample triumph unblockable vig
""".split()

for _tag in _MARKER_TAGS:
    register_handler(_tag)
