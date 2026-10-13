# سجل تنفيذ Phase 0 قبل Migration

**تاريخ التنفيذ الفعلي:** 2026-10-02 (اسم الملف يتبع تسمية المرحلة المطلوبة 2026-10-01).  
**النطاق:** تثبيت الحالة الحالية فقط. لا تغيير لعدد الطلاب 130/140، أو ملف المصفوفة، أو `catalog/manifest.json`، أو بنية المشروع.

## 1. مطابقة نور وقرار S016

- النسخة التشغيلية المعتمدة لمطابقة **موطن التوثيق** هي `outputs/noor_action_mapping_review_2026-09-30.md`، كما يثبت `PROJECT_HANDOFF_CURRENT.md:86` ورأس النسخة المعتمدة. `catalog/noor_action_mapping.md` مسودة سابقة غير حاكمة. وُضحت الحالتان في رأسي الملفين فقط؛ لم تتغير صفوف المطابقة (185 صفًا في كل نسخة)، وثبت تطابق متن كل نسخة مع الـBaseline.
- **S016 لا يولد استحقاقًا مستقلًا من المصفوفة دون سند رسمي أو تكليف معتمد.** تضع ورقة `مصفوفة الفصل الأول!A125:Y125` له نهاية الفصل الأول، لكن `T125` يحيل إلى قرار مشروع لا إلى خطة القصيم. في خطة القصيم الأصلية، صفحة PDF 12 (الصفحة المطبوعة 13) تصف اللجنة ودورية اجتماعها بلا تقرير فصلي لها؛ وصفحة PDF 60 تذكر التقرير الفصلي تحت «سجل البرامج والخدمات» وتفصل عنه «اللجان والمجالس». يتفق ذلك مع `outputs/term1_eligibility_timing_decision_layer_1448.md:144` و`PROJECT_HANDOFF_CURRENT.md:151`. لا تعديل لملف XLSX في هذه المرحلة.

## 2. ملف المصفوفة

- الملف المرفق خارج جذر المستودع: `C:\Users\CSS\.codex\codex-remote-attachments\01a0f7cd-b8ff-7b11-8b13-29e6adca6784\1D2819A2-82C7-4BA4-A94E-F87F1CAB5234\1-مصفوفة_تنفيذ_الفصل_الأول-.xlsx`.
- SHA-256 الحالي والمحفوظ في الـBaseline: `e4dab039fc5ef88934efd1463f24ba5d788a917ce0175ecd3529c032acb801d6`، مطابق للقيمة المعتمدة. الاسم الفعلي يحتوي همزة مركبة (`ا` + U+0654) ولم يتغير بين الأصل والـBaseline.
- فُتح بنجاح: 5 أوراق، حزمة ZIP وCRC سليمان، 547 صيغة قابلة للتحليل، بلا روابط خارجية أو `#REF!` ظاهر أو أخطاء صيغ مخزنة. هذا فحص بنيوي، لا إعادة حساب بمحرك Excel. لم يُنقل أو يُعدل.

## 3. Git وتصنيف غير المتتبع

- **قبل Phase 0:** 19 ملفًا متتبعًا معدلًا و49 غير متتبع؛ لا حذف ولا إعادة تسمية ولا remote. **قبل الـcommit وبعد تعديل `.gitignore`:** 20 معدلًا و49 غير متتبع؛ ثم أضيف هذا التقرير فأصبح غير المتتبع 50. الملفات المتجاهلة الفعلية 4 ملفات Python cache (`.pyc`).
- صُنفت الملفات الـ49 الأصلية وفق الوظيفة والمحتوى، لا الامتداد. لم تظهر بيانات طالب فعلية أو هوية/هاتف/بريد في الملفات التي فُحصت. مسارات `C:\Users\CSS` الشخصية موجودة في تقارير تاريخية/بناء؛ لا تمنع commit محليًا، لكن يلزم فحصها قبل أي نشر عام.

| التصنيف | العدد | الملفات |
|---|---:|---|
| `TRACK_NOW` | 17 | `PROJECT_HANDOFF_CURRENT.md`؛ مقتطفا `archive/original_sources/1-الدليل-التنظيمي_-التوجيه-الطلابي.pdf` و`2-الدليل-الإجرائي-الموجه-الطلابي.pdf`؛ `catalog/core_guides_reading_map.md`؛ `outputs/noor_action_mapping_review_2026-09-30.md` و`outputs/term1_eligibility_timing_decision_layer_1448.md`؛ مقتطفا `references/02_regulatory/organizational_guides/` و`references/02_regulatory/procedural_guides/`؛ مرجع نور في `references/03_official_operational_guides/noor/`؛ ملفات `standards/` الخمسة (`WEEKLY_PLAN_GATE.md`, `WEEKLY_PLAN_GATE_CHANGELOG.md`, `weekly_plan_gate_assessment.schema.json`, `weekly_plan_gate_checklist.md`, `weekly_plan_gate_rules.yaml`)؛ `tools/__init__.py`, `tools/check_weekly_plan_gate.py`, `tools/test_weekly_plan_gate.py`. |
| `HISTORICAL_TRACK` | 29 | `HANDOFF_NOUR.md`؛ `catalog/noor_action_mapping.md`؛ ملفات `reports/gate_v1_1_dry_run_2026-09-29/` الخمسة؛ ملفات `reports/gate_v1_1_plan_corrections_2026-09-29/` الخمسة؛ `reports/master_review_2026-09-29/MASTER_REVIEW.md` و`PROPOSED_CHANGES.md`؛ `reports/noor_knowledge_base_handoff.md`؛ `reports/noor_program_action_evidence_impact_weekly_map.md`؛ ملفات `reports/noor_reconciliation_2026-09-29/` الاثنا عشر عدا `plan_text_snapshot.json`؛ `reports/noor_stage_zero_verification_audit.md`. محفوظة كسجل لا كقرار حاكم. |
| `DERIVED_REBUILDABLE` | 3 | `extracted_text/pdf/REF-ORGANIZATIONAL-1446.txt` و`REF-PROCEDURAL-1446.txt` (استخراج معكوس غير معتمد)، و`reports/noor_reconciliation_2026-09-29/plan_text_snapshot.json`؛ تُترك خارج هذا الـcommit وتبقى في الـBaseline. |
| `TEMPORARY` / `SENSITIVE_DO_NOT_TRACK` / `NEEDS_DECISION` | 0 | لا ملف من الـ49 يقع فيها بعد الفحص الحالي. |

الملفات المتتبعة المعدلة قبل المرحلة (19) تشمل `AGENTS.md`, `README.md`, `catalog/manifest.json`, أربعة ملفات فهرسة/مصادر أخرى في `catalog/`, `catalog/versions.json`, `catalog/weekly_operating_rules.json`, `chunks/operational_guides.jsonl`, ستة DOCX/PDF تشغيلية، `reports/build_summary.json`, `reports/structure_validation.json`, و`tools/verify_library.py`. فُحصت الثنائيات الستة بنيويًا ونصيًا دون دليل تلف أو بيانات طالب فعلية. هذا commit لقطة قبل Migration، لا اعتماد لصحة الرقم 140 أو بصمات manifest القديمة.

## 4. البصمات التسع القديمة في manifest

كل SHA حالي أدناه يطابق ملف الـBaseline؛ الاختلاف مع `catalog/manifest.json` ناتج عن تحديثات سبقت اللقطة ولم يُحدث جرد بصماتها. لا دليل فساد، ولم يُعدل manifest هنا. التحديثات النصية تتعلق بتعليمات Gate والمراجع وتصنيف دليل السلوك. `chunks` يحوي 208 سجلات صالحة، وتغير metadata فقط في 131 سجلًا للدليل. ملفات الخطة الثنائية سليمة؛ تغير نصها بما يتسق مع تصحيح الخطة، لكن النسخة التي سجلها manifest القديم غير متاحة للمقارنة البايتية.

| الملف | SHA في manifest | SHA الحالي والـBaseline | التقييم |
|---|---|---|---|
| `AGENTS.md` | `42c2f495a54a99b58fb90e58a48211aef4b89a2ca24beda9a802fcd307bc7436` | `414d22f111ad41b7f9728884b7cce025ce572fc54e60b684e9a0928e1d4ab25f` | تحديث تعليمات؛ بقيت حقيقة 140 قديمة، تعالج لاحقًا. |
| `catalog/package_inventory.md` | `7e5ce148303610f1b1c520c48a3ece1218eedfaf23df37a691062c6a90c7a2b1` | `b235186d974b6100f00ad1a9c35e7b461322902a7469dfac8312f38c72e37aea` | تحديث جرد 24→26 مرجعًا. |
| `catalog/reference_matrix.json` | `061b51771ddf9581a41ebf0144f2f58442b1248b8a168d4723c8f7dadeeda48d` | `d37e34cab12c62e50094bfaecb45f529cb3b9f1e9bad17185a249c0f5c2d17fc` | تحديث تصنيف/ربط؛ JSON صالح. |
| `catalog/source_registry.json` | `e9b525f96e5b4e9fa0bcc99b4bc4d8b2a7cfe63a633ae8074042b1f2bbd62ed4` | `df47e9606e3cb6bcf5ebed731f3e2bb739b9331430a6f3e866061dfc19acbe5b` | تحديث سجل 26 معرفًا فريدًا ومسارات موجودة؛ JSON صالح. |
| `catalog/unresolved_references.md` | `56c0fb14ae2da6bda0ca7bcfd2293962464a4f3e2337af41ae2f1dcb4121c549` | `db5871b88c6c317d6b719a13e29399ed7add5c647c279c654241654dcf6edc5f` | تحديث حالة المراجع. |
| `chunks/operational_guides.jsonl` | `026577ca5f2c463f8a0d17d48d084ed2283215e9c27a128c4b5ecc6314f5e203` | `03f8e985924e364e9370e9519734573a1bcd1e7d80bdd8dcf8c4718594fd9a71` | تحديث metadata، لا نص المقاطع/صفحاتها. |
| `outputs/weekly_plans/2026-10-04_to_2026-10-08/weekly_plan_2026-10-04_adhd.docx` | `f8569cd96931fa9f2e32042738ff812f6c4474524b8007fe3b967271d2c2bba8` | `3cb29234e362218cb547865cdce856211873ae909d084859a48e2e8070f8c0d0` | تصحيح خطة؛ ZIP وXML سليمان. |
| `outputs/weekly_plans/2026-10-04_to_2026-10-08/weekly_plan_2026-10-04_adhd.pdf` | `afa9cab5f2efa2f895484a8c56ff0f9add3e12b9fb74b3dfee6ec284beb823ba` | `ac3dd468bdc6666ee19b8565ad3e3b622bc7b928f1c10bb41d87a71b84352431` | نسخة PDF صالحة من صفحتين؛ رموز الإجراءات تتفق مع DOCX الحالي. |
| `README.md` | `4beef7584034593e0f3b6802b770fd5775cd105e7bd8a8fc67571f577ccfbd8f` | `90ae0eee7f66f95d170c86a661a8093881c8655935f2333397f35d0fc93ba08b` | تحديث وصف وتعليمات؛ بقيت حقيقة 140 قديمة. |

أضافت Phase 0 سطر `tmp/` فقط إلى `.gitignore`، فأصبح اختلاف بصمته عاشرًا مؤقتًا بالنسبة إلى manifest حتى إعادة الجرد في مرحلته المحددة. لم يُعدل manifest ولم تُعد توليد أي مشتقات.

## 5. نقطة الرجوع وحدود المرحلة

- أُنشئ commit محلي بعنوان `Checkpoint pre-migration state after Phase 0 reconciliation` يضم 20 ملفًا متتبعًا معدلًا و46 ملفًا من فئتي `TRACK_NOW`/`HISTORICAL_TRACK` وهذا التقرير (67 ملفًا إجمالًا)، ووسم محلي `pre-migration-2026-10-01` يشير إليه. لا `push` ولا remote.
- **بعد نقطة الرجوع:** لا تعديل متتبع، وتبقى المشتقات الثلاثة غير متتبعة عمدًا؛ الـBaseline تحويها. لا مانع معلوم للانتقال إلى Phase 1. تبقى مصالحة 130، وإدخال XLSX للمستودع، وتحديث manifest، والمسارات المطلقة قبل النشر العام أعمالًا **لاحقة** لا تنفذ في Phase 0.
