# جرد مشتق لحزمة مكتبة الموجه الطلابي 1448

تاريخ التحديث: 2026-10-04. هذا جرد مشتق من سجل المصادر ومصفوفة السجلات وmanifest وشجرة الملفات؛ لا يمنح مصدرًا سلطة جديدة.

## الأعداد ونطاقها

- سجلات سجل المصادر: 29؛ ليست كلها أصولًا مستقلة.
- الأصول المستقلة غير المشتقة: 25 (باستبعاد السجل المكرر وثلاثة سجلات أنواعها تبدأ بـ derived_). يشمل هذا العدد أرشيف القوالب بوصفه أصلًا واحدًا.
- المشتقات المسجلة: 3؛ النسخ المكررة المسجلة: 1.
- بصمات محتوى مختلفة بين السجلات: 28؛ يشمل هذا المقياس المشتقات، فلا يساوي عدد الأصول.
- نطاق catalog/manifest.json: 93 ملفًا ثابتًا من الأصول والنسخ التشغيلية المحددة؛ ليس جردًا لكل ملفات المشروع أو نطاق حزمة التسليم.
- قوالب أرشيف السجلات: 31 ملفًا؛ تقابلها 31 إحالة في مصفوفة نور، ولا يعني وجودها وجوب التعبئة أو وقوع العمل.
- مقاطع الاسترجاع JSONL: 850؛ تُزامن metadata من سجل المصادر ومصفوفة السجلات. النص القديم لم يُعد OCR أو التحقق الدلالي منه؛ يحكم الأصل عند الاستدلال.
- حزمة الإصلاح تُحدد بقائمة ملفات وبصمات مستقلة في تقرير التسليم؛ لا تُستنتج من ملفات Git أو manifest وحدهما.
- متابعة التحكيم 2026-10-04: حزمة المراجعة الكاملة تشمل اعتمادات archive التي يفحصها الفاحص العام، والنسخ السابقة الآمنة والفروق، وتحدد عضويتها الفعلية في REVIEW_MANIFEST مستقل. لا يصلح استبعاد archive في الحزمة السابقة نطاقًا لفحص المشروع العام. نتائج المحادثات السابقة تاريخية؛ قبول المتابعة والاسترجاع البارد NOT_RUN، والحالة CANDIDATE.

## الاستخدام الحالي

الأصل الإجرائي النشط REF-PROCEDURAL-FULL-1446؛ المقتطف REF-PROCEDURAL-1446 تاريخي ومساعد محدود النطاق فقط. حالة المصادر من السجل الحالي وفق قرارات الاعتماد، لا من عمر الإصدار أو metadata المقاطع.

وفق DEC-024 أزيلت مشتقات الفصل الثلاثة؛ توجيه التخطيط الحالي في catalog/reference_matrix.json وcatalog/program_source_rules.md، والأصول الرسمية محفوظة. الأعداد في الجرد السابق تاريخية؛ نطاق manifest الحالي 91 ملفًا بعد حذف3 وإضافة1 وتحديث الملفات الموجودة، وليس جرد المشروع الكامل.

## السجلات المسجلة

| المعرف | النوع | الحالة من السجل | جودة النص | موطن المرجع أو الأصل |
|---|---|---|---|---|
| `REF-QASSIM-1448` | regional_plan | plan_year_1448 | needs_ocr | `references/04_regional_plans/خطة برامج وخدمات التوجيه الطلابي تعليم القصيم 1448.pdf` |
| `REF-TASKS-GUIDE` | derived_regulatory_summary | derived_from_procedural_and_organizational_guides | needs_ocr | `references/02_regulatory/organizational_guides/مهام الموجه الطلابي حسب الدليل الإجرائي والتنظيمي .pdf` |
| `REF-ORGANIZATIONAL-1446` | official_organizational_excerpt | primary_for_roles_in_supplied_package | needs_text_review | `references/02_regulatory/organizational_guides/الدليل التنظيمي - مقتطف التوجيه الطلابي 1446.pdf` |
| `REF-PROCEDURAL-1446` | official_procedural_excerpt | historical_auxiliary_excerpt | needs_text_review | `references/02_regulatory/procedural_guides/الدليل الإجرائي - مقتطف الموجه الطلابي 1446.pdf` |
| `REF-FOLLOWUP-FORM` | operational | current_for_1448_review | searchable | `references/03_official_operational_guides/استمارة متابعة خطة الموجه الطلابي.pdf` |
| `REF-BEHAVIOR-1447-V5` | regulatory | current_user_approved | partially_searchable | `references/02_regulatory/behavior_and_attendance_regulations/قواعد السلوك والمواظبة الإصدار الخامس 1447.pdf` |
| `REF-OFFICIAL-GUIDE-V1` | official_operational_guide | current_user_approved | partially_searchable | `references/03_official_operational_guides/دليل برامج وخدمات التوجيه الطلابي الإصدار الأول.pdf` |
| `REF-NOOR-TECH` | noor_technical_guide | current_within_package | partially_searchable | `references/03_official_operational_guides/noor/الدليل الاسترشادي لأبرز الخدمات التقنية للتوجيه الطلابي في نظام نور.pdf` |
| `REF-NOOR-TECH-DUP` | duplicate_original | duplicate | partially_searchable | `archive/original_sources/الدليل_الاسترشادي_لأبرز_الخدمات_التقنية_للتوجيه_الطلابي_في_نظام.pdf` |
| `REF-HISTORICAL-BEHAVIOR` | recognized_applied_guide | recognized_by_qassim_plan_1448 | partially_searchable | `references/03_official_operational_guides/دليل التربويين لرعاية السلوك.pdf` |
| `PG-01` | program_guide | read_before_formal_program_execution | partially_searchable | `references/05_program_guides/01_التهيئة_والدعم/01 دليل الأسبوع التمهيدي.pdf` |
| `PG-02` | program_guide | read_before_formal_program_execution | partially_searchable | `references/05_program_guides/03_النمو_والمستقبل/02 دليل برنامج التوجيه المهني 1445.pdf` |
| `PG-03` | program_guide | read_before_formal_program_execution | searchable | `references/05_program_guides/02_الوقاية_والانضباط/03 دليل برنامج رفق لخفض العنف.pdf` |
| `PG-04` | program_guide | read_before_formal_program_execution | needs_ocr | `references/05_program_guides/01_التهيئة_والدعم/04 دليل إطار توثيق علاقة الأسرة مع المدرسة 1446.pdf` |
| `PG-05` | program_guide | supporting_material_requires_program_match | partially_searchable | `references/05_program_guides/04_برامج_توعوية_وتطويرية_للموجه/05 دليل برنامج المهارات النفسية والاجتماعية.pdf` |
| `PG-06` | program_guide | read_before_formal_program_execution | partially_searchable | `references/05_program_guides/03_النمو_والمستقبل/06 دليل برنامج رعاية ودعم الفئات الخاصة من الطلبة.pdf` |
| `PG-07` | program_guide | read_before_formal_program_execution | partially_searchable | `references/05_program_guides/04_برامج_توعوية_وتطويرية_للموجه/07 دليل برنامج رعاية متكرري الغياب والتأخر.pdf` |
| `PG-08` | program_guide | read_before_formal_program_execution | partially_searchable | `references/05_program_guides/03_النمو_والمستقبل/08 دليل برنامج المجلس الطلابي 1445.pdf` |
| `PG-09` | program_guide | read_before_formal_program_execution | partially_searchable | `references/05_program_guides/02_الوقاية_والانضباط/09 دليل برنامج الاستخدام الآمن للإنترنت والألعاب الإلكترونية 1445.pdf` |
| `PG-10` | program_guide | read_before_formal_program_execution | partially_searchable | `references/05_program_guides/03_النمو_والمستقبل/10 دليل برنامج تنمية الدافعية 1445.pdf` |
| `PG-11` | program_guide | read_before_formal_program_execution | partially_searchable | `references/05_program_guides/01_التهيئة_والدعم/11 دليل التوجيه وقت الأزمات.pdf` |
| `PG-12` | program_guide | read_before_formal_program_execution | partially_searchable | `references/05_program_guides/04_برامج_توعوية_وتطويرية_للموجه/12 دليل قائمة المشكلات الطلابية 1445.pdf` |
| `PG-13` | program_guide | read_before_formal_program_execution | partially_searchable | `references/05_program_guides/02_الوقاية_والانضباط/13 دليل برنامج السلوك الإيجابي.pdf` |
| `PG-14` | program_guide | read_before_formal_program_execution | searchable | `references/05_program_guides/02_الوقاية_والانضباط/خطة الانضباط 1448 التوجيه الطلابي.pdf` |
| `REF-NOOR-INDICATORS` | noor_operational_reference | current_within_package | partially_searchable | `references/03_official_operational_guides/noor/مؤشرات نظام نور التوجيه الطلابي.pdf` |
| `REF-RECORDS-ZIP` | templates_archive | templates_subject_to_decision_matrix | mixed | `references/06_templates_and_evidence/سجلات_التوجيه_وفق_خطة_1448/` |
| `REF-PROCEDURAL-FULL-1446` | official_procedural_full | current_user_approved | needs_text_review | `references/02_regulatory/procedural_guides/الدليل الإجرائي الكامل - رجب 1446.pdf` |
| `IDX-PROCEDURAL-COUNSELOR-1446` | derived_routing_index | active_derived_non_governing | searchable_utf8 | `catalog/خريطة_صفحات_الموجه_الطلابي_نسخة_متحققة.md` |
| `KNOW-PROCEDURAL-COUNSELOR-1446` | derived_procedural_knowledge | active_derived_non_governing | searchable_utf8 | `references/02_regulatory/procedural_guides/derived/كل_ما_يخص_الموجه_الطلابي_في_الدليل_الإجرائي_نسخة_متحققة.md` |
