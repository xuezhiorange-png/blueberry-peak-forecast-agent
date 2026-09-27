# V0.9-S0 全球设施蓝莓生物学与管理科学 authority review

**TASK_ID:** V0_9_S0_GLOBAL_PROTECTED_BLUEBERRY_BIOLOGY_AND_MANAGEMENT_AUTHORITY_REVIEW_R1

**版本：** 0.9.0 — BLUEBERRY_FORECAST_AGENT_V0_9_BIOLOGICAL_FORECAST_FOUNDATION

**结论：** PASS_V0_9_S0_SCIENTIFIC_AUTHORITY_REVIEW_COMPLETED
**范围：** 科学证据综述与可审计理论骨架；不是模型实现、参数定标或生产建议。

## 核心结论

保护地蓝莓预测可以建立在一条跨年度因果骨架上：上一季的果负载和采后植株状态影响枝条更新、花芽形成与储备；生产制度决定植株进入落叶休眠—需冷—forcing 路径，还是保叶/非休眠路径；花芽萌发、开花、有效授粉和坐果形成有来源 lineage 的果实 cohort；果实经过阶段性生长和成熟，形成每日新成熟量。剪枝、摘花/疏花、促早、温室环境均可沿不同路径改变植株状态，不能压成同一个产量倍率或收获日期偏移。

证据足以支持 V0.9-S1 冻结**状态和因果方向**，不支持在 S0 直接冻结云南默认值、品种参数或一套全球统一的休眠/成熟函数。基本生物过程有较强证据；反应大小和时点普遍依赖 blueberry type、cultivar、气候、设施及干预定义。没有主张已由一套端到端试验验证。

具体证据边界包括：SHB 替代生产系统的综合综述强调系统多样性和证据异质性；果实 double-sigmoid 阶段得到多项生理和解剖研究支持，但各论文的阶段术语和成熟生理分类并不完全一致。[Fang 等综述](https://doi.org/10.3390/agronomy10101531)；[蓝莓成熟系统综述](https://doi.org/10.1093/hr/uhaf126)；[高丛与兔眼果实发育研究](https://doi.org/10.2503/jjshs.55.46)

## 1. 研究与 authority 方法

本轮实际访问 DOI、期刊、PubMed/PMC、大学/政府及学术机构页面，并以来源页面可核验的元数据、摘要或方法描述建账；未保存或复制论文全文。来源矩阵包含 **47 条唯一来源**：Tier A=37、A2=4、B=1、C=5、D=0、X=0。Tier A/A2 共 **41 条同行评审期刊论文或科学综述**；另将同行评审状态不同或属于会议论文/程序研究的材料单列为 C 或 B，而不靠其补足核心机制数量。纳入记录的具名国家/地区为 11 个：阿根廷、巴西、加拿大、中国、日本、新西兰、葡萄牙、斯洛文尼亚、西班牙、智利、美国。

六个指定重点地区均有材料，但证据深度不均：

| 地区 | 本轮可用证据的侧重 | 外推边界 |
|---|---|---|
| 中国 | SHB 花芽诱导、温室促早/化学处理、PFAL、光照与 CO2 控制、果实发育生理 | 部分为单一品种或控制环境；工程优化不是整季产量因果模型 |
| 美国 | Florida SHB 休眠/evergreen 与修剪、Georgia 高隧道和成熟期、Oregon NHB 修剪、Michigan 授粉 | 地区和 cultivar 特异；不可合并成同一 chill / forcing 参数 |
| 日本 | 花芽分化、采后温度/日长、促成栽培和授粉 | 有些生产资料是会议论文或地方性资料 |
| 西班牙 | 阿斯图里亚斯无加温隧道早熟；露地/塑料栽培品质研究 | 保护栽培数据有限；早熟可行性不代表固定日期偏移 |
| 葡萄牙 | 温和冬季、满足需冷后临时覆盖及早熟品种表现 | 主要为地区性会议论文，不能推成全地中海规则 |
| 智利 | NHB 冬剪负载、source–sink、枝龄和高温品质响应 | 品种、果园、季节和处理强度特异 |

### Authority tiers

- **A**：同行评审原始实验、长期田间研究或控制生理研究，承担机制主证据。
- **A2**：系统综述或高质量科学综述，用于跨论文综合和冲突识别。
- **B**：大学/政府科学推广资料；支持生产系统定义和管理背景，不替代原始实验。
- **C**：会议论文、论文/学位研究或方法充分但证据范围较窄的材料。
- **D**：商业/种植者材料，只能提供实践观察。
- **X**：博客、SEO 或无出处摘要，不构成 scientific authority。

重要机制优先由至少两个相互独立的 A/A2 来源支持。对这一门槛未达到的参数、地区或路径，登记为证据缺口，不从相近作物或商业材料补齐。

## 2. 完整跨年度周期

下面的周期是由多类研究综合出的**理论骨架**，并非所有系统都沿同一路径、同一日历顺序或同一参数运行。证据较扎实的是状态之间的大方向；每个箭头的速率、阈值和效应量仍须由 cultivar/system 证据确定。

    flowchart TD
      priorCrop["上一季 crop load"]
      postState["采后植株状态"]
      canopy["枝条 叶幕 与碳储备"]
      growth["营养生长与 shoot cessation"]
      budInit["花芽诱导与分化"]
      prune["剪枝与枝条更新"]
      microclimate["设施微气候：温度 光照 湿度"]
      system{"生产制度"}
      decid["落叶型：适应与休眠"]
      chill["需冷暴露"]
      dormancy["休眠状态/解除"]
      ever["常绿/非休眠路径"]
      retain["保叶与持续生理活动"]
      forcing["forcing 与设施管理"]
      bud["萌芽与花芽膨大"]
      bloom["开花 cohort"]
      thin["采花/疏花/疏果"]
      pollination["有效授粉与受精"]
      set["坐果与 crop load"]
      source["SourceCapacity"]
      sink["SinkDemand"]
      ratio["source-sink interaction"]
      stage1["果实 Stage I"]
      stage2["果实 Stage II"]
      stage3["果实 Stage III"]
      color["Color break"]
      ripe["Ripe fruit cohort"]
      mature["每日新成熟量"]
      harvest["Harvest State Engine"]
      priorCrop --> postState --> canopy --> growth --> budInit --> system
      postState --> prune
      prune --> canopy
      prune --> budInit
      system --> decid --> chill --> dormancy --> forcing
      system --> ever --> retain --> forcing
      microclimate --> forcing
      microclimate --> stage2
      forcing --> bud --> bloom --> thin --> pollination --> set
      canopy --> source
      set --> sink
      source --> ratio
      sink --> ratio
      ratio --> stage1 --> stage2 --> stage3 --> color --> ripe --> mature
      mature -.->|"成熟供给接口"| harvest

> 图中成熟量到 Harvest State Engine 的虚线表示系统边界，不表示采摘能力属于植物生理因果状态。生物引擎输出 daily newly mature quantity；既有 Harvest State 才结合期初成熟库存、损耗、采摘能力计算 harvest quantity。该接口划分是模型架构抽象，不是声称文献已经验证现有工程实现。

剪枝会改变结构、潜在花芽 sink 与未来叶幕 source；摘花/疏花主要调整 reproductive sink；二者不可互换。[SHB 花芽密度实验](https://doi.org/10.21273/hortsci.34.4.607)、[智利修剪负载研究](https://doi.org/10.4067/S0718-58392023000400418)、[source/sink 果枝研究](https://doi.org/10.1016/j.scienta.2018.06.041)

## 3. 年周期各 transition：driver、方向、管理和外推限制

“加速/延迟”表示在研究条件下可能推动或延后状态转移的因素，不代表无条件单调规律。没有充分直接证据的转换明确写为 gap。

| Transition | 主要 driver；可能的加速/延迟 | 可改变路径的管理事件 | Cultivar / system 限制 |
|---|---|---|---|
| 上季采收 → 采后植株状态 | 当前 crop load、叶片健康、枝条更新、根/冠储备共同决定起点 | 采后修剪、灌溉/营养干预、保叶或落叶管理 | 直接、跨系统量化的采后状态基线不足；应观察而非补造 |
| 采后状态 → 新梢生长 | 温度、日长、植株 vigor 与资源供给影响萌梢；胁迫可能压低生长 | 采后修剪、遮阴、水肥 | potted、露地、容器和 evergreen 状态不同；不能用单一 shoot-growth rate |
| shoot growth → 生长停止 | photoperiod、温度、枝条成熟和 genotype | 夏剪/hedging、设施温度管理 | 休眠型材料与持续生长型材料不同 |
| 生长停止 → flower-bud initiation | 短日及温度在若干 SHB/NHB 研究中影响诱导；高温可在特定材料下抑制诱导 | 光周期管理、枝条/冠层管理 | 诱导时点可在采收中或采后；类型与品种差异明显；短日阈值不是全局常数 |
| initiation → differentiation / bud number | shoot、cane age、冠层位置/光环境、上一季负载与 vigor | 剪枝、枝条更新、花芽负载调节 | 不同品种的形成季节和节点分布不同；观察间隔也影响结论 |
| 花芽潜力 → 适应/休眠或常绿延续 | 低温适应、叶片保留和品种生理状态 | 落叶、defoliation、leaf retention、温室开闭 | “落叶”“休眠”“常绿”“非休眠”“everbearing”不是同义标签 |
| deciduous endodormancy → chill accumulation | 逐时温度及模型温度响应决定累计；暖温反转处理取决于模型 | 温室关闭/开窗会改变实际微气候；不可把设施日数当冷量 | Chill Hours、Utah、Dynamic 产出量纲不同；不能直接比较数值 |
| chill exposure → dormancy release | bud intrinsic state、品种需求、低温历史和 dormancy assay | dormancy-break chemical treatment 是独立干预 | 低温暴露量不是休眠解除观测；阈值依 cultivar、bud type、模型而变 |
| dormancy release → forcing | 满足休眠后的热量累积通常推动萌芽和花期进程 | greenhouse closure/opening、heating start/stop | chill 与 forcing 必须分开；冷量不足时化学处理路径不同 |
| forcing → bud swell / budbreak | 温度和 forcing duration；寒害可损伤已发育芽 | 加温、促早处理、通风/开棚 | 设施会同时改变昼夜温度、光照和冻害暴露，不是 calendar shift |
| budbreak → bloom | 芽发育速率、花序 florets、温度与 genotype | forcing、授粉蜂群布置 | 早花不确保早收或高产；花量和冻害是中介因素 |
| bloom → effective pollination | 花期、花 receptive 状态、兼容花粉、pollinator visits 和花期天气 | pollination start/end、人工授粉 | 访问次数不等于有效受精；自交亲和性和 type/cultivar 影响所需访问量 |
| pollination/fertilization → fruit set | 授粉成功、胚珠/种子形成与花器状态 | pollination management；不得以其替代观测 fruit set | 不同 cultivar 的果实发育、seed set 和自交/异交反应不同 |
| fruit set → crop load | 初始花量、set rate、落果、人工疏除 | flower removal、flower thinning、fruitlet/fruit thinning | 花芽疏除发生于开花前；摘花、疏花和疏果的作用时点不同 |
| crop load + source capacity → retention / berry growth | 叶面积、叶健康、光、温度、水分、营养和储备相对果实/新梢/根的需求 | 果负载和冠层管理、灌溉/营养干预 | leaf:fruit ratio 是局部 proxy，不是 whole-plant carbon balance |
| fruit set → Stage I | 早期细胞分裂/膨大、种子发育和 assimilate supply | thinning 可能改变 sink competition | 解剖阶段定义和果实组织贡献因品种不同 |
| Stage I → Stage II | 温度、发育年龄、源库条件 | 设施微气候影响温度；不等同固定日期移动 | double-sigmoid 支持较强，转段日期/热量仍需品种校准 |
| Stage II → Stage III | thermal age、果实生长、资源与 genotype | 水肥/冠层管理可能通过生理环境影响，但通用 effect size 未定 | stage nomenclature 尚不完全 harmonized |
| Stage III → color break → ripe | 温度、发育阶段、seed/hormone 及 genotype | greenhouse environment、shade 等可能影响环境输入 | climacteric/ethylene 的 crop-wide 分类仍有冲突；不设置普遍 hormone switch |
| ripe cohort → daily newly mature quantity | cohort 数量、成熟分布核、温度/发育状态和 crop load | 生理管理可影响成熟；采摘本身不改变 biological maturity definition | cohort 架构有科学根据，但 cohort kernel 属待校准模型抽象 |
| daily newly mature → harvested quantity | 这一步属于成熟库存、损耗和 picking capacity | 采摘班次/能力和 Harvest State 管理 | **不属于 S0 生物引擎**；不可把 maturity 与 harvest 或 arrival 混为一谈 |
| harvest → 下一年度采后状态 | 留果/采收时间、当前 crop load、叶片与根冠状态可能影响翌年 | postharvest management | 有跨年度机制证据但实用量化因果仍不足 |

### Q1：完整跨年度生长周期是什么？

从上一季采后开始，经植株结构/储备恢复、枝条生长停止、下一季花芽诱导和分化，进入落叶型或常绿型路径；落叶型将 chilling、休眠状态和 forcing 分开；之后进入 bud swell/break、花期、授粉/坐果、果实 cohort 的 Stage I–III、color break、ripe cohort，最后产生 daily newly mature quantity。成熟供给才交给 Harvest State。下一轮采后状态重新成为下一季起点。

## 4. 专题结论

### Q2：花芽形成由什么控制？

控制线索包括 cultivar/type、photoperiod、温度、shoot cessation、枝条/节点/cane age、冠层光环境、植株 vigor、上一季 fruit load 与资源状态。受控研究支持某些 highbush 材料的短日诱导；日本/新西兰跨品种观察表明，形成时间可随 type/cultivar 在采收期至采后变化。故可将 next-season flower-bud potential 作为跨年状态，但不能用固定“采后第 N 天”或统一短日阈值。

### Q3：剪枝通过哪些路径影响当季及下一季？

剪枝去除结果木和潜在花芽，改写 cane-age structure、productive shoot density、冠层光环境和潜在 crop load；同时可能促进新梢/叶幕更新，影响当季叶面积和未来生长。冬剪负载研究中，较低果芽负载可能提高粒重/品质而减少单株产量；NHB 不同 cultivar 和季节效应也不同。[Strik 等](https://doi.org/10.21273/HORTSCI.38.2.196)、[Jorquera-Fontana 等](https://doi.org/10.4067/S0718-95162014000400008)、[Hirzel 等](https://doi.org/10.4067/S0718-58392023000400418)。S0 不创建 pruning factor；事件必须保留 date/type/intensity/target/scope，removed fruiting-wood 和 bud ratios 可先作为待观测/待校准项。

### Q4：摘花/疏花和剪枝机制何异？

**FLOWER_REMOVAL != PRUNING。**花芽/花/幼果负载操作首先降低 reproductive sink；剪枝通常同时移除枝条/叶幕未来结构与潜在 sink，并改变光环境。SHB 花芽密度实验显示，花芽负载与 vegetative budbreak、leaf area、leaf-to-fruit ratio、果重和成熟时点相关；智利修剪研究也观察到果品质与单株产量的负载权衡。[Maust 等](https://doi.org/10.21273/hortsci.34.4.607)、[Kumarihami 等](https://doi.org/10.1016/j.scienta.2021.110530)。证据支持把两类管理分开，但并非所有研究都做了“相同 reproductive sink removal、仅剪枝不同”的完全匹配对照；效应量不可直接等同。

### Q5：决定最终 fruit set / crop load 的主要因素是什么？

crop load 是由潜在花量、花期状态、兼容花粉/授粉访问、受精/种子形成、温度与落花落果共同决定；疏除是后续管理干预。花期访问、品种自交兼容性、种子数/重量与果重/成熟时点存在证据关联；但是 bee visit count 不能作为 fertilization 或 fruit set 的代数替代。[Michigan/BC 授粉研究](https://doi.org/10.1371/journal.pone.0158937)、[13 个 SHB 品种授粉研究](https://doi.org/10.21273/HORTTECH.26.2.213)、[种子重量研究](https://doi.org/10.1016/j.scienta.2021.110313)。雨湿、低温等特定花期天气效应需按有直接证据的来源标注；S0 不制定授粉优化策略。

### Q6：source–sink 是否足以成为模型一级状态？

作为**因果状态族**足够成熟：source 包括当季叶幕/光合能力及储备；sink 包括花、果、新梢和根生长。果负载、叶面积/果数及 cultivar 影响果实和叶片 traits 有原始实验支持。[Maust 等](https://doi.org/10.21273/hortsci.34.4.607)、[Lobos 等](https://doi.org/10.1016/j.scienta.2018.06.041)。但单一 source-sink ratio 公式、whole-plant carbohydrate balance 和参数目前不够成熟。建议 S1 将 SourceCapacity、SinkDemand、SourceSinkRatio 作为概念状态/待选 proxy，S0 不选最终 proxy，也不伪造叶面积或 reserve 值。

### Q7：落叶型 blueberry 的 chilling / forcing 如何建模？

先区分低温暴露与内休眠状态。三个模型的含义不同：

- **Chill Hours**：按指定温度窗累计小时；实现简单，但暖温反转和不同温区效应表达有限。
- **Utah Chill Units**：对温度赋权并允许温暖温度抵消部分积累；具体版本对蓝莓预测的适用性有限。
- **Dynamic Model / Chill Portions**：用两阶段中间前体—稳定 chill portion 表达冷量生成与温暖逆转；其模型理论不是蓝莓 cultivar 阈值本身。

高丛蓝莓实验中，低温有效性并非等于“每个冷小时一样”，且模型适配因 cultivar/方法而异；综述指出 blueberry chill model 仍有 dilemma。[Norvell 与 Moore](https://doi.org/10.21273/JASHS.107.1.54)、[Warmund 综述](https://doi.org/10.71318/apom.2015.69.1.26)。因此理论结构可冻结为：

    chill exposure + cultivar/bud context
        → dormancy-state evidence
        → dormancy release
        → separate forcing accumulation
        → bud development / bloom

不能直接从累计 chill 推断 endodormancy 已解除。各品种阈值和模型选择留待具备匹配的 cultivar、温度、budbreak/dormancy 观察后验证。

### Q8：evergreen production 应怎样不同？

Evergreen/non-dormant 路径需要 canopy retention、叶片功能、冬季环境、花芽/开花路径和 management 独立状态。佛罗里达系统资料与 warm-winter 非休眠生产研究支持它区别于常规落叶周期；受控研究中 FL16-64 everbearing genotype 在测试日长和温度下表现出与 Arcadia 不同的生殖反应。[UF/IFAS system guide](https://doi.org/10.32473/edis-hs1362-2020)、[Darnell 等](https://doi.org/10.1080/14620316.1998.11511029)、[Benevenute 等](https://doi.org/10.1016/j.scienta.2025.114463)。但“保叶 evergreen”“non-dormant management”“遗传型 everbearing”不能互换；**禁止将 evergreen chill requirement 统一设为 0**。两条路径可以共享基本花—授粉—果实发育状态，但休眠/需冷/持续叶幕和开花路径不可强行共用。

### Q9：大棚/隧道促早改变什么？

设施首先改变逐时空气温度、日最低/最高温、根区温度、辐射/光、湿度、通风和冻害/授粉环境。高隧道、临时覆盖和温室研究显示，花芽/开花/成熟可能提前，但 fruit set、yield、果实质量或冻害风险也可能变化；效果不是单一平移。[Georgia 高隧道研究](https://doi.org/10.21273/HORTSCI.44.7.1850)、[Portugal 临时隧道研究](https://doi.org/10.17660/ActaHortic.2006.715.27)、[Spain 无加温隧道研究](https://doi.org/10.17660/ActaHortic.2006.715.47)、[Chile 高温研究](https://doi.org/10.3390/plants13131846)。环境观测优先级在 V0.9 计划中仍为 greenhouse sensor > farm sensor > nearest weather；S0 不将温室统一建模为 HARVEST_DATE_OFFSET。

### Q10：bloom cohort 能否映射到 maturity cohort？

**可以作为科学上可辩护的状态 lineage 和 S1/S3 候选结构**：花期、坐果、果实生长阶段和 ripe dates 有时间关联；生长阶段的 double-sigmoid 与组织变化有原始研究支持。[NeSmith](https://doi.org/10.1080/15538362.2011.619430)、[Shimura](https://doi.org/10.2503/jjshs.55.46)、[Yang 等发育研究](https://doi.org/10.1186/s12870-021-03067-6)。但果实发育期在品种/地点间不同；thermal kernel、分布宽度、cohort 观测粒度尚未统一。故是**结构支持充分、参数未识别**，不是已验证的成熟预测器。

### Q11：哪些机制足以进入 S1 contract？

可进入状态/事件 contract 的因果骨架：不同生产制度；上一季到本季的花芽潜力；chill accumulator 与 dormancy state 分离；forcing 独立记录；剪枝与花/果疏除分事件；花期—有效授粉—果 set 分状态；crop load/source-sink state；fruit cohort 和 staged maturity；greenhouse microclimate 输入；daily newly mature quantity 到 Harvest State 的接口。这里的 “ready” 只表示可定义状态、事件和边，不表示参数已可用。

### Q12：哪些仍需 future research？

待解决包括：目标 cultivar 的 Chill Hours/Utah/Dynamic 适用性及 dormancy-release 标签；南方设施 evergreen 与 deciduous 的可识别边界；不同 pruning timing/type 的交互与跨年度 carryover；最小可观测 source-sink proxy；授粉天气与花药兼容性到 crop load 的映射；阶段边界标准化；适用于目标 cultivar 的 thermal base/upper limits 和 cohort maturity kernel；设施对 pollination/source–sink/yield 的独立效应；以及任何云南生产参数。冲突不作跨论文平均，均保留在 uncertainty register。

## 5. 两个 production systems 的状态要求

| 项目 | DECIDUOUS_NATURAL | DECIDUOUS_FORCING | EVERGREEN |
|---|---|---|---|
| 基本路径 | 落叶/适应 → endodormancy → natural chill → dormancy release → ambient forcing | 落叶/适应 → chill requirement → dormancy release → cover/heating/forcing | 保叶/leaf function → 可能降低或不同的完整休眠表达 → system/genotype-specific bloom/fruit sequence |
| 必须记录 | leaf fall/retention、温度历史、休眠观察、萌芽/开花 | 上述字段 + closure/opening/heating 和 treatment 事件及时间 | canopy retention、冬季叶片状态、光合环境、系统标签定义与 genotype |
| 不允许 | 用某一 cultivar Chill Hours 替代 dormancy state | 用 forcing=true 代替 chill/heat sequence | 自动设置 chill requirement=0 |
| 共享下游 | bloom、pollination、set、fruit cohort、ripening | bloom、pollination、set、fruit cohort、ripening | 有条件共享下游繁殖状态；其前端 dormancy/leaf-retention path 不强制共用 |

## 6. 管理干预的因果划分

| ManagementEvent 类型 | 主要状态作用 | 可预期方向 | 证据边界 |
|---|---|---|---|
| PRUNING / WINTER_PRUNING / CANE_RENEWAL | 枝龄结构、fruiting wood、花芽数、冠层光、潜在叶面积 | sink 可能下降、枝条更新和 future source 可能改变；果实大小/产量有负载权衡 | 强度、枝条年龄、cultivar 和季节特异；不是标量 yield multiplier |
| SUMMER_PRUNING / POSTHARVEST_PRUNING | 新梢、冠层、花芽诱导环境 | 可能改变后续 shoot cessation 和花芽潜力 | timing-matched 多系统证据不足；S0 不排序或定系数 |
| FLOWER_BUD_THINNING / FLOWER_REMOVAL / FLOWER_THINNING | reproductive sink | 有效花量与潜在果数下降；source per remaining fruit 可能增加 | 与剪枝分开；花芽去除不等于落果后的疏果 |
| FRUITLET_THINNING / FRUIT_THINNING | 已坐果 sink、果数 | 可能改变果实大小、剩余负载和成熟分布 | 直接跨 cultivar 证据不足；操作时点需记录 |
| DORMANCY_BREAK_TREATMENT | bud dormancy/budbreak pathway | 可能诱导/集中萌芽，也有花芽伤害风险 | 与加温/forcing 分别记录；S0 不提供剂量 |
| GREENHOUSE_CLOSE / OPEN / HEATING_START / STOP | 实际环境轨迹和 forcing | 可能改变物候，也可能改变冻害、授粉、source 与果实质量 | 记录事件时间、强度/温度和空间 scope，非日历偏移 |
| POLLINATION_START / END | effective pollination exposure | 可能影响 fertilization、seed set 与 fruit set | bee visitation 不是 fruit set；不做 pollinator 优化 |
| SHADE_APPLICATION / IRRIGATION_STRESS / NUTRITION_INTERVENTION | source、叶幕和果实发育环境 | 可能改变光合能力、source-sink 和果实品质 | 变量需来源/authority 标记；效应非通用 |

## 7. Source–Sink graph 与最小可观察候选集合

理论 source：

    SourceCapacity
      = current leaf/canopy photosynthetic capacity
      + stored reserve contribution

理论 sink：

    SinkDemand
      = flowers + fruit cohorts + shoot tips + roots

这不是已定量验证的蓝莓方程。source capacity、reserve、sink demand 是不同状态/通量；leaf area / fruit number 只是潜在 proxy 之一。现有研究足以说明 source–sink 路径值得在 contract 中表达，但不支持在 S0 选定 proxy 或单位换算。

为 S2 审计准备的**观测候选集**（不是最终 proxy 选择）：

- 最小结构：plant density；productive shoot/cane count；cane-age class；pruning event；当前 fruit/flower load。
- canopy/source 候选：leaf area 或一致定义的 canopy-retention proxy；叶片健康/黄化记录；设施内 PAR/light 和温度；若已有则 root-zone temperature。
- reproductive sink：flower-bud count/sample；10/50/90% bloom 日期；flower removal/thinning scope/intensity；fruit-set sample；定期果数/load sample。
- 储备：若没有实测碳水化合物，标 LATENT/UNAVAILABLE；不从亩产、产量或叶面积反推储备。
- 结果端：按标签清楚的 bloom cohort 记录 fruit stage/color break/ripe sampling；成熟库存和采摘量由 Harvest State 分离。

所有 EnvironmentInput 字段均需 OBSERVED / PROXY / LATENT / UNAVAILABLE 标志、单位、传感器/来源和覆盖区间。最低可实施测量方案由 S2 决定，本节不授权大规模 IoT。

## 8. Chill 与 forcing：比较不等于选型

| 方案 | 理论计算思想 | 对 S0 的判断 | 蓝莓特定限制 |
|---|---|---|---|
| Chill Hours | 处于指定温度窗内的小时累加 | 简单、可解释；需要冻结温窗和小时数据质量 | 暖温抵消和不同温度效率的表达不足；品种阈值不通用 |
| Utah Chill Units | 对温区赋正/负权重，可能被暖温抵消 | 显式温度响应比普通小时窗丰富 | 权重/时间起点依赖版本；历史蓝莓比较不能据此确认全局最优 |
| Dynamic Chill Portions | 可逆 chill precursor 积累后形成较稳定 chill portion | 适合讨论波动暖冬的热过程表示 | 其通用果树模型机理不等于经蓝莓各 cultivar 校准 |

因此 S1 可要求 chill_model_id、hourly_temperature_source、chill_value/unit、dormancy_observation 分栏；S0 不决定 V0.9 production chill engine。

**Forcing** 应另算后休眠热响应，不与 chilling 混成一个值。温室加热、隧道闭合、氢氰胺/脱叶剂是不同 ManagementEvent；chemical treatment 可改变 budbreak 和 flower mortality，其作用机制不等于温度升高。[Abreu 等](https://doi.org/10.1371/journal.pone.0256942)、[Wang 等中国温室研究](https://doi.org/10.3390/agriculture11050439)。

## 9. Fruit development 与 cohort 可行性

SHB/NHB 的果实阶段研究支持用 Stage I/II/III 组织果实发育和 double-sigmoid growth；发育解剖研究进一步观察到花前细胞分裂、受精后膨大以及 color development。品种间 bloom-to-ripe duration、日历日期和 heat accumulation 存在差异。[NeSmith 等](https://doi.org/10.1080/15538362.2011.619430)、[Shimura](https://doi.org/10.2503/jjshs.55.46)、[Yang 等发育研究](https://doi.org/10.1186/s12870-021-03067-6)。

所以 “Bloom cohort → Fruit cohort → Ripe cohort”是足以供 S1 定义实体/因果 lineage 的结构候选；要转为 S3 可执行成熟引擎，还需确定 cohort 粒度、fruit set、thermal age、development kernel、每状态观测规则和参数 authority。S0 的文献数值只进入 literature candidate register，不作为默认参数。

## 10. Claim 类别与 S1 readiness

主张登记共 **30 条**：

| 证据分类 | 条数 | 含义 |
|---|---:|---|
| ESTABLISHED_MECHANISM | 8 | 可作为基本生物因果关系表达，仍需保留适用范围 |
| SUPPORTED_BUT_CONTEXT_DEPENDENT | 14 | 方向有证据，效应受类型/品种/环境/管理影响 |
| PLAUSIBLE_MODEL_ABSTRACTION | 4 | 可作为设计候选，不可写作已证实定量生物规律 |
| INSUFFICIENT_EVIDENCE | 3 | 关键参数或状态阈值尚无足够证据 |
| CONFLICTING_EVIDENCE | 1 | chill-model 选择/结果不可统一；更细差异另见不确定性台账 |

S1 contract readiness 统计：**24 条可进入状态/事件/边界 contract**；**6 条暂不具备模型/阈值/生产参数 readiness**。ready 的意思仅是可以在 S1 明确“是什么、哪些状态相连、证据支持到哪”，不等于具体变量现在都可观测，也不等于参数可辨识。

冲突/不确定性登记 15 项。核心 unresolved 包括 chilling 模型优先级、Evergreen 标签/休眠边界、不同管理操作下负载权衡、source-sink 定量 proxy、品种化果实成熟 kernel、ripening physiology 定义。不同研究不做简单平均。

## 11. 文献参数候选登记原则

参数台账目前登记 25 条研究中实际出现的数值或模型定义，包括 photoperiod/温度处理水平、特定 chill/forcing 序列、观察到的 bloom-to-ripe 日期范围、某地隧道试验时点、果实阶段时长和修剪/负载实验处理。所有条目均为 LITERATURE_OBSERVED_VALUE_ONLY 或 LITERATURE_PRIOR_CANDIDATE，并强制 not_production_default=true、calibration_requirement=Required。

例如 56.2–82.8 天来自 Georgia 七个 SHB cultivar 的 50% bloom 至 50% ripe；约 74 天来自中国两种 SHB 的 anthesis 到成熟时间序列；它们阶段定义、品种和地区不相同，不能合并为一个常数。S0 不创建云南 chill threshold、forcing base temperature、温室目标值、修剪系数或成熟 kernel。

## 12. S0 验收核对

| Gate | 结果 | 说明 |
|---|---|---|
| SCIENTIFIC_SOURCE_COUNT_SUFFICIENT | PASS | 47 unique sources，超过 40 |
| PEER_REVIEWED_SOURCE_COUNT_SUFFICIENT | PASS | 41 个 Tier A/A2 来源，超过 25 |
| COUNTRY_OR_REGION_COVERAGE_SUFFICIENT | PASS | 11 个具名国家/地区，含六个指定地区 |
| SOURCE_AUTHORITY_CLASSIFIED | PASS | 每来源标 A/A2/B/C；D/X 未作为科学 authority |
| PRODUCTION_SYSTEMS_SEPARATED | PASS | deciduous natural / deciduous forcing / evergreen 分开 |
| PRUNING_CAUSAL_PATH_REVIEWED | PASS | source 与 sink 的多路径及局限已登记 |
| FLOWER_THINNING_CAUSAL_PATH_REVIEWED | PASS | 与剪枝区分；直接头对头效应量不足 |
| FLOWER_BUD_FORMATION_REVIEWED | PASS | 上一季至下一季路径有独立 claim |
| CHILLING_REVIEWED / FORCING_REVIEWED | PASS | 三种 chill model 比较；未选全局模型 |
| EVERGREEN_REVIEWED / SOURCE_SINK_REVIEWED | PASS | 系统路径与 proxy 限制明确 |
| POLLINATION_FRUIT_SET_REVIEWED | PASS | visitation、fertilization、set 分开 |
| FRUIT_DEVELOPMENT / COHORT_FEASIBILITY | PASS | 阶段结构支持；成熟参数不视为已识别 |
| PROTECTED_CULTIVATION_REVIEWED | PASS | 六个指定地区均覆盖；地区深度不等 |
| CONFLICT_AND_UNCERTAINTY_REGISTER_COMPLETE | PASS | 15 项登记，允许 unresolved |
| BIOLOGICAL_CAUSAL_GRAPH_CREATED | PASS | 文档含完整跨年度图 |
| PRODUCTION_PARAMETER_CREATED | FALSE | 未创建 |
| MODEL_CODE_CHANGED / TRAINED / BACKTESTED | FALSE | 未执行 |

## 13. 研究边界与下一步

本 review 完成 S0 的 science authority 基础，不授权 S1–S4。下一步只有在用户单独授权后才开始 V0.9-S1 contract。S1 应使用 claim register 里明确的边/状态范围，并把未识别参数保留为待定字段；之后 S2 才能盘点企业真实观测和最小采集计划。

V0.8 的 2025–2026 benchmark 已消费：V0.9 可继续用于 audit、replay、reporting，但不可用于模型选择、参数选择、超参数选择或管理规则选择。本轮未读取其逐 Base 指标、未运行回测。

**结束状态：S0 完成；S1 未启动。**
