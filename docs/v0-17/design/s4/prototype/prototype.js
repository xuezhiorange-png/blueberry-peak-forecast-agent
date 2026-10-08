/* SYNTHETIC DESIGN FIXTURE — NOT PRODUCTION DATA.
 * All aggregates, ranks and queue rows below are literal visual fixtures.
 * Number conversion occurs ONLY in the chart renderer for pixel coordinates.
 * No API, actual access, inference, simulation, aggregation or persistence.
 */
const fixture = Object.freeze({
  dates: ['01-02','01-03','01-04','01-05','01-06','01-07','01-08','01-09','01-10','01-11','01-12','01-13','01-14','01-15','01-16'],
  point: ['80','100','120','160','200','180','140','100','80','120','160','140','100','80','60'],
  capacity: ['140','140','140','140','140','140','140','140','140','140','140','140','140','140','140'],
  backlog: ['0','0','0','20','80','120','120','80','20','0','20','20','0','0','0'],
  total7: '980', total15: '1820', peakDate: '01-06', peak: '200',
  comparison: [
    {name:'B · 直接处理 140', rank:'1', loss:'980', max:'120', shortfall:'140', ending:'0'},
    {name:'C · 人数 × 人效 + buffer', rank:'2', loss:'980', max:'120', shortfall:'140', ending:'0'},
    {name:'A · 直接处理 120', rank:'3', loss:'1280', max:'200', shortfall:'260', ending:'80'}
  ]
});
const titles = {OVERVIEW:['总览','从保存的预测出发，先看数量，再看规划压力。'],FORECAST:['预测','核对日期、每日数量与保存预测的完整性。'],ATTRIBUTION:['影响因素','先确认解释 authority，再查看模型贡献。'],CAPACITY_SIMULATOR:['产能模拟','显式输入条件，比较处理能力与跨日积压。'],QUALITY:['预测质量','独立历史验证，不代表当前生产表现。']};
let page = 'OVERVIEW';
let state = 'READY';
let selectedDate = 4;
let scenario = 'A';
let stale = false;
const content = document.querySelector('#page-content');
const statePanel = document.querySelector('#state-panel');
const panelHead = (title,note,badge='') => `<div class="panel-heading"><div><h2>${title}</h2><p>${note}</p></div>${badge ? `<span class="badge neutral">${badge}</span>` : ''}</div>`;
function authorityDetails(){return `<details><summary>保存记录 authority 详情</summary><dl><dt>记录</dt><dd>DESIGN-001 · SYNTHETIC_COMPANY</dd><dt>来源</dt><dd>HIERARCHICAL · 合成设计身份，未查询真实记录</dd><dt>预测起点</dt><dd>2025-01-01（不是当前日期）</dd><dt>来源与投影</dt><dd>source_result_hash / projection_hash 在 S5 分别透传；本原型未生成业务 hash</dd><dt>层级</dt><dd>COMPANY → REGION → BASE；不含 FARM / FACTORY</dd><dt>完整性</dt><dd>${state==='PARTIAL' ? '部分样本：仅 7 日，不构成完整 H15' : '15 日合成设计样本'}</dd></dl></details>`;}
function kpis(){return `<section class="kpis" aria-label="核心预测指标">${[
['预测起点后 7 日累计量',fixture.total7,'kg','D1–D7 · 保存窗口'],
['预测起点后 15 日累计量',state==='PARTIAL'?'—':fixture.total15,'kg',state==='PARTIAL'?'不足 15 日 · 不可计算':'D1–D15 · 保存窗口'],
['保存曲线高峰日期',fixture.peakDate,'','2025 年 · 样本日期'],
['高峰日预测量',fixture.peak,'kg','来自保存日曲线，不累加子峰']
].map(([label,value,unit,note])=>`<article class="kpi"><div class="kpi-label">${label}</div><div class="kpi-value">${value} <small>${unit}</small></div><div class="kpi-note">${note}</div></article>`).join('')}</section>`;}
function chart(kind='point',id='forecast-chart'){return `<div class="legend"><span>${kind==='backlog'?'日末积压':'预测值 / POINT'}</span>${kind==='capacity'?'<span class="capacity">有效处理能力</span>':kind==='point'?'<span class="unavailable">80% / 90%规划上界 · 未绑定</span>':''}</div><div class="chart-frame"><canvas id="${id}" data-chart="${kind}" role="img" aria-label="${kind==='backlog'?'合成日末积压曲线':'合成逐日预测曲线'}；精确数量见下方日期详情和辅助表格"></canvas></div>`;}
function dateControls(){return `<div class="date-strip" aria-label="选择预测日期">${fixture.dates.slice(0,state==='PARTIAL'?7:15).map((date,i)=>`<button data-date="${i}" aria-pressed="${i===selectedDate}">${date}</button>`).join('')}</div><div id="date-detail" class="date-detail" aria-live="polite">2025-${fixture.dates[selectedDate]} · D${selectedDate+1} · 预测值 ${fixture.point[selectedDate]} kg · 两种规划上界暂不可用</div>`;}
function dailyTable(){return `<table class="data-table"><caption>合成辅助日表 · 原始数量字符串 · 缺失上界不是零</caption><thead><tr><th>日期 / Lead day</th><th class="numeric">预测值 kg</th><th class="desktop-extra">规划上界 80 / 90</th></tr></thead><tbody>${fixture.dates.slice(0,state==='PARTIAL'?7:15).map((date,i)=>`<tr><td><button data-date="${i}">2025-${date} · D${i+1}</button></td><td class="numeric">${fixture.point[i]}</td><td class="desktop-extra">— / — · NOT_AVAILABLE</td></tr>`).join('')}</tbody></table>`;}
function boundNotice(){return `<div class="notice"><strong>规划上界暂不可用 · NOT_AVAILABLE</strong>本次保存预测没有兼容的 M1 区间绑定，不用 POINT 替代上界。Point 不是已证明 P50；规划上界不是已证明分位数。历史覆盖率低于名义水平，不保证未来覆盖。</div>`;}
function overview(){return `${kpis()}<section class="panel">${panelHead('逐日预测','2025-01-02 至 01-16 · 合成保存曲线','POINT 可视样本')}${chart()}${dateControls()}${boundNotice()}</section><div class="columns"><section class="panel unavailable-panel">${panelHead('区域 / 基地贡献','需要同一权威范围的服务端贡献合同','NOT_AVAILABLE')}<p>当前 API 未提供合法子实体贡献比例。这里不会在浏览器推算占比，也不会用当前 registry 改写历史层级。</p><details><summary>层级完整性与贡献区别</summary><p>保存层级完整，不等于已获得贡献接口或独立子实体访问授权。缺 child 不当作零。</p></details></section><section class="panel">${panelHead('较高预测量日期','描述性关注顺序，不是生产报警')}<ol class="high-list"><li><span>01-06 <em>相对关注 1</em></span><strong>200 <small>kg</small></strong></li><li><span>01-07 <em>相对关注 2</em></span><strong>180 <small>kg</small></strong></li><li><span>01-05 <em>相对关注 3</em></span><strong>160 <small>kg</small></strong></li></ol></section></div><section class="panel">${panelHead('能力与数据范围','各模块独立，不将 Point 可用解释为全部能力可用')}<div class="status-list"><span class="badge">预测 · 设计样本</span><span class="badge neutral">规划上界 · 未绑定</span><span class="badge neutral">归因 · 未绑定</span><span class="badge neutral">质量 · 仅历史</span><span class="badge neutral">当前实际 · 不可用</span></div>${authorityDetails()}<details><summary>图表辅助数据表</summary>${dailyTable()}</details></section>`;}
function forecast(){return `${kpis()}<section class="panel">${panelHead('保存预测曲线','COMPANY 合成范围 · 可用 '+(state==='PARTIAL'?'7':'15')+' 日，不补足缺失日期')}<div class="tabs" aria-label="Horizon 说明">${['H1','H3','H7','H15'].map(h=>`<button data-horizon="${h}">${h}</button>`).join('')}</div><p id="horizon-help" class="help">H7 表示 D1..D7，H15 表示 D1..D15；不是某一个单日。摘要由服务端提供。</p>${chart()}${dateControls()}${boundNotice()}${authorityDetails()}</section><section class="panel">${panelHead('每日预测明细','点击日期，与曲线详情同步；手机保留日期与预测值，缺失说明在详情中')}${dailyTable()}</section>`;}
function attribution(){return `<section class="panel">${panelHead('本次预测的解释 authority','保存预测 DESIGN-001 · 合成 COMPANY 上下文','NOT_AVAILABLE')}<div class="notice"><strong>尚未绑定合法的 M1 归因来源</strong>Operational Peak 保存预测没有 M1 模型、当时特征快照与封存 point prediction 的精确绑定。不能使用一般特征重要性代替本次预测解释。</div>${authorityDetails()}</section><section class="panel unavailable-panel"><div class="empty-symbol" aria-hidden="true">—</div><h2>影响因素贡献暂不可用</h2><p>没有合法 authority，就不展示因素排名或贡献柱形。后续取得精确绑定后，此区域展示组贡献、正负方向和逐项明细。</p><div class="notice amber"><strong>模型归因，不是因果解释</strong>允许描述“模型中对本次预测贡献较大”；不把 Harvest State 贡献描述为造成产量变化。</div><details><summary>未来合法结果的展示规则（仅规格）</summary><p>有符号贡献采用零基线、正负方向标记和同源明细表。intercept、clip adjustment、serialization adjustment 独立，不擅自分摊。本原型未绘制虚构 READY 因素。</p></details></section>`;}
function capacity(){return `<section class="panel">${panelHead('设置情景条件','合成预声明 A/B/C；此静态原型不执行计算','初始积压固定 0')}<div class="notice amber"><strong>SYNTHETIC_COST · 非公司真实成本</strong>损失单位 SYNTHETIC_LOSS_UNIT；没有 canonical company cost，也未验证真实 ROI。</div><div class="form-grid"><label><span>规划水平</span><select id="planning"><option value="POINT">预测值 / POINT</option><option disabled>80%规划上界 · 未绑定</option><option disabled>90%规划上界 · 未绑定</option></select></label><label><span>显式选择成本合同（无默认）</span><select id="cost"><option value="">请选择合成成本合同</option><option value="BALANCED">BALANCED · 1 : 1</option><option value="UNDER_4X">UNDER_4X · 4 : 1</option><option value="OVER_4X">OVER_4X · 1 : 4</option></select></label></div><p class="help">上界不可用时不回退 POINT。情景只比较同一保存预测、规划水平、日期范围与成本合同。</p><div class="tabs" role="tablist" aria-label="编辑一个情景">${['A','B','C'].map(x=>`<button class="tab" role="tab" data-scenario="${x}" aria-selected="${x===scenario}">情景 ${x}</button>`).join('')}</div><div class="form-grid" id="scenario-form"><label><span>产能模式</span><select id="capacity-mode"><option value="DIRECT" ${scenario!=='C'?'selected':''}>直接处理能力</option><option value="WORKFORCE_DERIVED" ${scenario==='C'?'selected':''}>人数 × 显式人效</option></select></label><label><span>同日额外处理能力 kg/日</span><input id="buffer" inputmode="decimal" value="${scenario==='C'?'20':'0'}"></label><label id="direct-field"><span>直接处理能力 kg/日</span><input id="direct" inputmode="decimal" value="${scenario==='B'?'140':'120'}"></label><label id="workforce-field"><span>人数（非负整数）</span><input id="workforce" inputmode="numeric" value="${scenario==='C'?'10':''}"></label><label id="productivity-field"><span>显式人效 kg/人·日</span><input id="productivity" inputmode="decimal" value="${scenario==='C'?'12':''}"></label><div class="wide help">本样本逐日相同；S5 必须支持逐日输入并与保存日期精确对应。buffer 是当日处理能力，不是冷库库存，不结转。</div></div><div class="form-actions"><button class="primary" id="submit-simulation">模拟（预览提交说明）</button><button id="show-sample">查看预声明固定结果样本</button></div><p id="simulation-message" role="status" class="help"></p></section><div id="stale-message"></div><div id="fixed-results">${capacityResults()}</div>`;}
function capacityResults(){return `<section class="panel">${panelHead('固定结果样本 · 情景 B','仅展示预声明 POINT / UNDER_4X / 140kg 条件，不代表当前表单计算','SYNTHETIC FIXTURE')}<div class="kpis">${[['日处理量不足','4','天'],['累计日不足量','140','kg'],['最大积压','120','kg'],['期末积压','0','kg']].map(([a,b,u])=>`<article class="kpi"><div class="kpi-label">${a}</div><div class="kpi-value">${b} <small>${u}</small></div></article>`).join('')}</div><div class="notice">累计日不足量是每日新需求相对能力的 gross deficit；日末积压是跨日队列，二者不相同。</div><dl><dt>总处理利用率</dt><dd>派生展示约 86.67% · exact authority 1820 / 2100 kg</dd><dt>合成规划缺口损失</dt><dd>980 SYNTHETIC_LOSS_UNIT · 不是货币</dd><dt>利用率表示</dt><dd>Decimal50 / ROUND_HALF_EVEN / rounding_applied=true；零分母时不可计算</dd></dl>${chart('capacity','capacity-chart')}<details><summary>需求与能力辅助表</summary>${dailyTable()}<p>固定样本 B 的有效能力每天 140 kg，非表单推导。</p></details></section><section class="panel">${panelHead('跨日积压','日末 closing backlog，不是当天 daily overload')}${chart('backlog','backlog-chart')}<details><summary>积压辅助数据表</summary><table class="data-table"><thead><tr><th>日期</th><th class="numeric">日末积压 kg</th></tr></thead><tbody>${fixture.dates.map((d,i)=>`<tr><td>2025-${d}</td><td class="numeric">${fixture.backlog[i]}</td></tr>`).join('')}</tbody></table></details></section><section class="panel">${panelHead('给定条件下的情景排序','固定 POINT + UNDER_4X 设计样本；不同成本合同可能改变顺序')}<table class="data-table comparison-table"><caption>B 与 C 有效能力相同；相同结果按 scenario_id 最终打破并列</caption><thead><tr><th>情景 / 排序</th><th class="numeric">合成损失</th><th class="numeric">最大积压 kg</th><th class="numeric">累计不足 kg</th><th class="numeric">期末积压 kg</th></tr></thead><tbody>${fixture.comparison.map(r=>`<tr><td data-label="情景 / 排序"><span class="rank">#${r.rank}</span> ${r.name}</td><td data-label="合成损失" class="numeric">${r.loss}</td><td data-label="最大积压 kg" class="numeric">${r.max}</td><td data-label="累计不足 kg" class="numeric">${r.shortfall}</td><td data-label="期末积压 kg" class="numeric">${r.ending}</td></tr>`).join('')}</tbody></table><p class="help">DESCRIPTIVE_ORDER_UNDER_GIVEN_INPUTS_AND_COST_CONTRACT。不是优化、人员推荐或自动排产。synthetic loss 不代表公司收益。</p></section>`;}
function quality(){return `<section class="panel">${panelHead('历史验证范围','独立于全局所选 Operational Peak 保存预测','HISTORICAL_VALIDATION')}<div class="scope-strip"><span class="badge neutral">V0_15_S5_M1_RIDGE</span><span class="badge neutral">EXPOSED_OOT</span><span class="badge neutral">2025–2026</span><span class="badge neutral">BASE_COHORT_AGGREGATE</span></div><p class="help">STRICT_PIT=false · RETROSPECTIVE_OBSERVATION · production_accuracy_validated=false · prospective_interval_coverage_validated=false</p><div class="notice"><strong>当前产季 · NO_CURRENT_ACTUAL</strong>当前产季暂无可用于正式评分的实际采收数据。</div></section><section class="panel">${panelHead('历史点预测指标','以下数字仅为合成设计样本；S5 显示冻结历史证据，不重新评分')}<table class="data-table"><caption>H1/H3/H7/H15 前缀窗口 · 原始精确值将在详情中展示</caption><thead><tr><th>窗口</th><th class="numeric">WAPE</th><th class="numeric">MAE kg</th><th class="numeric">Bias kg</th><th class="numeric desktop-extra">累计 WAPE</th></tr></thead><tbody>${[['H1','24.0%','21.0','-4.0','24.0%'],['H3','23.5%','20.5','-3.5','20.0%'],['H7','23.0%','20.0','-3.0','18.0%'],['H15','24.5%','22.0','-4.5','17.5%']].map(r=>`<tr>${r.map((x,i)=>`<${i===0?'th':'td'} class="${i>0?'numeric':''} ${i===4?'desktop-extra':''}">${x}</${i===0?'th':'td'}>`).join('')}</tr>`).join('')}</tbody></table><p class="help">手机隐藏的累计 WAPE 在下方详情展开，不丢弃指标。</p><details><summary>累计 WAPE 与精确值详情（合成）</summary><p>H1 24.0% · H3 20.0% · H7 18.0% · H15 17.5%。展示格式不参与计算。</p></details></section><section class="panel">${panelHead('区间与规划上界历史覆盖','仅 H7/H15 有冻结覆盖证据；H1/H3 暂不可用','RETROSPECTIVE')}<div class="notice amber"><strong>历史覆盖率低于名义水平</strong>图中为合成布局样本，不代表未来 coverage guarantee。真实冻结结果亦低于名义 80% / 90%，必须保留负面证据。</div>${[['H7 · PI80','54','80'],['H7 · PI90','74','90'],['H7 · Upper80','72','80'],['H7 · Upper90','82','90'],['H15 · PI80','51','80'],['H15 · PI90','71','90'],['H15 · Upper80','70','80'],['H15 · Upper90','81','90']].map(([label,observed,nominal])=>`<div class="coverage-row"><span>${label}<br><small>名义 ${nominal}%</small></span><div class="bar-track" role="img" aria-label="${label} 合成观察 ${observed}%，名义 ${nominal}%"><div class="bar-observed" style="width:${observed}%"></div><div class="bar-target" style="left:${nominal}%"></div></div><strong>${observed}%</strong></div>`).join('')}<details><summary>候选 / 可计算 / 不可计算 / 覆盖数量（合成布局样本）</summary><table class="data-table"><thead><tr><th>窗口 / PI80</th><th>候选</th><th>可计算</th><th>不可计算</th><th>覆盖</th></tr></thead><tbody><tr><td>H7</td><td>100</td><td>100</td><td>0</td><td>54</td></tr><tr><td>H15</td><td>100</td><td>100</td><td>0</td><td>51</td></tr></tbody></table><p>S5 必须逐项透传真实 counts，不由 coverage 反推人数或行数。</p></details></section>`;}
function renderState(){
  const messages={LOADING:['正在读取已验证来源','加载只影响请求模块，不显示 pending 零值。'],EMPTY:['请选择已保存预测','可信授权上下文尚未接入；高级身份输入仅用于技术核验。'],PARTIAL:['部分数据 · 可用 7 日','H15 不可计算；不补零、不外推。层级缺 child 时不得进入模拟。'],NOT_AVAILABLE:['当前权威来源不支持此能力','不替代来源、不补齐模拟结果、不伪造归因。'],ERROR:['暂时无法读取，请重试','脱敏错误 READ_UNAVAILABLE；保留独立模块，不展示错误来源数据。'],AUTHORITY_MISMATCH:['来源身份不一致，已停止展示受影响结果','请重新核验完整保存记录身份。排名和模拟结果同时失效。'],NO_CURRENT_ACTUAL:['当前产季暂无可用于正式评分的实际采收数据。','历史验证与保存预测可独立查看；不提供实际采收导入或评分。']};
  if(state==='READY'){statePanel.innerHTML='';return false;}
  if(page==='QUALITY'){messages.EMPTY=['历史公共证据尚未就绪','不依赖全局保存记录；缺包时保持 NOT_AVAILABLE。'];messages.PARTIAL=['历史证据部分可用','仅展示已封存项；缺失覆盖项不补算。'];}
  const [title,description]=messages[state];
  const blocked=['LOADING','EMPTY','NOT_AVAILABLE','ERROR','AUTHORITY_MISMATCH'].includes(state);
  statePanel.innerHTML=`<section class="panel state-card ${state==='AUTHORITY_MISMATCH'?'notice mismatch':state==='ERROR'?'notice error':state==='PARTIAL'?'notice amber':''}" ${state==='LOADING'?'aria-busy="true"':''}><h2>${title}</h2><p>${description}</p>${state==='LOADING'?'<div class="skeleton-grid"><div class="skeleton"></div><div class="skeleton"></div><div class="skeleton"></div><div class="skeleton"></div></div>':blocked?'<button id="recover-state">'+(state==='ERROR'?'重试样本状态':'重新核验保存记录')+'</button>':''}</section>`;
  return blocked;
}
function render(){
  document.querySelector('#page-title').textContent=titles[page][0];
  document.querySelector('#page-description').textContent=titles[page][1];
  document.querySelector('#page-status').textContent='设计样本 · '+(page==='ATTRIBUTION'&&state==='READY'?'NOT_AVAILABLE':state);
  document.querySelectorAll('nav a').forEach(a=>{if(a.dataset.page===page)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');});
  if(selectedDate>6&&state==='PARTIAL')selectedDate=4;
  document.querySelector('.context-title').innerHTML=state==='EMPTY'?'请选择已保存预测':'示意公司 <span class="badge">COMPANY</span>';
  document.querySelector('.context p').textContent=state==='EMPTY'?'暂无已核验保存记录':page==='QUALITY'?'历史质量独立于此合成保存上下文':'起点 2025-01-01 · 保存记录 DESIGN-001 · '+(state==='PARTIAL'?'7':'15')+' 日样本';
  const blocked=renderState();
  content.innerHTML=blocked?'':({OVERVIEW:overview,FORECAST:forecast,ATTRIBUTION:attribution,CAPACITY_SIMULATOR:capacity,QUALITY:quality})[page]();
  document.querySelector('#recover-state')?.addEventListener('click',()=>{if(state==='ERROR'){state='READY';document.querySelector('#review-state').value=state;render();}else openDialog();});
  if(state==='PARTIAL'&&page==='CAPACITY_SIMULATOR'){document.querySelector('#fixed-results').hidden=true;document.querySelector('#stale-message').innerHTML='<div class="notice amber">短窗口或缺 child 必须由 S2 判定；不把此完整15日固定样本当作部分数据的模拟结果。</div>';}
  if(state==='PARTIAL'&&page==='QUALITY'){const panels=content.querySelectorAll('section.panel');panels[2].innerHTML='<h2>覆盖证据暂不可用</h2><p>当前部分证据状态不展示缺失覆盖项；不重新评分或推算。</p>';}
  bindPage();
  requestAnimationFrame(drawCharts);
}
function bindPage(){
  document.querySelectorAll('[data-date]').forEach(button=>{
    button.addEventListener('click',()=>selectDate(Number(button.dataset.date)));
    button.addEventListener('keydown',event=>{if(event.key==='ArrowRight'||event.key==='ArrowLeft'){event.preventDefault();const all=[...document.querySelectorAll('.date-strip [data-date]')];let next=all.indexOf(button)+(event.key==='ArrowRight'?1:-1);if(next<0)next=all.length-1;if(next>=all.length)next=0;all[next]?.focus();all[next]?.click();}});
  });
  document.querySelectorAll('[data-horizon]').forEach(b=>b.addEventListener('click',()=>{document.querySelector('#horizon-help').textContent=b.dataset.horizon+' = D1..D'+b.dataset.horizon.slice(1)+' 前缀窗口；摘要来自服务端，本原型不重算。';}));
  document.querySelectorAll('[data-scenario]').forEach(b=>b.addEventListener('click',()=>{scenario=b.dataset.scenario;stale=true;render();markStale();}));
  document.querySelector('#capacity-mode')?.addEventListener('change',()=>{resolveForm();markStale();});
  document.querySelectorAll('#scenario-form input,#cost,#planning').forEach(el=>el.addEventListener('input',markStale));
  document.querySelector('#submit-simulation')?.addEventListener('click',()=>{document.querySelector('#simulation-message').textContent=document.querySelector('#cost').value?'静态设计原型不执行模拟。S5 将提交完整已验证身份和逐日输入至 S2。':'请显式选择成本合同；没有默认成本。';});
  document.querySelector('#show-sample')?.addEventListener('click',()=>{document.querySelector('#fixed-results').hidden=false;document.querySelector('#stale-message').innerHTML='<div class="notice amber">以下仅为预声明固定结果样本，不是当前编辑输入的计算结果。</div>';requestAnimationFrame(drawCharts);});
  resolveForm();
  if(stale&&page==='CAPACITY_SIMULATOR')markStale();
}
function resolveForm(){const mode=document.querySelector('#capacity-mode');if(!mode)return;const workforce=mode.value==='WORKFORCE_DERIVED';document.querySelector('#direct-field').hidden=workforce;document.querySelector('#workforce-field').hidden=!workforce;document.querySelector('#productivity-field').hidden=!workforce;}
function markStale(){stale=true;const results=document.querySelector('#fixed-results');if(results)results.hidden=true;const notice=document.querySelector('#stale-message');if(notice)notice.innerHTML='<div class="notice amber" role="status"><strong>输入已修改，结果已过期</strong>当前输入没有有效结果或排名。请重新提交；静态原型不会进行业务计算。</div>';}
function selectDate(index){selectedDate=index;document.querySelectorAll('[data-date]').forEach(b=>b.setAttribute('aria-pressed',String(Number(b.dataset.date)===index)));const detail=document.querySelector('#date-detail');if(detail)detail.textContent=`2025-${fixture.dates[index]} · D${index+1} · 预测值 ${fixture.point[index]} kg · 两种规划上界暂不可用`;drawCharts();}
function drawCharts(){
  document.querySelectorAll('canvas[data-chart]').forEach(canvas=>{
    const box=canvas.getBoundingClientRect();if(!box.width||!box.height)return;
    const scale=window.devicePixelRatio||1;canvas.width=box.width*scale;canvas.height=box.height*scale;
    const ctx=canvas.getContext('2d');ctx.scale(scale,scale);
    const w=box.width,h=box.height,left=42,right=12,top=16,bottom=32,max=240;
    ctx.font='13px -apple-system, sans-serif';ctx.textBaseline='middle';ctx.fillStyle='#50645c';
    [0,60,120,180,240].forEach(v=>{const y=h-bottom-(v/max)*(h-top-bottom);ctx.strokeStyle='#e2e8e2';ctx.beginPath();ctx.moveTo(left,y);ctx.lineTo(w-right,y);ctx.stroke();ctx.fillText(String(v),4,y);});
    const count=state==='PARTIAL'?7:15;
    const px=i=>left+i*(w-left-right)/(count-1);
    const py=v=>h-bottom-(Number(v)/max)*(h-top-bottom);
    [0,4,count-1].forEach(i=>ctx.fillText(fixture.dates[i],Math.min(px(i)-16,w-38),h-10));
    const draw=(values,color,dash=[])=>{ctx.strokeStyle=color;ctx.lineWidth=2.5;ctx.setLineDash(dash);ctx.beginPath();values.slice(0,count).forEach((v,i)=>{if(i===0)ctx.moveTo(px(i),py(v));else ctx.lineTo(px(i),py(v));});ctx.stroke();ctx.setLineDash([]);};
    if(canvas.dataset.chart==='backlog')draw(fixture.backlog,'#93691f');else{draw(fixture.point,'#164b3b');if(canvas.dataset.chart==='capacity')draw(fixture.capacity,'#667b90',[6,4]);}
    if(canvas.dataset.chart==='point'){ctx.fillStyle='#164b3b';ctx.beginPath();ctx.arc(px(selectedDate),py(fixture.point[selectedDate]),4.5,0,Math.PI*2);ctx.fill();}
  });
}
const dialog=document.querySelector('#run-dialog');
function openDialog(){dialog.showModal();document.querySelector('#close-dialog').focus();}
document.querySelector('#select-run').addEventListener('click',openDialog);
document.querySelector('#close-dialog').addEventListener('click',()=>dialog.close());
dialog.addEventListener('close',()=>document.querySelector('#select-run').focus());
document.querySelector('#identity-fields').innerHTML=['source_kind','forecast_family','run_id','hierarchy_level','entity_id','target_season','origin_date','baseline_id','policy_version','expected_source_result_hash'].map(field=>`<label><span>${field}</span><input name="${field}" autocomplete="off" aria-label="${field}"></label>`).join('');
document.querySelector('#identity-form').addEventListener('submit',event=>{event.preventDefault();document.querySelector('#identity-message').textContent='仅展示核验流程：本原型不会访问 API 或把未验证身份提交为上下文。';});
document.querySelectorAll('nav a').forEach(a=>a.addEventListener('click',()=>{page=a.dataset.page;render();document.querySelector('#main').focus();}));
document.querySelector('#review-state').addEventListener('change',event=>{state=event.target.value;render();});
window.addEventListener('resize',drawCharts);
document.querySelector('#large-text').addEventListener('click',event=>{const enlarged=document.documentElement.classList.toggle('large-type');event.target.setAttribute('aria-pressed',String(enlarged));requestAnimationFrame(drawCharts);});
const initial=document.querySelector(`nav a[href="${location.hash}"]`);if(initial)page=initial.dataset.page;
render();
