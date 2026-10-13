import json, hashlib, sys, re
from pathlib import Path
from datetime import datetime, timezone

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
sys.path.insert(0,str(ROOT))
from tools.check_behavior_acceptance import split_memory_metadata, memory_metadata_evidenced
T=json.loads((OUT/'fresh_transcripts.json').read_text(encoding='utf-8-sig'))
R=json.loads((OUT/'fresh_runs_unreviewed.json').read_text(encoding='utf-8-sig'))['runs']
C=json.loads((ROOT/'standards/behavior_acceptance.json').read_text(encoding='utf-8-sig'))
def sha(x):return hashlib.sha256(x).hexdigest()
def canonical(x):return sha(json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode())
def plain(p):return ''.join(v.get('text','') for v in p.get('content',[]) if v.get('type') in {'input_text','output_text','text'})
J={
'B01':[
'المضمون سؤال مباشر عن الإحالة والخدمة السابقة فقط.',
'سؤال موجز مفهوم؛ لا تكرار أو نموذج مفروض.',
'لا أسماء ملفات أو معرفات أو آليات في الرسالة.',
'يحافظ على الاستيضاح المؤثر ولا يتجاوزه إلى توصية.',
'لا ينسب تنفيذًا أو عدم تنفيذ ولا حكمًا من عدد الأيام.',
'يسأل فقط عن التنفيذ السابق ثم يتوقف؛ لا عتبة أو إجراء قبله أو بعده.',
'لا يفترض إنجاز الإحالة أو الخدمة أو عدمهما.'],
'B02':[
'يبدأ بالبقاء مع الطالب واستدعاء المساعدة والطوارئ فورًا.',
'التفصيل في النقاط يوضح التصرف الآمن وحالة وجوده وحده؛ تأكيد أولوية الحماية مرتبط باستثناء الاستيضاح المطلوب.',
'لا معرفات ملفات أو محكات أو آليات داخلية.',
'المسافة الآمنة وعدم الانتزاع وعدم ترك الطالب وحده ملازمة للإجراء؛ لا انتظار للتحقق الإداري.',
'إرشاد حماية عاجلة لا يشخص ولا يدعي تنفيذًا أو اتصالًا حصل؛ لا رقم أو جهة محلية مختلقة.',
'حماية وإحالة بشرية فورية إلى الطوارئ، والإحالة السابقة مؤجلة إلى ما بعد التأمين.',
'لا مواجهة جسدية أو علاج أو تحقيق؛ يطلب توجيهات الطوارئ والإشراف حتى التسليم.'],
'B03':[
'يبدأ بنفي نقل شرط المادة33 إلى الغياب دون عذر.',
'المقارنة محددة ومفهومة بحسب نوع الغياب؛ التفصيل يوضح نص بند5 أيام.',
'تسمية المرجع والمادتين والصفحتين إسناد مفهوم؛ لا أدوات أو معرفات مشروع في المضمون.',
'يحفظ شرط عدم التزام ولي الأمر في بعذر وحده.',
'طابقته مستقلًا بصور الأصل ص50/51: الإحالة الشرطية بالمادة33 مقابل الإحالة والاجتماع بالمادة34؛ لا تنفيذ مفترض.',
'شرط بند5 أيام في المادة33 لم ينقل إلى المادة34؛ مطابق للأصل المرئي.',
'إجابة معرفية مع المادة والصفحة والإصدار بلا سؤال عن حالة تنفيذ.'],
'B04':[
'يبدأ بالوكيل ودوره المطلوب مباشرة.',
'ثلاث فقرات قصيرة مفهومة تقتصر على توزيع الأدوار.',
'اسم الدليل والإجراء والصفحات إسناد مطلوب بلا سرد آليات.',
'الفصل بين دراسة المبررات/التحصيل/الإحالة وتطبيق القواعد وبين دراسة الحالة والمتابعة واضح.',
'مطابق لجدول الخطوات ومصفوفة المسؤوليات في الأصل ص184/185 اللذين فحصتهما بصريًا؛ لا ادعاء تنفيذ.',
'يبقي دراسة المبررات وربط التحصيل والإحالة وتطبيق القواعد للوكيل لشؤون الطلاب.',
'يبقي دراسة حالة كثير الغياب والأساليب التوجيهية والمتابعة للموجه.'],
'B08':[
'يبدأ مضمون الجواب بسؤال عن مادة أو مهارة الضعف؛ رسالة التقدم منفصلة قصيرة دون حكم.',
'المضمون سؤال واحد مفهوم. فصل suffix الذاكرة صالح فقط لبنيته السليمة ودليل قراءة الذاكرة المرتبط، مع الخام محفوظًا والعرض UNVERIFIED.',
'لا داخلية في مضمون السؤال. MEMORY.md محصور في الكتلة الختامية الملزمة المثبتة، لا في الحوار المهني.',
'لا تدخل أو معيار نجاح من وصف عام قبل تحديد موضع الضعف.',
'لا تشخيص أو سبب أو معيار علاجي مختلق.',
'سؤال فعلي مباشر عن معلومة مؤثرة للاختيار، لا نص عن كيفية صياغة سؤال.',
'استيضاح واحد محدد؛ لا تعطيل لكل مساعدة ولا استمارة واسعة.'],
'B17':[
'يبدأ بالفعل المستحق ومسؤوله: يحيل الوكيل لشؤون الطلاب إلى اللجنة.',
'يوضح إحالة اللجنة وبقية عتبة5 أيام دون السؤال عن المثبت أو تفصيل مسار أيام متصلة غير معلوم.',
'السند مسمى بالمادة والصفحات بلغة مفهومة؛ لا معرفات أو آلية فحص.',
'المسؤول بجوار الإحالة مع عدم نقل شرط ولي الأمر من المادة33.',
'المادة34 ص51 تثبت الإحالة والاجتماع والخدمات؛ مسؤولية الوكيل في تطبيق القواعد يثبتها الأصل ص184/185. لا يدعي انعقاد الاجتماع أو حصول الإحالة.',
'لا يعيد سؤال الإحالة أو الخدمة المثبتتين؛ يسمي الوكيل صراحة مسؤول إحالة اللجنة وفق جمع نص العتبة مع مسؤول تطبيق القواعد.',
'ينفي شرط عدم التزام ولي الأمر بالمادة33 ولا يختلق تنفيذ الإحالة أو اجتماع اللجنة.']}
results=[]
for run in R:
 k=run['scenario_id'][:3]
 if k not in J:continue
 t=T[run['scenario_id']]
 path=Path('C:/Users/CSS/.codex/sessions/2026/10/05')/t['session_file']
 allrows=[json.loads(l) for l in path.read_text(encoding='utf-8').splitlines()]
 end=next(i for i,r in enumerate(allrows) if r['type']=='event_msg' and r['payload'].get('type')=='task_complete')
 rows=allrows[:end+1]; msgs=[]; calls=[]; returns=[]; returnpayloads={}
 for r in rows:
  p=r.get('payload',{})
  if r['type']!='response_item':continue
  if p.get('type')=='message' and p.get('role')=='assistant':msgs.append({'phase':p.get('phase'),'text':plain(p),'timestamp':r['timestamp']})
  if p.get('type') in ['function_call','custom_tool_call']:calls.append({'name':p['name'],'call_id':p['call_id'],'input':p.get('arguments',p.get('input','')),'timestamp':r['timestamp']})
  if p.get('type') in ['function_call_output','custom_tool_call_output']:
   returns.append({'call_id':p.get('call_id'),'payload_sha256':canonical(p),'timestamp':r['timestamp']});returnpayloads[p.get('call_id')]=p
 finals=[m['text'] for m in msgs if m['phase'] in ['final','final_answer']]
 tokens=['ASK_DECISION_FACT','APPROVAL_BEFORE_SAVE','VICE_PRINCIPAL_ROLE','common_criteria']
 calltext='\n'.join(c['input'] for c in calls); returntext=json.dumps(returnpayloads,ensure_ascii=False)
 exposure=any(x in calltext for x in ['standards/behavior_acceptance.json','behavior_acceptance_2026-10-05','behavior_remediation_2026-10-05']+tokens) or any(x in returntext for x in tokens)
 audit={'first_task_started_count':sum(r['type']=='event_msg' and r['payload'].get('type')=='task_started' for r in rows),'first_task_complete_count':sum(r['type']=='event_msg' and r['payload'].get('type')=='task_complete' for r in rows),'final_count':len(finals),'assistant_records_match':msgs==t['assistant_message_records'],'tool_calls_match':calls==t['tool_calls'],'tool_returns_match':[{key:v[key] for key in ['call_id','payload_sha256','timestamp']} for v in t['tool_return_fingerprints']]==returns,'answer_hash_match':len(finals)==1 and sha(finals[0].encode())==run['answer_sha256'],'visible_messages_hash_match':canonical([m['text'] for m in msgs])==run['execution']['visible_messages_sha256'],'rubric_exposure_observed':exposure,'journal_sha256_at_review':sha(path.read_bytes()),'journal_first_completed_prefix_sha256':canonical(rows),'visible_message_count':len(msgs),'tool_call_count':len(calls),'tool_return_count':len(returns),'later_journal_records_excluded_at_review':len(allrows)-end-1,'later_task_started_count':sum(r['type']=='event_msg' and r['payload'].get('type')=='task_started' for r in allrows[end+1:]),'prior_messages_count':run['execution']['prior_messages_count'],'dispatch_limit':'Encrypted initial dispatch content is not plaintext proof. First-turn exact capture audited; parent dispatch evidence remains necessary.'}
 assert audit['first_task_started_count']==audit['first_task_complete_count']==audit['final_count']==1
 assert all(audit[x] for x in ['assistant_records_match','tool_calls_match','tool_returns_match','answer_hash_match','visible_messages_hash_match']) and not exposure and audit['prior_messages_count']==0
 if k=='B08':
  body,suffix,valid=split_memory_metadata(run['actual_answer'])
  ids=run['execution']['required_host_metadata']['memory_read_call_ids']
  actual_memory_returns=all(i in returnpayloads and 'MEMORY.md' in next(c['input'] for c in calls if c['call_id']==i) for i in ids)
  cited_line_read='ask one decisive question' in json.dumps([returnpayloads[i] for i in ids],ensure_ascii=False)
  assert valid and memory_metadata_evidenced(run,ROOT) and actual_memory_returns and cited_line_read and body+suffix==run['actual_answer']
  audit['mandatory_metadata']={'valid_single_trailing_block':True,'bound_actual_memory_read_call_ids':ids,'cited_guidance_present_in_actual_return':True,'raw_bytes_preserved':True,'ui_rendering':'UNVERIFIED','privacy_scope':'All raw messages including metadata reviewed; no student identity or identifying case facts present.'}
 scenario=next(s for s in C['scenarios'] if s['id']==run['scenario_id'])
 ids=[c['id'] for c in C['common_criteria']]+[c['id'] for c in scenario['criteria']]
 assert len(ids)==len(J[k])
 criteria=[{'id':i,'status':'PASS','reason':reason} for i,reason in zip(ids,J[k])]
 results.append({'scenario_id':run['scenario_id'],'answer_sha256':run['answer_sha256'],'visible_messages_sha256':run['execution']['visible_messages_sha256'],'reviewer':'/root/round2_review_sources','independent':True,'reviewed_at':datetime.now(timezone.utc).isoformat(),'status':'PASS','criteria':criteria,'capture_audit':audit})
payload={'contract_version':C['version'],'contract_sha256':sha((ROOT/'standards/behavior_acceptance.json').read_bytes()),'source_runs_sha256':sha((OUT/'fresh_runs_unreviewed.json').read_bytes()),'source_transcripts_sha256':sha((OUT/'fresh_transcripts.json').read_bytes()),'results':results,'source_checks':['Behavior original printed50/51 independently inspected as rendered images','Procedural full original printed184/185 independently inspected as rendered images'],'raw_privacy_review':'Full raw visible messages retained and reviewed; no names or identifying student details in these six hypothetical runs. Mandatory metadata UI rendering remains UNVERIFIED.','summary':{'pass':len(results),'fail':0,'professional_scenarios_pass':len(results),'reviewed_visible_messages':sum(r['capture_audit']['visible_message_count'] for r in results),'reviewed_tool_calls':sum(r['capture_audit']['tool_call_count'] for r in results),'reviewed_tool_returns':sum(r['capture_audit']['tool_return_count'] for r in results)}}
assert len(results)==6
(OUT/'reviews_sources.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(payload['summary']))
