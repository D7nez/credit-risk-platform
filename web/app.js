const FEATURES = ['LIMIT_BAL','PAY_0','PAY_2','PAY_3','PAY_4','PAY_5','PAY_6','BILL_AMT1','BILL_AMT2','BILL_AMT3','BILL_AMT4','BILL_AMT5','BILL_AMT6','PAY_AMT1','PAY_AMT2','PAY_AMT3','PAY_AMT4','PAY_AMT5','PAY_AMT6'];
const GROUPS = [
  {title:'الحد الائتماني',help:'قيمة الحد الممنوح للبطاقة، بنفس وحدة بيانات التدريب.',fields:['LIMIT_BAL']},
  {title:'حالة السداد السابقة',help:'PAY_0 هو الشهر الأحدث؛ القيم الموجبة تدل على تأخر.',fields:['PAY_0','PAY_2','PAY_3','PAY_4','PAY_5','PAY_6']},
  {title:'الفواتير الشهرية',help:'من BILL_AMT1 الأحدث إلى BILL_AMT6 الأقدم.',fields:[1,2,3,4,5,6].map(i=>'BILL_AMT'+i)},
  {title:'المدفوعات الشهرية',help:'من PAY_AMT1 الأحدث إلى PAY_AMT6 الأقدم.',fields:[1,2,3,4,5,6].map(i=>'PAY_AMT'+i)}
];
const SAMPLE = {LIMIT_BAL:20000,PAY_0:2,PAY_2:2,PAY_3:-1,PAY_4:-1,PAY_5:-2,PAY_6:-2,BILL_AMT1:3913,BILL_AMT2:3102,BILL_AMT3:689,BILL_AMT4:0,BILL_AMT5:0,BILL_AMT6:0,PAY_AMT1:0,PAY_AMT2:689,PAY_AMT3:0,PAY_AMT4:0,PAY_AMT5:0,PAY_AMT6:0};
const $ = id => document.getElementById(id);
const percent = n => n == null ? '—' : `${(n*100).toFixed(1)}%`;
const num = n => Number(n).toLocaleString('en-US');
let toastTimer;
function toast(message, error=false){const node=$('toast');node.textContent=message;node.className=(error?'error ':'')+'show';clearTimeout(toastTimer);toastTimer=setTimeout(()=>node.className='',4200)}
function credential(admin=false){return sessionStorage.getItem(admin?'riskscope_admin_key':'riskscope_api_key')||''}
async function request(path, method='GET', body=null, admin=false){
  const headers = {'Accept':'application/json'};
  if(body!==null) headers['Content-Type']='application/json';
  headers[admin?'X-Admin-Key':'X-API-Key']=credential(admin);
  const response=await fetch(path,{method,headers,body:body===null?undefined:JSON.stringify(body)});
  const payload=await response.json().catch(()=>({error:`HTTP ${response.status}`}));
  if(!response.ok) throw Error(payload.error||`HTTP ${response.status}`);
  return payload;
}
function el(name,classes,text){const node=document.createElement(name);if(classes)node.className=classes;if(text!==undefined)node.textContent=text;return node}
function buildFields(){
  const target=$('inputGroups');
  for(const group of GROUPS){const section=el('section','field-section');section.append(el('h3','',group.title),el('p','',group.help));const grid=el('div','field-grid');
    for(const feature of group.fields){const label=el('label','',feature);const input=el('input');input.type='number';input.step='any';input.name=feature;input.required=true;input.placeholder='0';input.setAttribute('aria-label',feature);label.append(input);grid.append(label)}
    section.append(grid);target.append(section)}
}
function switchTab(tab){document.querySelectorAll('.nav').forEach(n=>n.classList.toggle('active',n.dataset.tab===tab));document.querySelectorAll('.tab-panel').forEach(n=>n.classList.toggle('active',n.id===tab));if(tab==='monitor'&&credential(true)) refreshMonitor()}
function readForm(){const record={};for(const key of FEATURES){const input=document.querySelector(`[name="${key}"]`);if(input.value.trim()==='')throw Error(`أدخل قيمة ${key}`);record[key]=Number(input.value)}return record}
function showScore(data){const root=$('scoreResult');root.replaceChildren();root.hidden=false;const circle=el('div','score-circle');circle.style.setProperty('--score',`${data.default_probability_next_month*100}%`);circle.append(el('strong','',percent(data.default_probability_next_month)));
  const text=el('div');text.append(el('h2','','احتمالية التعثر في الشهر التالي'),el('p','','تقدير إحصائي من نموذج تاريخي. لا تستخدمه وحده لاتخاذ قرار عن شخص.'),el('code','',`معرّف التنبؤ: ${data.prediction_id}`));
  root.append(circle,text);$('outcomeId').value=data.prediction_id;root.scrollIntoView({behavior:'smooth',block:'nearest'})}
function downloadText(name,content){const url=URL.createObjectURL(new Blob([content],{type:'text/csv;charset=utf-8'}));const a=el('a');a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),500)}
function parseCSV(text){const lines=text.replace(/^\uFEFF/,'').trim().split(/\r?\n/).filter(Boolean);if(lines.length<2)throw Error('CSV يحتاج صف عناوين وسجل واحد على الأقل');
  const header=lines[0].split(',').map(s=>s.trim());if(header.join('|')!==FEATURES.join('|'))throw Error('أسماء الأعمدة أو ترتيبها لا يطابق القالب. حمّل القالب من الزر.');
  if(lines.length-1>500)throw Error('الحد الأقصى 500 سجل في الدفعة');return lines.slice(1).map((line,i)=>{const cells=line.split(',');if(cells.length!==FEATURES.length)throw Error(`عدد الخانات غير صحيح في السطر ${i+2}`);const row={};FEATURES.forEach((f,j)=>{const value=cells[j].trim();if(!value||!Number.isFinite(Number(value)))throw Error(`قيمة غير رقمية في السطر ${i+2}، العمود ${f}`);row[f]=Number(value)});return row})}
function renderBars(container,values,labels){container.replaceChildren();if(!values.length||values.every(v=>v===0)){container.classList.add('empty-chart');container.textContent='لا توجد بيانات بعد';return}container.classList.remove('empty-chart');const highest=Math.max(...values,1);values.forEach((v,i)=>{const col=el('div','bar-col');const bar=el('i');bar.style.height=`${Math.max(2,(v/highest)*150)}px`;bar.title=`${labels[i]}: ${v}`;col.append(bar,el('small','',labels[i]));container.append(col)})}
async function refreshMonitor(){try{const data=await request(`/api/monitor?days=${$('windowDays').value}`,'GET',null,true);$('mPredictions').textContent=num(data.predictions);$('mLabeled').textContent=num(data.labeled);$('mMean').textContent=percent(data.mean_score);$('mPsi').textContent=data.drift.psi==null?'—':data.drift.psi.toFixed(3);$('psiHint').textContent=data.drift.status==='available'?'تغير توزيع الاحتمالات':'يلزم 100 تنبؤ للمقارنة';$('modelVersion').textContent=`نسخة النموذج: ${data.model_version}`;
    renderBars($('dailyChart'),data.daily_counts.map(d=>d.count),data.daily_counts.map(d=>d.date.slice(5)));renderBars($('scoreChart'),data.score_histogram,data.score_histogram.map((_,i)=>`${i*10}–${(i+1)*10}`));
    const q=data.performance;const ready=q.status==='available';$('qualityHint').textContent=ready?`مقاييس ${q.labeled} نتيجة فعلية ضمن الفترة`:`يلزم 30 نتيجة فعلية على الأقل مع وجود حالتي التعثر وعدم التعثر. المتاح: ${q.labeled}.`;
    $('qPr').textContent=ready?q.pr_auc.toFixed(3):'—';$('qRoc').textContent=ready?q.roc_auc.toFixed(3):'—';$('qBrier').textContent=ready?q.brier.toFixed(3):'—';$('qCapture').textContent=ready?percent(q.top20_capture):'—';
  }catch(error){toast(error.message,true);if(!credential(true))$('keyDialog').showModal()}}
function init(){buildFields();document.querySelectorAll('.nav').forEach(n=>n.addEventListener('click',()=>switchTab(n.dataset.tab)));
  $('keyButton').addEventListener('click',()=>$('keyDialog').showModal());$('keyForm').addEventListener('submit',event=>{if(event.submitter?.value==='cancel')return;sessionStorage.setItem('riskscope_api_key',$('apiKey').value);sessionStorage.setItem('riskscope_admin_key',$('adminKey').value);toast('حُفظت المفاتيح لهذه الجلسة')});$('apiKey').value=credential();$('adminKey').value=credential(true);
  $('sampleButton').addEventListener('click',()=>{for(const [key,value]of Object.entries(SAMPLE))document.querySelector(`[name="${key}"]`).value=value;toast('تم ملء مثال تجريبي من البيانات العامة')});
  $('scoreForm').addEventListener('submit',async event=>{event.preventDefault();try{const data=await request('/api/predict','POST',readForm());showScore(data);toast('تم حساب النتيجة وتسجيلها')}catch(error){toast(error.message,true);if(!credential())$('keyDialog').showModal()}});
  $('templateButton').addEventListener('click',()=>downloadText('riskscope_batch_template.csv',FEATURES.join(',')+'\n'+FEATURES.map(f=>SAMPLE[f]).join(',')+'\n'));
  $('batchButton').addEventListener('click',async()=>{try{const file=$('batchFile').files[0];if(!file)throw Error('اختر ملف CSV أولًا');if(file.size>2_000_000)throw Error('حجم الملف يتجاوز 2 MB');const rows=parseCSV(await file.text());const data=await request('/api/batch','POST',{records:rows});const node=$('batchResult');node.hidden=false;node.replaceChildren(el('h2','',`تم تحليل ${data.results.length} سجل`),el('p','',`معرّف الدفعة: ${data.batch_id} · نسخة النموذج: ${data.model_version}`));const button=el('button','primary-button','تحميل النتائج CSV');button.addEventListener('click',()=>downloadText('riskscope_scores.csv','prediction_id,default_probability_next_month\n'+data.results.map(r=>`${r.prediction_id},${r.default_probability_next_month}`).join('\n')+'\n'));node.append(button);toast('ظهرت الدفعة في لوحة المراقبة')}catch(error){toast(error.message,true);if(!credential())$('keyDialog').showModal()}});
  $('refreshButton').addEventListener('click',refreshMonitor);$('windowDays').addEventListener('change',refreshMonitor);
  $('outcomeForm').addEventListener('submit',async event=>{event.preventDefault();try{await request('/api/outcome','POST',{prediction_id:$('outcomeId').value.trim(),actual_default:Number($('outcomeValue').value)},true);toast('حُفظت النتيجة الفعلية');refreshMonitor()}catch(error){toast(error.message,true);if(!credential(true))$('keyDialog').showModal()}});
  fetch('/healthz').then(r=>{if(!r.ok)throw Error();return r.json()}).then(()=>{$('serviceStatus').textContent='الخدمة جاهزة';document.querySelector('.status-dot').classList.add('ok')}).catch(()=>$('serviceStatus').textContent='الخدمة غير متاحة');
}
document.addEventListener('DOMContentLoaded',init);
