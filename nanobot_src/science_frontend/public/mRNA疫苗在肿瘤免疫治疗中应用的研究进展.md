# mRNA疫苗在肿瘤免疫治疗中应用的研究进展

## 摘要

mRNA疫苗技术近年来在肿瘤免疫治疗领域取得了突破性进展。新冠疫情推动了LNP递送系统的快速成熟，将mRNA推向了临床应用前台。mRNA肿瘤疫苗通过编码肿瘤相关抗原或新抗原，激活树突状细胞并诱导肿瘤特异性T细胞应答，在黑色素瘤、胰腺癌、HPV相关肿瘤等多个瘤种中展现出良好前景。个体化新抗原mRNA疫苗（mRNA-4157）和固定化肿瘤相关抗原疫苗（BNT111等）的临床研究数据显示，联合PD-1抑制剂可显著提升客观缓解率。本综述系统梳理mRNA肿瘤疫苗的技术平台、作用机制、临床证据、联合治疗策略及安全性数据，分析当前面临的新抗原预测准确性、递送系统优化、生产成本等挑战，展望AI辅助疫苗设计、淋巴结靶向递送等未来方向。

**关键词**：mRNA肿瘤疫苗；新抗原；脂质纳米颗粒；个体化治疗；免疫检查点抑制剂

---

## 一、引言

肿瘤免疫治疗自2010年代以来经历了快速发展，以PD-1/PD-L1抑制剂为代表的免疫检查点阻断疗法已成为多种实体瘤的标准治疗。然而，单药客观缓解率通常仅20-30%，多数患者最终出现耐药，提示需要联合多种免疫治疗策略。治疗性肿瘤疫苗作为主动免疫治疗的核心组成，旨在诱导持久的肿瘤特异性T细胞应答，有望与免疫检查点抑制剂形成协同效应。

mRNA疫苗技术平台经历了二十余年的积累与优化。1990年代Wolff等人首次报道mRNA可作为体内蛋白表达模板；2005年前后核苷酸修饰技术的引入显著降低了mRNA的免疫原性；2010年代LNP递送系统的成熟解决了mRNA的细胞内递送难题；2019年末新冠疫情催生了全球首个获批的mRNA疫苗产品，快速积累了大规模人群安全性数据。COVID-19 mRNA疫苗的成功不仅验证了平台技术的可行性，更为mRNA在肿瘤领域的应用奠定了坚实基础。

与传统的肽类肿瘤疫苗和树突状细胞（DC）疫苗相比，mRNA疫苗具有多重优势：可编码更大分子量抗原、诱导更强的CD8+ T细胞应答、无HLA限制性、可快速批量生产、且可通过序列优化调节免疫原性。个体化mRNA疫苗能够针对患者特有的肿瘤突变谱设计抗原，实现真正的精准免疫治疗。

本综述聚焦mRNA肿瘤疫苗在实体瘤治疗中的应用，系统评价其技术平台演进、免疫学机制、临床证据及联合治疗策略，并分析安全性特征与当前面临的转化挑战，为该领域的临床研究与未来发展提供参考。

---

## 二、mRNA疫苗技术平台概述

### 2.1 技术发展历程与分子结构优化

mRNA疫苗的核心结构包含5个关键元件：5'端帽（cap）、5'非翻译区（UTR）、编码区（ORF）、3'UTR和Poly(A)尾。早期mRNA分子因未经修饰而具有强免疫激活能力，2005年Karikó和Weissman发现核苷酸修饰（尤其是假尿苷替换尿苷）可显著降低Toll样受体（TLR）介导的免疫识别，同时保留mRNA的翻译活性，这一突破为mRNA的临床应用扫清了主要障碍。

近年来，非帽依赖性线性mRNA疫苗平台取得了新进展。2024年Nature Communications报道了一种线性帽独立mRNA（LciRNA）癌症疫苗平台，通过融合UPA保护序列和编码区，实现了无需5'帽结构的稳定翻译起始，并具有内在佐剂效应，在小鼠模型中诱导了强效的抗肿瘤免疫应答。该设计简化了mRNA的合成工艺，降低了成本。

### 2.2 序列设计与核苷酸修饰策略

mRNA序列设计涉及密码子优化、GC含量调节和核苷酸修饰等多个维度。密码子优化可提高翻译效率但需避免稀有密码子；核苷酸修饰（如N1-甲基假尿苷）可降低固有免疫激活、延长mRNA半衰期。新冠mRNA疫苗（BNT162b2和mRNA-1273）均采用核苷酸修饰策略，在大规模人群中验证了安全性。

自复制mRNA（saRNA）技术通过引入RNA复制酶基因，可在细胞内自主复制，显著减少所需剂量。2025年Science Translational Medicine发表的Research Article报道了HPV相关肿瘤模型中单次免疫自复制或非复制mRNA-LNP疫苗均可控制肿瘤生长，展示了该技术的应用潜力。

### 2.3 递送系统进展

LNP是目前最成熟的mRNA递送平台，由可电离脂质、磷脂、胆固醇和PEG脂质组成。可电离脂质在酸性环境下带正电，促进mRNA在内涵体中释放；PEG脂质可防止颗粒聚集、延长循环时间。COVID-19 mRNA疫苗的成功证明了LNP平台的安全性和有效性。

然而，当前LNP平台存在非特异性递送问题——静脉给药后约80% mRNA-LNP积聚在肝脏而非目标淋巴组织。2025年Vaccines报道了一种精准工程化的DC靶向mRNA-LNP新抗原疫苗，通过修饰LNP表面引导mRNA优先进入树突状细胞，在小鼠模型中诱导了更强的T细胞应答并展示了更优的肿瘤控制效果。

淋巴结靶向是提升mRNA疫苗效力的关键策略。2025年Nature Biomedical Engineering报道了一种转铁蛋白受体相关聚合体-mRNA复合物，通过单核细胞介导的运输实现淋巴结靶向积累，在多种肿瘤模型中展示了强效的抗肿瘤免疫激活。

此外，生物模拟纳米疫苗平台也在快速发展。2025年Journal of Advanced Research发表综述，系统介绍了包含外泌体、红细胞膜和肿瘤细胞膜在内的仿生递送系统，这些策略可增强免疫激活的精准性和临床疗效。

---

## 三、mRNA肿瘤疫苗作用机制

### 3.1 抗原呈递与T细胞激活路径

mRNA肿瘤疫苗通过肌肉或皮下注射进入人体后，被注射部位的树突状细胞（DC）摄取。mRNA在DC细胞质中利用宿主翻译机器合成肿瘤抗原蛋白，抗原蛋白经由主要组织相容性复合体（MHC）I类分子途径加工处理并呈递于DC表面，直接激活CD8+细胞毒性T淋巴细胞（CTL）。同时，DC可通过MHC II类分子途径激活CD4+辅助性T细胞，后者通过分泌IL-2进一步促进CTL增殖。

mRNA-LNP疫苗本身具有内在佐剂效应。LNP中的可电离脂质可激活DC的TLR信号通路，促进DC成熟和细胞因子分泌。2024年Frontiers in Immunology发表的比较临床研究评估了4种mRNA疫苗的免疫学和临床特征，揭示了mRNA疫苗共享的免疫学特征与独特机制，为理解mRNA疫苗的免疫激活提供了重要数据。

### 3.2 新抗原预测与mRNA编码策略

新抗原（neoantigen）来源于肿瘤细胞特有的非同义突变，具有肿瘤特异性和免疫原性，是个体化mRNA肿瘤疫苗的核心靶点。新抗原预测流程包括：全外显子组测序鉴定肿瘤突变、RNA-seq验证突变表达、HLA分型预测突变肽与MHC结合亲和力、人工智能算法进一步筛选具有高免疫原性潜力的突变肽。

mRNA-4157（V940）是个体化新抗原mRNA疫苗的代表产品，可编码最多34种患者特异性新抗原。2024年Cancer Discovery发表的KEYNOTE-603研究揭示了mRNA-4157的免疫原性机制：疫苗接种后可在患者体内检测到对新抗原的特异性T细胞应答，且应答强度与临床疗效相关。

固定化抗原mRNA疫苗则针对肿瘤相关抗原（TAA）设计，如BNT111针对黑色素瘤相关抗原（黑色素瘤分化抗原MART-1、酪氨酸酶、GP100等）。这类疫苗可批量生产、成本较低，但存在中枢免疫耐受和off-tumor毒性的潜在风险。

### 3.3 固有免疫激活与佐剂效应

mRNA疫苗的佐剂效应主要来源于以下机制：mRNA本身的TLR7/8激活（未修饰mRNA尤著）、LNP组分的TLR4激活、以及mRNA翻译产物dsRNA的MDA5通路激活。这些固有免疫信号可促进DC成熟、细胞因子分泌和T细胞初始激活。

2025年Molecular Therapy Nucleic Acids发表的HPV mRNA-LNP疫苗研究，深入解析了该疫苗如何系统性激活抗肿瘤免疫应答——疫苗接种后可在淋巴结、外周血和肿瘤微环境中检测到系统性的免疫激活信号，展示了mRNA疫苗诱导的免疫级联效应。

---

## 四、临床证据：单药与早期阶段研究

### 4.1 个体化新抗原疫苗mRNA-4157

mRNA-4157（V940，Moderna/默沙东共同开发）是个体化mRNA肿瘤疫苗的先驱产品。KEYNOTE-603 Phase 1研究在实体瘤患者中评估了mRNA-4157单用及联合帕博利珠单抗的安全性与疗效。2024年发表在Cancer Discovery的后续分析深入揭示了其免疫原性特征：疫苗接种后可检测到针对多个新抗原的CD8+ T细胞应答，应答者在临床上展示出更优的肿瘤控制效果。

mRNA-4157联合帕博利珠单抗在晚期黑色素瘤的Phase 2b研究（Keynote-942）于2023年公布结果：联合组客观缓解率（ORR）达50%，显著高于帕博利珠单抗单药组的32%；中位无进展生存期（mPFS）尚未达到vs 单药组4.1个月；联合组3级以上治疗相关不良事件发生率为14%vs 单药组10%。该结果于2024年获得FDA突破性疗法认定。

### 4.2 固定化抗原疫苗BNT111

BNT111（BioNTech）是针对黑色素瘤的固定化mRNA疫苗，编码4种黑色素瘤相关抗原（NY-ESO-1、酪氨酸酶、MART-1、GP100）。Phase 1/2研究（BNT111-01）初步验证了其安全性与免疫原性，单药或联合PD-L1抑制剂LIBTAYO显示出了一定的临床活性。

### 4.3 DC靶向mRNA疫苗

DC是mRNA肿瘤疫苗的核心效应细胞靶点，优化DC摄取的策略受到广泛关注。2025年Vaccines报道了一种精准工程化DC靶向mRNA-LNP新抗原疫苗，通过表面修饰实现DC优先摄取，在临床前模型中展示了更优的T细胞激活和肿瘤控制效果。

### 4.4 系统评价与Meta分析

2025年Journal of Translational Medicine发表的Meta分析系统比较了mRNA疫苗与树突状细胞疫苗在实体瘤中的疗效、免疫应答和安全性。该分析纳入多项临床研究，结果显示mRNA疫苗在诱导T细胞免疫应答方面与DC疫苗相当，但生产可行性和成本更具优势。

---

## 五、联合治疗策略

### 5.1 与PD-1/PD-L1抑制剂联用

mRNA肿瘤疫苗与PD-1/PD-L1抑制剂的联合是当前最主流的临床开发策略。理论上，疫苗诱导的肿瘤特异性T细胞浸润可提升肿瘤对免疫检查点阻断的敏感性；而PD-1/PD-L1抑制剂可通过解除T细胞耗竭维持疫苗激活的抗肿瘤免疫。Keynote-942研究中mRNA-4157联合帕博利珠单抗在黑色素瘤的ORR提升约18个百分点，证实了这一协同效应。

2024年Journal of Nanobiotechnology发表的临床前研究系统阐述了mRNA疫苗联合免疫检查点阻断的协同机制：疫苗增强肿瘤免疫原性、促进DC成熟和T细胞浸润；联合PD-1/PD-L1阻断可逆转T细胞耗竭、延长应答持续时间。该研究在多种肿瘤模型中验证了联合策略的显著抑瘤效果。

### 5.2 与其他免疫治疗联用

除PD-1/PD-L1抑制剂外，mRNA疫苗与其他免疫调节剂的联合也在探索中。2025年Signal Transduction and Targeted Therapy发表的回顾性研究提示，新冠mRNA疫苗接种后100天内启动免疫检查点抑制剂治疗的NSCLC和黑色素瘤患者，总生存期（OS）有改善趋势，提示mRNA疫苗可能通过激活免疫系统提升ICIs疗效。

HPV mRNA-LNP疫苗与免疫检查点抑制剂的联合正在HPV相关肿瘤中进行评估。2025年Molecular Therapy Nucleic Acids发表的临床前研究显示，该联合策略在HPV相关肿瘤模型中展示了系统性的免疫激活和肿瘤控制效果。

### 5.3 与化疗、放疗的协同

化疗和放疗可通过损伤相关分子模式（DAMP）释放增强肿瘤免疫原性，与mRNA疫苗形成正向协同。临床前研究提示，mRNA疫苗与标准化疗或放疗联合可增强抗肿瘤免疫应答，但临床证据仍有限。

---

## 六、安全性与耐受性特征

### 6.1 常见不良事件

mRNA肿瘤疫苗的安全性特征与COVID-19 mRNA疫苗类似，以1-2级局部和全身反应为主。常见不良事件包括：注射部位疼痛/红斑、发热、寒战、头痛、肌痛、乏力和恶心。发热通常是自限性的，多在接种后24-48小时内自行缓解。

### 6.2 严重不良事件与独特毒性

3级以上严重不良事件发生率相对较低。COVID-19 mRNA疫苗在广泛人群中积累的安全性数据为mRNA平台提供了重要参考，但仍需注意肿瘤患者与健康人群的差异——肿瘤患者可能存在更复杂的免疫异常和合并用药。

新抗原疫苗理论上存在针对正常组织表达相似抗原的交叉反应风险。2025年Journal for Immunotherapy of Cancer发表的综述指出，多个肿瘤相关抗原（TAA）含有与正常组织蛋白相同的共享表位，可能导致off-tumor毒性，需要在疫苗设计中予以关注。

### 6.3 长期安全性

由于mRNA肿瘤疫苗仍处于早期临床研究阶段，长期随访数据有限。mRNA本身在细胞质中短暂存在且不整合入基因组，理论上长期安全性风险较低。COVID-19 mRNA疫苗在数亿人群中的广泛使用提供了重要的安全性参考，心肌炎、过敏反应等严重不良事件发生率极低且多见于特定人群。

---

## 七、挑战、局限性与未来方向

### 7.1 新抗原预测准确性瓶颈

新抗原预测是个体化mRNA疫苗的核心技术瓶颈。尽管AI和机器学习算法不断优化，但预测准确性仍待提高——多数高预测分数的突变肽最终无法诱导有效的T细胞应答。2025年Frontiers in Immunology发表的黑色素瘤新抗原疫苗综述指出，新抗原选择需要综合考量突变表达水平、MHC结合亲和力、TCR识别潜力等多重因素，未来AI辅助的整合预测模型有望提升准确性。

### 7.2 递送系统的组织特异性分布

当前LNP平台静脉给药后主要积聚于肝脏，而非目标免疫器官。2025年Journal of Controlled Release发表的综述指出，淋巴结靶向是提升mRNA疫苗效力的关键策略——多种新型递送系统（可电离脂质纳米粒、聚合体-mRNA复合物、仿生纳米疫苗等）正在临床前和早期临床研究中评估，初步数据显示淋巴结富集可显著增强T细胞应答。

### 7.3 生产与时间成本

个体化mRNA疫苗需要针对每位患者定制生产，从肿瘤样本获取到疫苗制备通常需要数周时间，对于进展快速的晚期肿瘤患者可能延误治疗。此外，当前个体化疫苗的生产成本高昂，限制了可及性。固定化抗原mRNA疫苗和共享新抗原疫苗可在一定程度上解决这一问题，但仍需平衡个体化程度与疗效。

### 7.4 AI与精准医疗的融合

AI正在深度融入mRNA肿瘤疫苗的开发流程。2025年Frontiers in Oncology报道了AI辅助的肿瘤免疫图谱绘制用于优化mRNA疫苗设计的研究，利用机器学习算法整合肿瘤基因组、免疫微环境和患者免疫状态等多维度数据，实现疫苗抗原的智能选择和序列优化。这一方向有望系统性提升疫苗设计的精准性和成功率。

### 7.5 多种实体瘤的探索

当前mRNA肿瘤疫苗临床研究主要集中在黑色素瘤（因免疫原性强、高TMB、ICIs已获批），但正在向更多实体瘤拓展：胰腺癌（mRNA个性化新抗原疫苗）、HPV相关肿瘤（宫颈癌、头颈鳞癌）、食管癌、肺癌、结直肠癌等。2025年Translational Cancer Research报道了基于食管癌肿瘤抗原和免疫亚型的潜在mRNA疫苗开发研究，2025年Journal of Clinical Medicine发表的综述则全面梳理了mRNA疫苗在黑色素瘤PD-1抑制剂、T-VEC、肿瘤浸润淋巴细胞疗法演变格局中的定位。

---

## 八、结论与展望

mRNA疫苗技术在肿瘤免疫治疗领域展现出令人鼓舞的应用前景。新冠疫情加速了该技术平台的成熟，LNP递送系统的安全性已在数亿人群中得到验证，为mRNA肿瘤疫苗的临床转化奠定了基础。固定化抗原mRNA疫苗（BNT111）和个体化新抗原mRNA疫苗（mRNA-4157）的早期临床研究数据支持了进一步的临床开发，后者与PD-1抑制剂联合在晚期黑色素瘤中展示的ORR提升和PFS改善具有重要临床意义。

然而，该领域仍面临多重挑战：新抗原预测的准确性有待提高、递送系统的淋巴结靶向效率需要优化、个体化疫苗的生产成本和时间仍是瓶颈。AI辅助的疫苗设计、DC靶向递送、淋巴结靶向策略等技术创新有望系统性解决当前痛点。

未来五年将是mRNA肿瘤疫苗的关键验证期——多项Phase 2/3临床研究正在黑色素瘤、胰腺癌、HPV相关肿瘤等瘤种中推进，预计将提供更确切的疗效证据。若这些研究取得阳性结果，mRNA肿瘤疫苗有望成为实体瘤免疫治疗的重要组成部分，与免疫检查点抑制剂、细胞治疗等形成互补，为更多肿瘤患者带来临床获益。

---

## 参考文献

1. mRNA vaccines in oncology: personalized cancer immunization and neoantigen targeting. Molecular & Cellular Oncology. 2025.
2. Neoantigen-based cancer vaccines: a mechanistic and clinical review of personalised melanoma immunotherapy. Frontiers in Immunology. 2025.
3. Current Progress and Future Perspectives of RNA-Based Cancer Vaccines: A 2025 Update. Cancers. 2025.
4. mRNA Cancer Vaccines: From Pandemic Paradigm to Personalized Oncology Therapeutics. Cancer Innovation. 2025.
5. T-cell Responses to Individualized Neoantigen Therapy mRNA-4157 (V940) Alone or in Combination with Pembrolizumab in the Phase 1 KEYNOTE-603 Study. Cancer Discovery. 2024.
6. Next-Generation mRNA Vaccines in Melanoma: Advances in Delivery and Combination Strategies. Cells. 2024.
7. Engineering Anti-Tumor Immunity: An Immunological Framework for mRNA Cancer Vaccines. Vaccines. 2024.
8. A Precision-Engineered DC-Targeting mRNA-LNP Neoantigen Vaccine Elicits Stronger T Cell Responses and Exhibits Superior Tumor Control. Vaccines. 2025.
9. AI-powered mapping of tumor immunity for optimized mRNA vaccine engineering. Frontiers in Oncology. 2025.
10. Dual-Targeting mRNA Cancer Vaccines for Simultaneous Antigen Presentation in Dendritic and Tumor Cells. ACS Nano. 2025.
11. Comparative efficacy, immune response, and safety of mRNA versus dendritic cell vaccines in solid tumors: a systematic review and meta-analysis. Journal of Translational Medicine. 2025.
12. Enhanced mRNA vaccine combined with immune checkpoint blockade efficiently suppresses tumor growth and metastasis. Journal of Nanobiotechnology. 2025.
13. Validation of "SARS-CoV-2 mRNA Vaccines Sensitize Tumors to Immune Checkpoint Blockade" in an Independent Cohort of 4,407 patients. Cancer Letters. 2025.
14. Melanoma vaccines: current R&D landscape, translational hurdles, and future outlook-a perspective drawn from 442 clinical trials. Frontiers in Immunology. 2024.
15. Research and Clinical Progress of Therapeutic Tumor Vaccines. Vaccines. 2024.
16. Key Clinical Frontiers of mRNA Loaded Lipid Nanoparticles in Cancer Vaccines. International Journal of Nanomedicine. 2024.
17. An engineered linear cap-independent mRNA vaccine with intrinsic adjuvanticity induces potent anti-tumor immunity in mice. Nature Communications. 2024.
18. Shared epitopes create safety and efficacy concerns in several cancer vaccines. Journal for Immunotherapy of Cancer. 2024.
19. Biomimetic and personalized nanovaccines in cancer immunotherapy: Design innovations, translational challenges, and future directions. Journal of Advanced Research. 2025.
20. Nanovaccines in Cancer Immunotherapy: Lymph Node-Targeted Strategies and Mechanistic Insights. Current Pharmaceutical Design. 2024.
21. Neoantigen-based T cell vaccines design strategies, therapeutic barriers, and clinical advances. Vaccine. 2025.
22. A novel mRNA-based therapeutic vaccine elicits robust anti-tumor immunity against HPV-associated malignancies. Frontiers in Immunology. 2025.
23. When vaccines reset tumors: SARS-CoV-2 mRNA shots create a transient checkpoint-sensitive state. Signal Transduction and Targeted Therapy. 2024.
24. Personalized and HPV cancer vaccines in head and neck squamous cell carcinoma: from concept to clinical implementation. Translational Oncology. 2025.
25. Advancements in Melanoma Treatment: A Review of PD-1 Inhibitors, T-VEC, mRNA Vaccines, and Tumor-Infiltrating Lymphocyte Therapy in an Evolving Landscape of Immunotherapy. Journal of Clinical Medicine. 2024.
26. Developing of potential mRNA vaccines based on tumor antigens and immune subtypes of esophageal cancer. Translational Cancer Research. 2024.
27. Shared clinical and immunologic features of mRNA vaccines: preliminary results from a comparative clinical study. Frontiers in Immunology. 2024.
28. Polymer-mRNA complexes for monocyte-trafficked, lymph node-targeted cancer vaccination. Nature Biomedical Engineering. 2025.
29. A Structurally Stabilized Lipopolymer Nanoplatform Targeting Pan-Tissue Antigen-Presenting Cells Enables Durable in situ mRNA Cancer Immunotherapy. Advanced Materials. 2025.
30. mRNA vaccines: a new era in vaccine development. Oncology Research. 2025.