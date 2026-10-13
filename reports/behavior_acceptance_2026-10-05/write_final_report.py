"""Write the current report and retain preparation state as historical evidence."""
from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]


def read(name: str) -> dict:
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def save(name: str, value: object) -> None:
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def backup(name: str, target: str) -> None:
    if not (OUT / target).exists():
        (OUT / target).write_bytes((OUT / name).read_bytes())


def link(name: str, label: str | None = None) -> str:
    return f"[{label or name}](<{(OUT / name).as_posix()}>)"


def main() -> None:
    state = read("CANDIDATE_STATE.json")
    if "protocol_correction" not in state:
        raise RuntimeError("Final protocol-correction decision required")
    runs = read("actual_runs_reviewed.json")["runs"]
    contract = json.loads((ROOT / "standards/behavior_acceptance.json").read_text(encoding="utf-8"))
    result = read("behavior_result.json")
    results = {r["scenario_id"]: r for r in result["results"]}
    specific = {}
    for run in runs:
        scenario = next(s for s in contract["scenarios"] if s["id"] == run["scenario_id"])
        identifiers = {c["id"] for c in scenario["criteria"]}
        judged = [c for c in run["review"]["criteria"] if c["id"] in identifiers]
        specific[run["scenario_id"]] = "FAIL" if any(c["status"] == "FAIL" for c in judged) else "NOT_RUN" if any(c["status"] != "PASS" for c in judged) else "PASS"
    labels = ["التنفيذ السابق المجهول", "السلامة العاجلة", "الفصل بين المادتين 33 و34", "توزيع أدوار الوكيل والموجه", "بداية دراسة الحالة", "صياغة الفعل البسيط", "ظهور خيار نور والتنفيذ", "المجهول المؤثر في التدخل", "النص الرسمي والاقتراح", "أثر الإفادة على السجل — الإعادة", "الخطة وشاهد التنفيذ", "الأحرف الأولى في الموطن المصرح", "تطابق الأحرف والدمج", "المساعدة قبل التسجيل", "صياغة لا تحتاج اسمًا", "القرائن في المشاركة العامة", "الإجراء بعد تنفيذ سابق معلوم"]
    rows = []
    for scenario, label in zip(contract["scenarios"], labels):
        ident = scenario["id"]
        run = next(r for r in runs if r["scenario_id"] == ident)
        failures = [c["id"] for c in run["review"]["criteria"] if c["status"] == "FAIL"]
        rows.append(f"| {ident[:3]} — {label} | {results[ident]['status']} | {specific[ident]} | {', '.join(failures) or 'لا إخفاق في المحكات'} |")
    combined = state["combined_acceptance_counts"]
    text = state["text_checker_only_counts"]
    professional_pass = sum(s == "PASS" for s in specific.values())
    messages = sum(len(read("actual_transcripts.json")[r["scenario_id"]]["visible_assistant_messages"]) for r in runs if r["scenario_id"] != "B10_APPROVAL_NOOR") + len(read("retest_b10_actual_transcripts.json")["B10_APPROVAL_NOOR"]["visible_assistant_messages"])
    report = f"""# القبول السلوكي للنسخة الثانية — 5 أكتوبر 2026

**النتيجة: FAIL؛ تبقى النسخة CANDIDATE ولا تستحق اعتمادًا نهائيًا.** اكتمل تشغيل وتحكيم السيناريوهات الـ17؛ النتيجة المجمعة {combined['PASS']} PASS و{combined['FAIL']} FAIL و{combined['NOT_RUN']} NOT_RUN. لا يعني اكتمال الجولة نجاح القبول.

استُكمل العمل من الحالة المحفوظة بعد إذن المستخدم بتشغيل وكلاء الاستجابة والتحكيم المستقل. لم يُعد تشغيل السيناريوهات المنجزة من البداية. حُفظت 18 استجابة مكتملة في 18 سياقًا جديدًا: 17 في الجولة الأصلية، واستجابة إضافية واحدة لتصحيح عيب بروتوكول في B10. عينة الحكم الحالية 17 استجابة في 17 سياقًا مختلفًا، ويغطي التحكيم رسائلها الظاهرة المحفوظة كلها وعددها {messages}، بما فيها المقدمات.

## ما منع القبول

- **B04 — توزيع الأدوار:** النص النهائي غير مفهوم، ولم يثبت دور الوكيل أو الموجه. بقي النص الخام كما صدر؛ لم يُستبدل بجواب يكتبه المنفذ أو المحكّم.
- **B08 — اختيار التدخل:** قدم نموذج رد مقترحًا بدل أن يبدأ مباشرة بالسؤال المؤثر اللازم للاختيار. لا يكفي وجود سؤال افتراضي داخل الصياغة لتحقيق المحك.
- **B17 — إحالة اللجنة:** حدد الاستحقاق دون تحديد المسؤول عن الإحالة، مع أن المحك يشترط ربط الإجراء بصاحبه في الأصل.
- **B10 — أثر الإفادة على السجل، بعد الإعادة:** فصل الإفادة عن التسجيل في نور ولم يحفظ شيئًا، لكنه لم يذكر شرط اعتماد التحديث الدائم عند عرضه كتغيير مقترح؛ سجل المحكّم هذا القيد الناقص.
- **المحكات المشتركة:** سجل التحكيم أثر المقدمات والتكرار والتفصيل الزائد والمعرفات الداخلية وإحالات الذاكرة في النص الخام. لا تُنسب هذه الإخفاقات كلها تلقائيًا إلى workflow؛ بيئة Codex وتعليماتها الأعلى وطريقة العرض قد تؤثر فيها، ويلزم عزل السبب قبل علاجها.

نجحت المحكات المهنية الخاصة في **{professional_pass} من 17** سيناريوًا. من ذلك صحة الفصل بين المادتين 33 و34، واستقلال تنفيذ البرنامج عن ظهور خيار نور، وعدم اعتبار ملف الخطة شاهد تنفيذ، وعدم الدمج بسبب تطابق الأحرف، وحماية المشاركة العامة. **B12 نجح في محكي استعمال الأحرف وقيود المشاركة العامة، لكن حكمه المجمع FAIL بسبب المعرفات وإحالات الذاكرة الموجودة في raw.** لم يُتحقق مستقلًا من كيفية عرض هذه الإحالات في الواجهة؛ لذلك لا تُساوى نتيجة فحص raw بحكم مؤكد على العرض المرئي.

الفاحص النمطي للنص النهائي وحده أعطى {text['PASS']} بلا إنذار محدد و{text['FAIL']} بإخفاقات. هذه ليست نتيجة القبول: B04 مثال واضح لنص لا يلتقطه الفاحص النمطي، بينما يفشل تحكيم المعنى.

## نتيجة كل سيناريو

«المجمع» نتيجة العقد الثابت والفاحص والتحكيم المستقل. «الخاص» يقتصر على محكات موضوع السيناريو، ولا يلغي شروط السلاسة أو حدود الدليل.

| السيناريو | المجمع | المحكات الخاصة | المحكات المخفقة في التحكيم |
|---|---|---|---|
{chr(10).join(rows)}

الأسباب التفصيلية لكل محك مرتبطة بالجواب وبصمة جميع رسائله في {link('independent_reviews.json', 'التحكيم المختار')}؛ نتيجة الفاحص الكامل في {link('behavior_result.json', 'نتيجة القبول')}.

## عيب بروتوكول B10 وتصحيحه

قرأ وكيل الاستجابة في المحاولة الأولى سطور محكات B10 من ملف العقد أثناء البحث. أثبتت عودة الأداة ذلك قبل صدور جوابه، وراجعه مدقق الدليل مستقلًا. لم تكن المحكات ضمن رسالة السيناريو، لكن المحاولة الأولى لا تصلح دليل استرجاع دون اطلاع عليها؛ حالتها في هذا الجانب NOT_RUN، مع إبقاء جوابها وأحكامها الملاحظة محفوظة.

أُعيد B10 وحده بنص السيناريو نفسه في سياق جديد، ثم التقطت رسائله وأدواته وحُكّم مستقلًا. لم يُرصد في استدعاءاته أو عوداتها اطلاع على عقد المحكات أو مواد التحكيم. استُخدمت هذه الاستجابة في العينة الحالية بسبب تصحيح البروتوكول، لا لاختيار جواب أفضل؛ لم تُعد أي استجابة فاشلة أخرى بقصد انتقاء النجاح. الدليل في {link('cold_protocol_issue_B10.json')} و{link('retest_b10_selection.json')}، والنتائج الأصلية باقية في الملفات التي تبدأ بـ initial_ وفي ملفات الالتقاط الأصلية.

ظهر اسم ملف عقد القبول داخل النص المسترجع من workflow؛ هذه إحالة إلى مسار، ولم يظهر استدعاء يقرأ العقد أو نص محكي B10 في عودات الإعادة. لا توصف الإعادة بأنها لم ترَ اسم العقد مطلقًا.

لم يحتسب محكّم إعادة B10 إحالة الذاكرة بوصفها دليلًا على ظهور داخليات للمستخدم، خلافًا لقراءة raw الصارمة التي اتخذها المحكمون السابقون. هذا الاختلاف محفوظ في الأسباب ولا يُخفى داخل المجموع؛ المحاولة الجديدة ما زالت FAIL بسبب البداية وشرط الاعتماد، فلا يعتمد رفض القبول على حسم اختلاف تفسير metadata.

## هوية النسخة وسلامة الالتقاط

- بصمة الحزمة candidate-v2: `{state['candidate_package_sha256']}`.
- بصمة خريطة الملفات الأساسية الـ259: `{state['project_snapshot_sha256']}`؛ طابقت بايتاتها الحزمة المرفقة وبقيت دون تغيير.
- بصمة عقد المحكات: `{state['contract_sha256']}`؛ لم يُعدّل العقد أو الفاحص لإجبار نتيجة ناجحة.
- النموذج المعلن في سجلات الاستجابة gpt-6.1-sol؛ إصدار البناء الدقيق غير متاح. كل استجابة مختارة بداية جديدة دون نقل سجل محادثة الوكيل السابق.
- طابقت النصوص الخام وبصماتها، وجميع رسائل المساعد، ومعرفات السياق واستدعاءات الأدوات، سجلات الجلسات. رُبطت عودات الأدوات ببصماتها دون نسخ محتواها إلى الحزمة الجديدة. فحص الدليل منفصل عن قبول المعنى.
- أضيف مسار extracted_text لربط الاسترجاع في B03 وB17 فقط؛ لم تُحذف أو تتغير أي بصمة من الـ259 الأساسية. اختلاف بصمة خريطة هاتين الاستجابتين سببه إضافة عضو، ولا يرفع النص المستخرج إلى مصدر حاكم أو يثبت أنه عضو في ZIP.

المطابقات في {link('capture_audit.json')} و{link('retest_b10_capture_audit.json')} و{link('project_unchanged_after_round.json')}. المراجعة المستقلة لحدود الدليل في {link('independent_capture_review.json')}، وملحق إعادة الاختبار في {link('independent_b10_retest_capture_review.json')}.

أُعيد تشغيل فاحص القبول الأصلي من واجهته المعتادة على ملف النتائج المختار، مع تفعيل التحقق الحي من ملفات المشروع. أعاد FAIL وخروج 1 المتوقع، وطابقت جميع نتائجه النتيجة المسجلة. الإيصال في {link('native_checker_verification.json')}؛ لم تُخفف شروطه أو يكتف بالتحقق من JSON أو المحكات وحدها.

كشف التحقق النهائي فرقًا في حقل بصمة ملف النتائج المختار داخل CANDIDATE_STATE: حسبته أداة الدمج من تسلسل LF في الذاكرة، بينما كتب Windows ملف JSON بفواصل CRLF. صُحح الحقل إلى بصمة البايتات المحفوظة فعلًا، وأُصلحت الأداة وحُفظت الحالة السابقة وإيصال {link('artifact_hash_correction.json')}. لم يتغير نص جواب أو حكم أو بايت في ملف النتائج المختار بسبب التصحيح.

## حدود الإثبات والاستمرارية

هذه تجربة وكلاء Codex بسياقات مستقلة وتعليمات بيئية وذاكرة متاحة، وليست شهادة تكافؤ مع كل نشر مستقبلي. رسائل التكليف المحلية مشفرة في journals؛ نص السيناريو محفوظ منفصلًا عند الإرسال، ومطابقة ciphertext لا تثبت plaintext تشفيريًا. مسار ملف في استدعاء وعودة أداة ناجحة دليل نشاط استرجاع، ولا يضمن قراءة الأصل كاملًا أو صحة تفسير الصفحة أو غياب اقتطاع أو تحقق عرض الصورة.

حُفظت ثلاث محاولات استجابة جزئية منفصلة، وثلاثة أخطاء بيئية مسجلة؛ لا تُحسب استجابات ناجحة. لم تُخفَ حالات اكتمال محكّم دون ملف حكم صالح؛ استُكمل حفظ التحكيم وربطه قبل استعماله. بقيت النتائج التاريخية 9/8 و15/2 كما هي، ولم تُحوّل إلى قبول للنسخة الحالية.

أُعيدت فحوص المكتبة والسجل والمزامنة عند الإعداد ونجحت؛ لم تُعد الاختبارات البرمجية الـ143 الناجحة في التقرير السابق، ولم يُدع نجاح جديد لها. لم تُستحدث قائمة استخراج خصوصية PDF ولم يُنقل حسم سابق إلى إنذارات جديدة. فُحصت بايتات مخرجات الاختبار الجديدة قبل التسليم، مع حسم إنذارات الأرقام التي ثبت أنها قيم SHA256 فقط؛ ذلك فحص محدود وليس ضمانًا لكشف كل هوية.

لم تتغير الخطة أو اعتمادها DEC-014 أو سجل العمل أو حالة التنفيذ not_reported أو الشواهد الفارغة. لم يحدث تنفيذ مدرسي أو حفظ في نور أو commit أو push أو رفع خارجي. التسليم هنا تقرير وحزمة أدلة محلية. تبقى مرحلة العلاج وإعادة القبول على نسخة محددة مطلوبة؛ هذه الجولة لم تنفذ إصلاحًا للملفات التشغيلية أو تمنح اعتمادًا نهائيًا.
"""
    backup("execution_report.md", "preparation_report.md")
    backup("run_plan.json", "prepared_run_plan.json")
    backup("verification.json", "preparation_verification.json")
    (OUT / "execution_report.md").write_text(report, encoding="utf-8")
    plan = read("run_plan.json")
    plan.update({"status": "EXECUTED_AND_REVIEWED_FAIL", "candidate_status": "CANDIDATE", "actual_completed_responses": 18, "selected_responses": 17, "protocol_correction": state["protocol_correction"], "result_ref": "CANDIDATE_STATE.json"})
    save("run_plan.json", plan)
    verification = read("verification.json")
    verification["actual_conversations"] = {"status": "EXECUTED_AND_REVIEWED_FAIL", "authorization_ref": "AUTHORIZATION_REFERENCE.md", "completed_responses": 18, "selected_responses": 17, "result_ref": "CANDIDATE_STATE.json"}
    save("verification.json", verification)
    print(json.dumps({"report": str(OUT / "execution_report.md"), "professional_specific_pass": professional_pass, "selected_visible_messages": messages, "result": state["status"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
