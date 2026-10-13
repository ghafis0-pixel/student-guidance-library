# سجل التغييرات المقترحة غير المنفذة

التاريخ: 2026-09-29  
الحالة الأصلية: مقترحات ناتجة عن المراجعة المستقلة.

تحديث 2026-09-29: اعتمد المستخدم مسار المراحل. نُفذت البنود `G-01` إلى `G-10` في مواصفة Gate v1.1، ثم نُفذت البنود `C-01` إلى `C-10` في المشغل والمخطط والاختبارات وmanifest. تغييرات الخطط والمكتبة والنماذج لم تنفذ، وتبقى محتاجة إلى مرحلتها واعتمادها المناسب.

## ضابط التنفيذ المستقبلي

- لا تُطبّق تغييرات بأثر رجعي على ملفات تاريخية إلا بسبب موثق.
- كل تغيير في Gate يرفع النسخة ويُسجل له سبب وقرار migration.
- لا تُنقل ملفات ولا تُعاد تسميتها ولا تُحذف تكرارات دفعة واحدة.
- لا تُعدّل خطة أسبوعية قبل إعادة اختبار Gate بعد إصلاحها.
- لا يُستخدم نور إلا في فحص محدد أو تنفيذ صريح مصرح به، مع تحقق الحفظ والظهور.

# 1. Gate changes

| ID | target | current | proposed | reason | risk | priority | approval required |
|---|---|---|---|---|---|---|---|
| G-01 | نطاق Gate | حكم واحد لكل المراحل | مراحل `DESIGN`, `PRE_EXECUTION`, `POST_EXECUTION`, `CLOSURE` | منع فشل الخطة بسبب حقيقة لم يحن وقتها | High | P0 | Yes |
| G-02 | D01 | الورقة التقاط مؤقت فقط | منع السجل الموازي فقط، مع استثناء التقاط مؤقت/أصل موقع/أداة حساسة/شاهد مطلوب | الصياغة الحالية أوسع من المصدر والواقع | High | P0 | Yes |
| G-03 | W01 | أولوية واحدة وقد تمنع النشاط الثاني | أولوية تقدم واحدة + مسارات إلزامية مستمرة + خدمات حدثية + طوارئ + حد WIP | واقعية منفذ واحد مع ADHD | High | P0 | Yes |
| G-04 | N01 | الربط بعد التنفيذ فقط | مسار متوقع في التصميم؛ اختيار فعلي وحالة حفظ بعد التنفيذ | فصل التخطيط عن الادعاء | High | P0 | Yes |
| G-05 | N03/V01 | غياب القيمة/الأثر قد يعامل كفشل | حالات `PENDING`, `NOT_MEASURED`, `NOT_APPLICABLE`, `NOT_ASSESSABLE_YET` | منع اختلاق القيم | High | P0 | Yes |
| G-06 | E03 | كل غموض زمني blocker | blocker فقط إذا تغير الاستحقاق؛ وإلا review مع normalization | 1447/1448 قرار محدد النطاق | Medium | P0 | Yes |
| G-07 | severity | block/fix/warning | BLOCKER/WARNING/REVIEW/INFO | تناسب الحكم مع الضرر | Medium | P0 | Yes |
| G-08 | evidence contract | نص وlocator غير فارغين | نوع دليل، locator موجود، صفحة/قسم، اسم مراجع وتاريخ | منع PASS الشكلي | High | P0 | Yes |
| G-09 | not applicable | قيمة عادية تمر بنص عام | سبب منظم ونطاق واسم مراجع | قابلية التدقيق | Medium | P1 | Yes |
| G-10 | migration | غير موضح | القواعد الجديدة مستقبلية؛ إعادة فحص القديم فقط عند خطأ جوهري أو طلب المستخدم | منع الأثر الرجعي | Medium | P1 | Yes |

# 2. Code changes

| ID | target | current | proposed | reason | risk | priority | approval required |
|---|---|---|---|---|---|---|---|
| C-01 | assessment schema | مفاتيح Python ضمنية | JSON Schema صريح مع enums وrequired/nonempty | ثبات المدخلات | High | P1 | Yes |
| C-02 | locator | لا يفحص | يتحقق من المسار داخل المكتبة ومن anchor/page إن أمكن | الاختبار المؤقت مرر locator وهميًا | High | P1 | Yes |
| C-03 | evidence | nonempty فقط | evidence type + claim + source + reviewer decision | جودة الإثبات | High | P1 | Yes |
| C-04 | metadata | وجود المفتاح فقط | تحقق ISO date و`Checked by` غير فارغ وscope معروف | حالات خاطئة أصدرت PASS | Medium | P1 | Yes |
| C-05 | YAML fields | `blocking` مهمل | إزالة الازدواج أو التحقق من اتساقه مع severity | منع اختلاف المواصفة والكود | Medium | P1 | Yes |
| C-06 | error handling | احتمال KeyError/استثناء | رسائل fail-closed مفهومة لكل مدخل مشوه | تشغيل آمن | Medium | P1 | Yes |
| C-07 | test plan path | `LIB.parent/outputs` | canonical داخل `student-guidance-library/outputs` | مسار هش | Medium | P1 | Yes |
| C-08 | test discovery | root command يشغل صفر | إضافة `tools/__init__.py` أو أمر موحد موثق/runner | قابلية التكرار | Low | P1 | Yes |
| C-09 | affected rules | تغير أي مرجع يمنع كل التقييم | ربط كل rule بمراجعها وإظهار المتأثر | تقليل إعادة العمل | Medium | P2 | Yes |
| C-10 | manifest | تقريران جديدان غير مدرجين بسبب حظر تعديل JSON في المراجعة | إدراجهما وإعادة توليد البصمات بعد الاعتماد | استعادة مرور `verify_library.py` بعد مخرجات المراجعة | Medium | P1 | Yes |

# 3. Library moves

لا يُنفذ أي نقل الآن.

| ID | target | current | proposed | reason | risk | priority | approval required |
|---|---|---|---|---|---|---|---|
| M-01 | دليل تعزيز السلوك داخل السجلات | نسخة مرجعية داخل templates/evidence | الإبقاء على المرجع في program guides ووضع إحالة داخل السجلات | تكرار وظيفة/تصنيف | Medium | P2 | Yes |
| M-02 | التقارير ذات المسارات المطلقة | provenance يعتمد `C:\Users\CSS\...` | مسارات نسبية أو source IDs | قابلية النقل | Medium | P1 | Yes |
| M-03 | نسخ المخرجات خارج المكتبة | `new-chat/outputs` ونسخة canonical | تحديد staging/تسليم ثم أرشفة غير الضروري | منع غموض النسخة المعتمدة | Low | P2 | Yes |

# 4. Library renames

| ID | target | current | proposed | reason | risk | priority | approval required |
|---|---|---|---|---|---|---|---|
| R-01 | نموذج المقابلة | `مفابلة إرشادية.docx` | `مقابلة إرشادية.docx` | خطأ مطبعي | Low | P2 | Yes |

لا تُغيّر أسماء الأصول داخل `archive/original_sources`؛ يطبق الاسم المنظم على النسخة المصنفة فقط مع حفظ `original_name`.

# 5. Duplicates requiring decision

| ID | type | group | proposed decision | reason | approval required |
|---|---|---|---|---|---|
| D-01 | Exact / Necessary Dual Record | أصل archive + نسخة مصنفة | KEEP | الأصل والنسخة المنظمة وظيفتان مختلفتان | Yes |
| D-02 | Exact / Documentation Duplicate | نص دليل نور التقني المكرر | استبعاد نسخة من الفهرسة، لا حذف الأصل | تحسين البحث | Yes |
| D-03 | Functional Duplicate | نماذج التوجيه الفردي | اختيار نموذج عامل واحد وإبقاء الآخر تاريخيًا | تقليل العبء | Yes |
| D-04 | Functional Duplicate | بطاقات الغياب/التأخر مقابل نور | التقاط مؤقت فقط إن احتاج العمل | منع سجل موازٍ | Yes |
| D-05 | Necessary Dual Record | أصل موقع + ملخص نور | KEEP كلاهما في موطنين مقيدين | متطلب مهني مشروع | Yes |
| D-06 | Near Duplicate | بطاقات الطالب/السجل الشامل | مقارنة الحقول قبل أي قرار | لا يكفي الاسم أو hash | Yes |

# 6. Paper form changes

| ID | target | current | proposed | reason | risk | priority | approval required |
|---|---|---|---|---|---|---|---|
| P-01 | أوراق الالتقاط | تعليمات جيدة لكن غير ممثلة في Gate بدقة | إضافة نوع النموذج وحالة الإتلاف/الحفظ وسبب الاستثناء | منع السجل الموازي دون فقد أصل | High | P1 | Yes |
| P-02 | دراسة الحالة/المقابلة | قوالب داخل Git | السماح بالقالب الفارغ فقط؛ النسخ المعبأة خارج Git | خصوصية | High | P1 | Yes |
| P-03 | التقارير العامة | قد تستخدم تلقائيًا | لا تنشأ إلا إذا طلب الدليل أو أضافت إثباتًا | عبء إداري | Medium | P2 | Yes |
| P-04 | حقول التوقيع | قد توحي بضرورة الطباعة | يحدد المصدر/الواقعة متى يلزم أصل موقع | لا تجعل الشكل متطلبًا | Medium | P2 | Yes |

# 7. Weekly plan corrections

لا تُعدّل الخطتان في هذه المرحلة.

| ID | plan | current issue | proposed future correction | basis | risk | priority | approval required |
|---|---|---|---|---|---|---|---|
| W-01 | 27 Sep-1 Oct | نور موصوف كمصدر حاكم للاستحقاق | استبداله بخطة القصيم/المصدر المختص، وإبقاء نور قناة توثيق | Source Authority Matrix | High | بعد Gate | Yes |
| W-02 | 27 Sep-1 Oct | لا عوازل/خطة يوم سيئ واضحة | إضافة الحد الأدنى دون توسيع الصفحات إلا عند الحاجة | ADHD rule | Medium | بعد Gate | Yes |
| W-03 | 27 Sep-1 Oct | لا شواهد تنفيذ | إبقاء الحالة «تنفيذ غير مثبت» حتى ورود دليل | نزاهة | High | عند الإغلاق | Yes |
| W-04 | 4-8 Oct | جدول بوابة برنامج ثابت رغم عدم الاستحقاق | جعله مشروطًا أو إحالة قصيرة | تقليل العبء | Medium | بعد Gate | Yes |
| W-05 | 4-8 Oct | locators ملتبسة | تصحيح الصفحة/المرجع الفعلي | قابلية التتبع | Medium | بعد Gate | Yes |
| W-06 | 4-8 Oct | مسار نور غير محسوم قبل الواقعة | كتابة «المسار المتوقع/يحدد بعد التنفيذ» | N01 المنقحة | Medium | بعد Gate | Yes |
| W-07 | كلاهما | التصميم قد يختلط بالإغلاق | فصل `ready design` عن `executed/entered/verified` | مراحل Gate | High | بعد Gate | Yes |

# 8. Items requiring human approval

1. اعتماد Source Authority Matrix رسميًا كترتيب المشروع.
2. اعتماد النطاق الدقيق لتصحيح 1447 إلى 1448 في خطة القصيم فقط.
3. اعتماد استثناءات الورق في D01 وسياسة الإتلاف الآمن.
4. اعتماد صياغة W01: أولوية تقدم واحدة مع المسارات الإلزامية والحدثية.
5. اعتماد نموذج الشدة ومراحل Gate.
6. اعتماد منع النسخ المعبأة الحساسة من Git وتحديد مخزنها المقيد.
7. اعتماد أن تغييرات Gate مستقبلية، ولا تعاد معالجة الملفات القديمة جماعيًا.
8. اعتماد التعديلات المحددة لكل خطة بعد اكتمال إصلاح Gate.
9. قرار حول النسخ الخارجية في `new-chat/outputs`.
10. قرار حول النقل/التسمية/الفهرسة لكل مجموعة تكرار بدل الحذف الجماعي.

# نقطة التوقف

تم إنشاء سجل المقترحات فقط. لم ينفذ أي تعديل وارد أعلاه.
