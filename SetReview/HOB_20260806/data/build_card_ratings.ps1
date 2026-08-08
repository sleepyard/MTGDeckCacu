$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$jsonPath = Join-Path $root 'data\scryfall_hob_unique_cards_20260806.json'
$outPath = Join-Path $root '03_CardRatings.md'
$cards = Get-Content -Raw -Encoding UTF8 $jsonPath | ConvertFrom-Json

# Paper ratings are deliberately anchored to this set, not to a numeric power score.
$draftA = @(126)
$draftAminus = @(12,14,26,29,42,54,61,69,75,82,91,93,96,99,104,109,110,114,119,123,124,131,136,137,138,139,142,143,146,147,154,158,164,166,169,170,174,176,177,178)
$draftBplus = @(3,5,7,13,17,22,25,27,32,33,36,39,41,44,49,50,53,55,60,62,64,65,66,68,70,74,77,81,83,84,87,89,90,97,98,103,105,107,108,113,117,118,120,121,122,128,129,132,134,141,144,148,149,151,152,156,159,163,168,171,172,173,175)
$draftB = @(4,6,8,11,16,19,23,30,34,35,37,45,47,51,52,56,58,71,72,73,78,80,85,88,94,101,102,106,112,115,116,127,130,133,140,145,150,155,157,165,167,179)
$draftCplus = @(1,9,10,15,18,20,21,28,31,38,43,48,57,67,79,95,100,111,125,127,135,153,160,161,173,180,181,182,183,184,185,186,187,188)
$draftCminus = @(46,59,76,86,92,103,134,175)
$draftD = @(98,137)

$sealedA = @(12,14,26,29,75,93,104,110,119,126,136,144,166,170,174,177)
$sealedAminus = @(42,54,61,69,82,91,96,99,109,114,123,124,131,137,138,139,142,143,146,147,154,158,164,169,176,178)
$sealedBplus = @(3,4,5,7,13,17,22,25,27,32,33,36,39,40,41,44,47,49,50,53,56,60,62,64,65,66,68,70,74,77,81,83,84,87,89,90,97,98,103,105,107,108,113,117,118,120,121,122,128,129,132,134,141,148,149,151,152,155,156,159,163,168,171,172,175,179,187)
$sealedB = @(1,2,6,8,9,10,11,16,19,23,30,34,35,37,45,51,52,55,58,59,71,72,73,78,80,85,88,94,101,102,106,112,115,116,125,127,130,133,140,145,150,157,165,167)
$sealedCplus = @(15,18,20,21,28,31,38,43,48,57,67,79,95,100,111,127,135,153,160,161,173,180,181,182,183,184,185,186,188)
$sealedCminus = @(46,76,86,92)

$t0 = @(5,12,33,40,42,75,96,110,114,120,131,136,142,143,144,158,166,170,174,176,177)
$t1 = @(3,4,6,7,8,14,17,22,24,25,26,27,29,32,34,36,37,39,41,47,49,50,53,54,55,57,59,60,61,64,65,66,68,69,70,71,72,74,76,77,79,82,83,84,87,89,90,91,93,94,98,99,101,103,104,105,106,107,108,109,112,113,115,117,118,119,121,122,123,124,125,128,129,130,132,134,138,139,140,141,145,146,147,148,149,150,151,152,154,155,156,157,159,163,164,165,167,168,169,171,172,175,178,179,181,187)

$usage = @{
  5='现有补强 / Tempo 软锁'
  12='新轴 / 自军保护与延迟空军'
  33='新轴 / 坟场法术引擎'
  40='新轴 / Artifact ETB 卡差'
  42='现有补强 / Vehicle Recruit'
  61='新轴 / 牺牲与 Amass 回报'
  75='现有补强 / 坟场对策威胁'
  96='新轴 / Wizard 法术'
  110='新轴 / Treasure Dragon 终结'
  114='新轴 / Equipment 批量兑现'
  120='新轴 / Landfall 与地数 Bear'
  131='新轴 / Halfling 产费'
  136='新轴 / 生物减费与闪现'
  142='现有补强 / Ramp 与地数'
  143='新轴 / Elf 产费'
  144='新轴 / Token 与抽牌翻倍'
  158='新轴 / Goblin counters 直伤'
  166='新轴 / GU Elf Landfall'
  170='现有补强 / 传奇导师与卡差'
  174='新轴 / Equipment Spell discount'
  176='现有补强 / 牺牲抽牌与保护'
  177='新轴 / Equipment Treasure'
  26='现有补强 / 扫场'
  27='互动 / 四力去除与保护'
  29='新轴 / Dwarf Token'
  36='新轴 / 生物启动式抽牌'
  49='新轴 / 坟场法术选择'
  53='新轴 / 顶牌分堆资源'
  54='新轴 / ETB 重复'
  57='新轴 / 非生物法术过滤'
  59='新轴 / Wizard 触发翻倍'
  70='观察 / Odd-Even 触发'
  77='现有补强 / Peer 备用磨牌'
  83='新轴 / 牺牲与 Treasure'
  93='新轴 / Dragon 扫场与加速'
  103='新轴 / Mountain Dragon 教程'
  104='新轴 / Treasure Dragon'
  122='新轴 / Elf Affinity'
  123='新轴 / Creature 与 Landfall 回报'
  134='新轴 / 生物死亡链'
  137='新轴 / 大量铺地终局'
  146='新轴 / Human Recruit 横向增益'
  154='新轴 / Equipment Hone'
  164='新轴 / Treasure 抓牌'
  168='新轴 / Elf 额外下地'
  169='新轴 / 牺牲抽牌与复归'
  181='现有补强 / Elf 找地'
}

function Get-Grade($id, $groups) {
  foreach ($entry in $groups.GetEnumerator()) { if ($entry.Value -contains $id) { return $entry.Key } }
  return 'C'
}

$draftGroups = @{ 'A'=$draftA; 'A-'=$draftAminus; 'B+'=$draftBplus; 'B'=$draftB; 'C+'=$draftCplus; 'C-'=$draftCminus; 'D'=$draftD }
$sealedGroups = @{ 'A'=$sealedA; 'A-'=$sealedAminus; 'B+'=$sealedBplus; 'B'=$sealedB; 'C+'=$sealedCplus; 'C-'=$sealedCminus }
$out = [System.Collections.Generic.List[string]]::new()
$out.Add('# HOB 全卡逐张评级')
$out.Add('')
$out.Add('> 快照：2026-08-06；模式 F；置信度 C1。`Draft` / `Sealed` 为纸面锚定等级，构筑字段按发售后测试优先级填写。基础地列为库存，不计入评级覆盖。中文名尚未执行 mtgch 逐张核对。')
$out.Add('')
$out.Add('| # | English | 稀有度 | Draft | Sealed | 角色 / 纸面定位 | 构筑（赛制：用途） | 置信度 |')
$out.Add('|---:|---|---|---|---|---|---|---|')

foreach ($c in ($cards | Sort-Object { [int]$_.collector_number })) {
  $id = [int]$c.collector_number
  if ($id -ge 189) {
    $out.Add("| $id | $($c.name) | common | - | - | 基本地，库存牌 | - | C1 |")
    continue
  }
  $d = Get-Grade $id $draftGroups
  $s = Get-Grade $id $sealedGroups
  $text = (($c.oracle_text + ' ' + (($c.card_faces.oracle_text) -join ' ')).ToLowerInvariant())
  $type = $c.type_line
  if ($text -match 'recruit') { $role = 'Recruit / loot 与 token' }
  elseif ($text -match 'amass') { $role = 'Amass / counters 与 Army' }
  elseif ($text -match 'landfall|basic land|forest card|mountaincycling|additional land') { $role = '铺地 / Landfall 或调色' }
  elseif ($text -match 'equipment|equip|hone') { $role = 'Equipment / 战斗放大' }
  elseif ($text -match 'storied|artifact|legendary|saga') { $role = 'Storied / 永久物密度' }
  elseif ($text -match 'destroy|exile|counter target|fight|gets -') { $role = '互动 / 节奏交换' }
  elseif ($text -match 'draw|mill|graveyard|discard') { $role = '资源 / 坟场或卡差' }
  elseif ($type -match 'Creature') { $role = '曲线生物 / 场面压力' }
  elseif ($type -match 'Land') { $role = '功能地 / 色源' }
  else { $role = '功能牌 / 需原型支持' }
  if ($usage.ContainsKey($id)) { $build = $usage[$id] } elseif ($t0 -contains $id) { $build = '新轴候选' } elseif ($t1 -contains $id) { $build = '目标赛制定向测试' } else { $build = '目前无明确用途' }
  $priority = if ($t0 -contains $id) { 'T0' } elseif ($t1 -contains $id) { 'T1' } elseif ($d -in @('D','C-') -and $s -in @('D','C-')) { 'T3' } else { 'T2' }
  $out.Add("| $id | $($c.name -replace '\|','/') | $($c.rarity) | $d | $s | $role | $build / $priority | C1 |")
}
$out.Add('')
$out.Add('## 评级使用说明')
$out.Add('')
$out.Add('- A / B / C / D / F 体系见 [MtgSetReviewWorkFlow.md](../../MtgSetReviewWorkFlow.md)；基础等级不包含最理想牌表的协同上限。')
$out.Add('- 双面牌按一张牌记录，但其 Adventure、Equipment 或永久物模式已在角色与构筑用途中合并考虑。')
$out.Add('- T0 / T1 只是发售后测试顺序，不是胜率或主流地位声明。')
$out | Set-Content -Encoding UTF8 $outPath
Write-Output "Wrote $outPath ($($out.Count) lines)"
